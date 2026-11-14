"""
Offline tests of the agent loop on the OpenAI-compatible path, against a fake server.

    python -m backend.llm.tests.test_openai_loop

Covers: tool calls assembled from streamed fragments (two in parallel),
reasoning from reasoning_content, reasoning and <think> tags, reasoning
passback on and off, Thinking steps (start, deltas, completion with the same
id), callId linking, tool errors, the step limit, request settings and
extra_body, models without tools, usage summing, the cost with and without
a price for cache reads, complete(), the images of
a tool result, which follow the tool messages in a user message, and the tool
record of an answer (tool_record.py): what it holds (with the reasoning of models
that get it passed back, also of answers without tool calls), and that the next
turn's request starts with the last one word for word when the record goes back.
"""
import asyncio
import json
import sys
import traceback
from dataclasses import replace

from backend.llm.agent_loop import STEP_LIMIT_NOTE, complete, run_agent
from backend.llm.client import create_openai_client
from backend.llm.tests.fake_openai_server import (
    FakeOpenAIServer, chunk, completion, tool_call_delta, usage_chunk,
)
from backend.llm.openai_chat import TOOL_IMAGES_NOTE
from backend.llm.tool_record import images_note, record, with_text
from backend.llm.tools import Tool, ToolRegistry, ToolText
from backend.llm.types import KIND_OPENAI_COMPATIBLE, ModelConfig, Usage


def make_config(base_url: str, **overrides) -> ModelConfig:
    config = ModelConfig(
        id=7, display_name="Fake Kimi", model_id="fake-model", provider_id=1, provider_name="Fake",
        kind=KIND_OPENAI_COMPATIBLE, base_url=base_url, api_key="test",
        supports_tools=True, reasoning="always", reasoning_passback=True,
        input_price_per_mtok=2.0, output_price_per_mtok=10.0, currency="EUR",
    )
    return replace(config, **overrides)


async def lookup(key: str) -> dict:
    return {"key": key, "value": f"value-of-{key}"}


async def explode() -> str:
    raise RuntimeError("the database is on fire")


TOOLS = ToolRegistry([
    Tool(name="lookup", description="Look up a key", title="Looking Up",
         parameters={"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
         func=lookup),
    Tool(name="explode", description="Always fails", parameters={"type": "object", "properties": {}}, func=explode),
])


async def collect(config, messages, server, **kwargs):
    client = create_openai_client(config)
    events = []
    async for event in run_agent(config, messages, system_prompt="You are a test.", client=client, **kwargs):
        events.append(event)
    assert not server.errors, server.errors
    return events


def steps_of(events):
    return [data for kind, data in events if kind == "step"]


def tokens_of(events):
    return "".join(data for kind, data in events if kind == "token")


def assistant_messages(body):
    return [m for m in body["messages"] if m["role"] == "assistant"]


def record_of(events):
    """The answer's tool record: reported once, right before the usage."""
    kinds = [kind for kind, _ in events]
    assert kinds.count("tool_record") == 1 and kinds[-2:] == ["tool_record", "usage"], kinds
    return events[-2][1]


# ---------------------------------------------------------------------------
# Scripted model turns
# ---------------------------------------------------------------------------

def turn1_two_tools(body):
    """Reasoning in reasoning_content, then two tool calls streamed in fragments."""
    assert body["stream"] is True and body["stream_options"] == {"include_usage": True}
    assert body["messages"][0] == {"role": "system", "content": "You are a test."}
    assert [t["function"]["name"] for t in body["tools"]] == ["lookup", "explode"]
    assert "tool_choice" not in body
    return [
        chunk(reasoning_content="I need "),
        chunk(reasoning_content="two keys."),
        chunk(tool_calls=[tool_call_delta(0, id="call_a", name="lookup", arguments="")]),
        chunk(tool_calls=[tool_call_delta(0, arguments='{"ke')]),
        chunk(tool_calls=[tool_call_delta(0, arguments='y": "alpha"}')]),
        chunk(tool_calls=[tool_call_delta(1, id="call_b", name="lookup", arguments='{"key": "beta"}')]),
        chunk(finish_reason="tool_calls"),
        usage_chunk(100, 20, reasoning_tokens=8),
    ]


def make_turn2(expect_passback: bool):
    def turn2(body):
        """Check the history after round 1, then reasoning in `reasoning` and one more tool call."""
        assistant = assistant_messages(body)
        assert len(assistant) == 1, assistant
        first = assistant[0]
        assert [c["id"] for c in first["tool_calls"]] == ["call_a", "call_b"]
        assert json.loads(first["tool_calls"][0]["function"]["arguments"]) == {"key": "alpha"}
        if expect_passback:
            assert first.get("reasoning_content") == "I need two keys.", first
        else:
            assert "reasoning_content" not in first, first
        tool_messages = [m for m in body["messages"] if m["role"] == "tool"]
        assert [m["tool_call_id"] for m in tool_messages] == ["call_a", "call_b"]
        assert json.loads(tool_messages[1]["content"]) == {"key": "beta", "value": "value-of-beta"}
        assert all(not k.startswith("_") for m in body["messages"] for k in m), "runtime-only keys leaked"
        return [
            chunk(reasoning="Now the third."),
            chunk(tool_calls=[tool_call_delta(0, id="call_c", name="lookup", arguments='{"key": "gamma"}')]),
            chunk(finish_reason="tool_calls"),
            usage_chunk(150, 10),
        ]
    return turn2


def make_turn3(expect_passback: bool):
    def turn3(body):
        """Reasoning in <think> tags, then the answer."""
        assistant = assistant_messages(body)
        assert len(assistant) == 2
        if expect_passback:
            assert assistant[1].get("reasoning_content") == "Now the third."
        else:
            assert "reasoning_content" not in assistant[1]
        return [
            chunk(content="<thi"),
            chunk(content="nk>All three "),
            chunk(content="found.</think>\n\n"),
            chunk(content="Alpha, beta "),
            chunk(content="and gamma."),
            chunk(finish_reason="stop"),
            usage_chunk(200, 15, cached_tokens=100),
        ]
    return turn3


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_three_step_chain_with_passback(server):
    server.script(turn1_two_tools, make_turn2(True), make_turn3(True))
    config = make_config(server.base_url)
    events = await collect(config, [{"role": "user", "content": "Find alpha, beta, gamma"}], server, tools=TOOLS)

    kinds = [kind for kind, _ in events]
    assert kinds[-1] == "usage" and kinds.count("usage") == 1
    usage = events[-1][1]
    assert (usage.input_tokens, usage.output_tokens, usage.reasoning_tokens, usage.cached_input_tokens) == (450, 45, 8, 100)
    api = usage.to_api(config)
    # Without a cached price, cache hits cost the full input price
    assert api["currency"] == "EUR" and abs(api["cost"] - (450 * 2 + 45 * 10) / 1e6) < 1e-9, api
    # With one, the 100 cached tokens cost the cached price and the other 350 the input price
    api = usage.to_api(replace(config, cached_input_price_per_mtok=0.5))
    assert abs(api["cost"] - (350 * 2 + 100 * 0.5 + 45 * 10) / 1e6) < 1e-9, api

    steps = steps_of(events)
    thinking = [s for s in steps if s.type == "thought"]
    # Three reasoning segments, each sent empty at the start and complete at the end
    assert [s.title for s in thinking] == ["Thinking"] * 6
    assert [s.content for s in thinking] == ["", "I need two keys.", "", "Now the third.", "", "All three found."]
    assert thinking[0].id == thinking[1].id and thinking[0].id != thinking[2].id
    deltas = [data for kind, data in events if kind == "step_delta"]
    assert [d["delta"] for d in deltas if d["id"] == thinking[0].id] == ["I need ", "two keys."]

    calls = [s for s in steps if s.type == "tool_call"]
    results = [s for s in steps if s.type == "tool_result"]
    assert [c.callId for c in calls] == ["call_a", "call_b", "call_c"]
    assert sorted(r.callId for r in results) == ["call_a", "call_b", "call_c"]
    assert calls[0].title == "Looking Up" and json.loads(calls[0].content) == {"key": "alpha"}
    assert results[0].title == "Result: Looking Up" and results[0].metadata["value"].startswith("value-of-")
    assert tokens_of(events) == "Alpha, beta and gamma."
    assert len(server.requests) == 3

    # The tool record: both rounds as the model had them, then the answer's text
    tool_record = record_of(events)
    assert [m["role"] for m in tool_record] == ["assistant", "tool", "tool", "assistant", "tool", "assistant"]
    assert [c["id"] for c in tool_record[0]["tool_calls"]] == ["call_a", "call_b"]
    assert tool_record[0]["reasoning_content"] == "I need two keys."
    assert json.loads(tool_record[2]["content"]) == {"key": "beta", "value": "value-of-beta"}
    # The answer's last text keeps the reasoning that led to it
    assert tool_record[-1] == {"role": "assistant", "content": "Alpha, beta and gamma.",
                               "reasoning_content": "All three found."}


async def test_three_step_chain_without_passback(server):
    server.script(turn1_two_tools, make_turn2(False), make_turn3(False))
    config = make_config(server.base_url, reasoning_passback=False)
    events = await collect(config, [{"role": "user", "content": "Find alpha, beta, gamma"}], server, tools=TOOLS)
    assert tokens_of(events) == "Alpha, beta and gamma."
    assert all("reasoning_content" not in m for m in record_of(events))


async def test_next_turn_starts_with_the_last_request(server):
    """With the record in the history, the next answer's request continues the last one word for word."""
    question = {"role": "user", "content": "Find alpha, beta, gamma"}
    follow_up = {"role": "user", "content": "Did you look them up?"}
    for passback in (True, False):
        server.reset()
        server.script(turn1_two_tools, make_turn2(passback), make_turn3(passback))
        config = make_config(server.base_url, reasoning_passback=passback)
        tool_record = record_of(await collect(config, [question], server, tools=TOOLS))
        last_request = server.requests[-1]["messages"]

        answer = {"role": "assistant", "content": "Alpha, beta and gamma."}
        if passback:
            answer["reasoning_content"] = "All three found."

        def next_turn(body):
            assert body["messages"][:len(last_request)] == last_request, body["messages"]
            assert body["messages"][len(last_request):] == [answer, follow_up], body["messages"]
            return [chunk(content="Yes."), chunk(finish_reason="stop"), usage_chunk(10, 1)]

        server.script(next_turn)
        events = await collect(config, [question, *tool_record, follow_up], server, tools=TOOLS)
        assert tokens_of(events) == "Yes."
        assert record_of(events) == [], "an answer without tool calls or reasoning has no record"


async def test_answer_without_tools_keeps_its_reasoning(server):
    """
    A model that gets its reasoning passed back gets it back in later turns too, also of answers
    that called no tool; an edit of the text drops it, and models without passback never get it.
    """
    question = {"role": "user", "content": "Think of a number."}
    follow_up = {"role": "user", "content": "Which one?"}

    def thinks(body):
        return [chunk(reasoning="I pick 7319."), chunk(content="Ready."), chunk(finish_reason="stop"),
                usage_chunk(10, 5)]

    for passback in (True, False):
        server.reset()
        server.script(thinks)
        config = make_config(server.base_url, reasoning_passback=passback)
        answer_record = record_of(await collect(config, [question], server, tools=TOOLS))
        if not passback:
            assert answer_record == [], answer_record
            continue
        assert answer_record == [{"role": "assistant", "content": "Ready.", "reasoning_content": "I pick 7319."}]

        def next_turn(body):
            assert body["messages"][1:] == [question, *answer_record, follow_up], body["messages"]
            return [chunk(content="7319."), chunk(finish_reason="stop"), usage_chunk(20, 2)]

        server.script(next_turn)
        assert tokens_of(await collect(config, [question, *answer_record, follow_up], server, tools=TOOLS)) == "7319."
        # Another model without passback gets the text only
        def text_only(body):
            assert body["messages"][2] == {"role": "assistant", "content": "Ready."}, body["messages"]
            return [chunk(content="7319."), chunk(finish_reason="stop"), usage_chunk(20, 2)]

        server.script(text_only)
        other = make_config(server.base_url, reasoning_passback=False)
        await collect(other, [question, *answer_record, follow_up], server, tools=TOOLS)
        # The reasoning led to the old text: an edit leaves no record
        assert with_text(answer_record, "Not ready.") == []


async def test_tool_error_continues(server):
    def turn1(body):
        return [chunk(content="Let me check."),
                chunk(tool_calls=[tool_call_delta(0, id="call_x", name="explode", arguments="{}")]),
                chunk(tool_calls=[tool_call_delta(1, id="call_y", name="nope", arguments="{}")]),
                chunk(tool_calls=[tool_call_delta(2, id="call_z", name="lookup", arguments="{not json")]),
                chunk(finish_reason="tool_calls"), usage_chunk(10, 5)]

    def turn2(body):
        tool_messages = {m["tool_call_id"]: m["content"] for m in body["messages"] if m["role"] == "tool"}
        assert "the database is on fire" in tool_messages["call_x"], tool_messages
        assert "Unknown tool 'nope'" in tool_messages["call_y"], tool_messages
        assert "not valid JSON" in tool_messages["call_z"], tool_messages
        return [chunk(content="It failed."), chunk(finish_reason="stop"), usage_chunk(20, 3)]

    server.script(turn1, turn2)
    config = make_config(server.base_url, reasoning="none")
    events = await collect(config, [{"role": "user", "content": "Try it"}], server, tools=TOOLS)
    results = [s for s in steps_of(events) if s.type == "tool_result"]
    assert len(results) == 3 and all(r.content.startswith("Error:") for r in results), results
    # Text before and after the tool round is kept apart
    assert tokens_of(events) == "Let me check.\n\nIt failed."
    # The record keeps each round's own text and which results were errors
    tool_record = record_of(events)
    assert tool_record[0]["content"] == "Let me check." and tool_record[-1]["content"] == "It failed."
    assert [m.get("_is_error") for m in tool_record if m["role"] == "tool"] == [True, True, True]
    # After the answer's text was edited: the calls and results stay, the new text is its only text
    edited = with_text(tool_record, "It broke.")
    assert [m["content"] for m in edited if m["role"] == "assistant"] == ["", "It broke."], edited
    assert [m for m in edited if m["role"] == "tool"] == [m for m in tool_record if m["role"] == "tool"]


async def test_tool_result_images_follow_in_a_user_message(server):
    fox = {"type": "image_url", "image_url": {"url": "data:image/png;base64,Rk9Y"}}

    async def look() -> ToolText:
        return ToolText("fox-1.png. The image follows.", images=[fox])

    tools = ToolRegistry([*TOOLS, Tool(name="look", description="Look at the fox", func=look,
                                       parameters={"type": "object", "properties": {}})])

    def turn1(body):
        return [chunk(tool_calls=[tool_call_delta(0, id="call_i", name="look", arguments="{}")]),
                chunk(tool_calls=[tool_call_delta(1, id="call_k", name="lookup", arguments='{"key": "k"}')]),
                chunk(finish_reason="tool_calls"), usage_chunk(10, 5)]

    def turn2(body):
        # A tool message only takes text: the image follows both tool results, in a user message
        roles = [m["role"] for m in body["messages"]]
        assert roles == ["system", "user", "assistant", "tool", "tool", "user"], roles
        look_result, lookup_result, images = body["messages"][3:]
        assert look_result == {"role": "tool", "tool_call_id": "call_i", "content": "fox-1.png. The image follows."}
        assert json.loads(lookup_result["content"]) == {"key": "k", "value": "value-of-k"}
        assert images["content"] == [{"type": "text", "text": TOOL_IMAGES_NOTE}, fox], images
        return [chunk(content="A fox."), chunk(finish_reason="stop"), usage_chunk(20, 3)]

    server.script(turn1, turn2)
    config = make_config(server.base_url, reasoning="none")
    events = await collect(config, [{"role": "user", "content": "Look"}], server, tools=tools)
    assert tokens_of(events) == "A fox."
    # The chat's step shows the text, not the image data
    results = {s.callId: s.content for s in steps_of(events) if s.type == "tool_result"}
    assert results["call_i"] == "fox-1.png. The image follows.", results
    # The record holds a note in place of the image: it is not sent again in later turns
    tool_record = record_of(events)
    assert tool_record[1] == {"role": "tool", "tool_call_id": "call_i",
                              "content": f"fox-1.png. The image follows.\n\n{images_note(1)}"}, tool_record[1]
    assert "Rk9Y" not in json.dumps(tool_record)


async def test_step_limit(server):
    def wants_tool(body):
        return [chunk(tool_calls=[tool_call_delta(0, id=f"call_{len(server.requests)}", name="lookup",
                                                  arguments='{"key": "k"}')]),
                chunk(finish_reason="tool_calls"), usage_chunk(10, 5)]

    def last_call(body):
        assert body.get("tool_choice") == "none", body.get("tool_choice")
        assert body["messages"][-1] == {"role": "user", "content": STEP_LIMIT_NOTE}
        return [chunk(content="Answer without more tools."), chunk(finish_reason="stop"), usage_chunk(30, 5)]

    server.script(wants_tool, wants_tool, last_call)
    config = make_config(server.base_url)
    events = await collect(config, [{"role": "user", "content": "Loop"}], server, tools=TOOLS, max_steps=3)
    assert tokens_of(events) == "Answer without more tools."
    assert len(server.requests) == 3
    # The note before the last call is part of what the model was sent, so it is in the record
    tool_record = record_of(events)
    assert [m["role"] for m in tool_record] == ["assistant", "tool", "assistant", "tool", "user", "assistant"]
    assert tool_record[4]["content"] == STEP_LIMIT_NOTE


async def test_request_settings(server):
    def check(body):
        assert body["temperature"] == 0.3 and body["top_p"] == 0.9, body
        assert body["max_tokens"] == 2048 and "max_completion_tokens" not in body, body
        assert body["reasoning_effort"] == "low"
        # extra_body is merged as-is and wins over computed settings
        assert body["provider"] == {"zdr": True} and body["top_p"] == 0.9
        assert "tools" not in body, "supports_tools=False must not send tools"
        return [chunk(content="ok"), chunk(finish_reason="stop"), usage_chunk(1, 1)]

    def defaults(body):
        for key in ("temperature", "top_p", "max_tokens", "max_completion_tokens", "reasoning_effort"):
            assert key not in body, f"{key} sent although unset"
        return [chunk(content="ok"), chunk(finish_reason="stop"), usage_chunk(1, 1)]

    server.script(check, defaults)
    config = make_config(server.base_url, temperature=0.3, top_p=0.5, max_output_tokens=2048,
                         reasoning_effort="low", extra_body={"provider": {"zdr": True}, "top_p": 0.9},
                         supports_tools=False)
    await collect(config, [{"role": "user", "content": "x"}], server, tools=TOOLS)
    await collect(make_config(server.base_url), [{"role": "user", "content": "x"}], server)


async def test_max_completion_tokens_for_openai():
    from backend.llm.openai_chat import max_tokens_param, request_options
    config = make_config(None, max_output_tokens=500)
    assert max_tokens_param(config) == "max_completion_tokens"
    assert request_options(config) == {"max_completion_tokens": 500}
    assert max_tokens_param(make_config("https://api.openai.com/v1")) == "max_completion_tokens"
    assert max_tokens_param(make_config("http://localhost:8080/v1")) == "max_tokens"


async def test_complete(server):
    def answer(body):
        assert body.get("stream") in (None, False) and "tools" not in body
        assert body["messages"][0]["role"] == "system"
        return completion("<think>hmm</think>\nShort Title")

    server.script(answer)
    config = make_config(server.base_url)
    text, usage = await complete(config, [{"role": "user", "content": "x"}], system_prompt="Titles.",
                                 client=create_openai_client(config))
    assert not server.errors, server.errors
    assert text == "Short Title" and usage.input_tokens == 10 and usage.output_tokens == 5


async def test_api_error_yields_usage_then_raises(server):
    def turn1(body):
        return [chunk(tool_calls=[tool_call_delta(0, id="call_1", name="lookup", arguments='{"key": "a"}')]),
                chunk(finish_reason="tool_calls"), usage_chunk(10, 5)]

    server.script(turn1)  # the second request gets a 500
    config = make_config(server.base_url)
    client = create_openai_client(config).with_options(max_retries=0)
    events = []
    try:
        async for event in run_agent(config, [{"role": "user", "content": "x"}], system_prompt="s",
                                     tools=TOOLS, client=client):
            events.append(event)
        raise AssertionError("expected an API error")
    except AssertionError:
        raise
    except Exception as e:
        assert "500" in str(e) or "scripted" in str(e), e
    assert events[-1][0] == "usage" and events[-1][1].input_tokens == 10
    # The tool that ran before the error is on record
    assert [m["role"] for m in record_of(events)] == ["assistant", "tool"], events[-2]
    server.errors.clear()


async def test_record_holds_complete_rounds_only(server):
    call = {"role": "assistant", "content": "", "_anthropic_content": [{"type": "thinking"}], "tool_calls": [
        {"id": "a", "type": "function", "function": {"name": "lookup", "arguments": "{}"}},
        {"id": "b", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}]}
    results = [{"role": "tool", "tool_call_id": "a", "content": "A"}, {"role": "tool", "tool_call_id": "b", "content": "B"}]
    second = {"role": "assistant", "content": "One more.", "tool_calls": [
        {"id": "c", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}]}
    # The run broke off while the second round's tool ran: only the first round, and the text so far
    # (the reasoning of a call that broke off is not passed: run_agent() only has it for a finished one)
    tool_record = record([call, *results, second], "One more.")
    assert [m["role"] for m in tool_record] == ["assistant", "tool", "tool", "assistant"], tool_record
    assert "_anthropic_content" not in tool_record[0] and tool_record[-1]["content"] == "One more."
    # A call without all of its results is no round; without a round there is no record
    assert record([call, results[0]], "") == []
    assert record([], "Just text.") == []
    # Reasoning alone is kept only with a text it led to
    assert record([], "", "Thoughts without an answer.") == []
    assert record([], "Text.", "Thoughts.") == [{"role": "assistant", "content": "Text.", "reasoning_content": "Thoughts."}]
    # Edited: the calls keep their reasoning, the new text has none
    edited = with_text(record([{**call, "reasoning_content": "Two lookups."}, *results], "Done.", "Both found."), "Changed.")
    assert edited[0]["reasoning_content"] == "Two lookups." and edited[-1] == {"role": "assistant", "content": "Changed."}



async def test_cost_reported_by_the_provider(server):
    """A provider that reports what each call cost it (Cortecs: usage.cost, in millionths of a euro)."""
    def calls_a_tool(cost):
        def turn(body):
            return [chunk(tool_calls=[tool_call_delta(0, id="call_r", name="lookup", arguments='{"key": "alpha"}')]),
                    chunk(finish_reason="tool_calls"), usage_chunk(1000, 20, cost=cost)]
        return turn

    def answers(cost):
        def turn(body):
            return [chunk(content="Done."), chunk(finish_reason="stop"), usage_chunk(1200, 10, cost=cost)]
        return turn

    config = make_config(server.base_url, input_price_per_mtok=2.0, output_price_per_mtok=10.0)
    reporting = replace(config, reported_cost_unit=0.000001)
    computed = (2200 * 2.0 + 30 * 10.0) / 1e6
    question = [{"role": "user", "content": "Look up alpha"}]

    # Every call reported its cost: the answer costs what the provider billed, whatever the prices say
    server.script(calls_a_tool(2700), answers(3250))
    usage = (await collect(config, question, server, tools=TOOLS))[-1][1]
    assert (usage.calls, usage.reported_calls, usage.reported_cost) == (2, 2, 5950.0), usage
    assert abs(reporting.cost(usage) - 0.00595) < 1e-12, reporting.cost(usage)
    assert usage.to_api(reporting)["cost"] == 0.00595 and usage.to_api(reporting)["currency"] == "EUR"
    assert abs(config.cost(usage) - computed) < 1e-12, "a provider without a unit: computed from the prices"
    assert abs(replace(reporting, input_price_per_mtok=None).cost(usage) - 0.00595) < 1e-12, "no prices needed"
    # Adding an empty record (no calls) changes nothing
    total = Usage()
    total.add(Usage())
    total.add(usage)
    assert abs(reporting.cost(total) - 0.00595) < 1e-12

    # One call without a cost: the whole answer is computed from the prices
    server.script(calls_a_tool(2700), answers(None))
    usage = (await collect(config, question, server, tools=TOOLS))[-1][1]
    assert (usage.calls, usage.reported_calls) == (2, 1), usage
    assert abs(reporting.cost(usage) - computed) < 1e-12, reporting.cost(usage)
    # Nothing to go on: no cost
    assert replace(reporting, input_price_per_mtok=None).cost(usage) is None
    assert not server.errors, server.errors


async def test_cost_counts_cache_reads():
    config = make_config("http://unused", input_price_per_mtok=0.182, output_price_per_mtok=0.547)
    usage = Usage(input_tokens=140_000, output_tokens=2_000, cached_input_tokens=135_000)
    full = (140_000 * 0.182 + 2_000 * 0.547) / 1e6
    # No cached price: every input token at the input price (providers without a cache discount)
    assert abs(config.cost(usage) - full) < 1e-12, config.cost(usage)
    # A cached price: the cache hits at that price, the rest of the input at the input price
    cached = replace(config, cached_input_price_per_mtok=0.005)
    expected = (5_000 * 0.182 + 135_000 * 0.005 + 2_000 * 0.547) / 1e6
    assert abs(cached.cost(usage) - expected) < 1e-12, cached.cost(usage)
    assert usage.to_api(cached)["cost"] == round(expected, 6)
    # No cache hits reported, a free cache, more hits reported than input: never below zero input
    assert abs(cached.cost(Usage(input_tokens=1000, output_tokens=10)) - (1000 * 0.182 + 10 * 0.547) / 1e6) < 1e-12
    free = replace(config, cached_input_price_per_mtok=0.0)
    assert abs(free.cost(usage) - (5_000 * 0.182 + 2_000 * 0.547) / 1e6) < 1e-12
    assert abs(cached.cost(Usage(input_tokens=100, output_tokens=0, cached_input_tokens=150)) - 100 * 0.005 / 1e6) < 1e-15
    # Without an input or output price there is no cost, cached price or not
    assert replace(cached, output_price_per_mtok=None).cost(usage) is None


TESTS = [
    test_three_step_chain_with_passback,
    test_three_step_chain_without_passback,
    test_next_turn_starts_with_the_last_request,
    test_answer_without_tools_keeps_its_reasoning,
    test_tool_error_continues,
    test_tool_result_images_follow_in_a_user_message,
    test_step_limit,
    test_request_settings,
    test_max_completion_tokens_for_openai,
    test_complete,
    test_api_error_yields_usage_then_raises,
    test_record_holds_complete_rounds_only,
    test_cost_counts_cache_reads,
    test_cost_reported_by_the_provider,
]


async def main() -> int:
    failures = 0
    with FakeOpenAIServer() as server:
        for test in TESTS:
            server.reset()
            try:
                if "server" in test.__code__.co_varnames[:test.__code__.co_argcount]:
                    await test(server)
                else:
                    await test()
                print(f"PASS  {test.__name__}")
            except Exception:
                failures += 1
                print(f"FAIL  {test.__name__}")
                traceback.print_exc()
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
