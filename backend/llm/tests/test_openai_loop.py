"""
Offline tests of the agent loop on the OpenAI-compatible path, against a fake server.

    python -m backend.llm.tests.test_openai_loop

Covers: tool calls assembled from streamed fragments (two in parallel),
reasoning from reasoning_content, reasoning and <think> tags, reasoning
passback on and off, Thinking steps (start, deltas, completion with the same
id), callId linking, tool errors, the step limit, request settings and
extra_body, models without tools, usage summing, complete(), the images of
a tool result, which follow the tool messages in a user message, and the tool
record of an answer (tool_record.py): what it holds, and that the next turn's
request starts with the last one word for word when the record goes back.
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
from backend.llm.types import KIND_OPENAI_COMPATIBLE, ModelConfig


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
    assert api["currency"] == "EUR" and abs(api["cost"] - (450 * 2 + 45 * 10) / 1e6) < 1e-9, api

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
    assert tool_record[-1] == {"role": "assistant", "content": "Alpha, beta and gamma."}


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

        def next_turn(body):
            assert body["messages"][:len(last_request)] == last_request, body["messages"]
            assert body["messages"][len(last_request):] == [
                {"role": "assistant", "content": "Alpha, beta and gamma."}, follow_up], body["messages"]
            return [chunk(content="Yes."), chunk(finish_reason="stop"), usage_chunk(10, 1)]

        server.script(next_turn)
        events = await collect(config, [question, *tool_record, follow_up], server, tools=TOOLS)
        assert tokens_of(events) == "Yes."
        assert record_of(events) == [], "an answer without tool calls has no record"


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
    tool_record = record([call, *results, second], "One more.")
    assert [m["role"] for m in tool_record] == ["assistant", "tool", "tool", "assistant"], tool_record
    assert "_anthropic_content" not in tool_record[0] and tool_record[-1]["content"] == "One more."
    # A call without all of its results is no round; without a round there is no record
    assert record([call, results[0]], "") == []
    assert record([], "Just text.") == []


TESTS = [
    test_three_step_chain_with_passback,
    test_three_step_chain_without_passback,
    test_next_turn_starts_with_the_last_request,
    test_tool_error_continues,
    test_tool_result_images_follow_in_a_user_message,
    test_step_limit,
    test_request_settings,
    test_max_completion_tokens_for_openai,
    test_complete,
    test_api_error_yields_usage_then_raises,
    test_record_holds_complete_rounds_only,
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
