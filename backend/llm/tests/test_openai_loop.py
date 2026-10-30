"""
Offline tests of the agent loop on the OpenAI-compatible path, against a fake server.

    python -m backend.llm.tests.test_openai_loop

Covers: tool calls assembled from streamed fragments (two in parallel),
reasoning from reasoning_content, reasoning and <think> tags, reasoning
passback on and off, Thinking steps (start, deltas, completion with the same
id), callId linking, tool errors, the step limit, request settings and
extra_body, models without tools, usage summing, and complete().
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
from backend.llm.tools import Tool, ToolRegistry
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


async def test_three_step_chain_without_passback(server):
    server.script(turn1_two_tools, make_turn2(False), make_turn3(False))
    config = make_config(server.base_url, reasoning_passback=False)
    events = await collect(config, [{"role": "user", "content": "Find alpha, beta, gamma"}], server, tools=TOOLS)
    assert tokens_of(events) == "Alpha, beta and gamma."


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
    server.errors.clear()


TESTS = [
    test_three_step_chain_with_passback,
    test_three_step_chain_without_passback,
    test_tool_error_continues,
    test_step_limit,
    test_request_settings,
    test_max_completion_tokens_for_openai,
    test_complete,
    test_api_error_yields_usage_then_raises,
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
