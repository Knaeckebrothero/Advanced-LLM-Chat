"""
Offline tests of the agent loop on the Anthropic path, with a mock HTTP transport.

    python -m backend.llm.tests.test_anthropic_loop

Covers the message conversion (system prompt, image data URLs, tool_use and
tool_result blocks, history that starts with an assistant message), the request
settings (adaptive thinking with summarized display, output_config.effort, no
temperature/top_p, max_tokens default, no forced tool_choice), thinking blocks
with signatures passed back unchanged, all tool results in one user message,
the step limit, refusals, usage with cache reads, and complete().
"""
import asyncio
import json
import sys
import traceback
from dataclasses import replace

import anthropic
import httpx2

from backend.llm.agent_loop import REFUSAL_NOTE, STEP_LIMIT_NOTE, complete, run_agent
from backend.llm.anthropic_chat import DEFAULT_MAX_TOKENS_STREAMING, HISTORY_START_PLACEHOLDER, to_anthropic_messages
from backend.llm.tools import Tool, ToolRegistry
from backend.llm.types import KIND_ANTHROPIC, ModelConfig

PNG_DATA = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGD4DwABBAEAwS2OUAAAAABJRU5ErkJggg=="


def make_config(**overrides) -> ModelConfig:
    config = ModelConfig(
        id=3, display_name="Claude (test)", model_id="claude-opus-5-5", provider_id=2,
        provider_name="Anthropic", kind=KIND_ANTHROPIC, base_url=None, api_key="test-key",
        supports_tools=True, supports_vision=True, reasoning="always", reasoning_effort="high",
        temperature=0.2, top_p=0.9,
    )
    return replace(config, **overrides)


async def lookup(key: str) -> dict:
    return {"key": key, "value": key.upper()}


async def broken() -> str:
    raise ValueError("no connection")


TOOLS = ToolRegistry([
    Tool(name="lookup", description="Look up a key",
         parameters={"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
         func=lookup),
    Tool(name="broken", description="Always fails", parameters={"type": "object", "properties": {}}, func=broken),
])


# ---------------------------------------------------------------------------
# Mock Messages API
# ---------------------------------------------------------------------------

def sse(events: list[dict]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def message_events(blocks: list[dict], stop_reason: str, input_tokens=100, output_tokens=50,
                   cache_read=0, thinking_tokens=None) -> list[dict]:
    """Stream events for a response made of these blocks (thinking, text, tool_use)."""
    events = [{"type": "message_start", "message": {
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": [], "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": 1,
                  "cache_read_input_tokens": cache_read, "cache_creation_input_tokens": 0}}}]
    for index, block in enumerate(blocks):
        if block["type"] == "thinking":
            events.append({"type": "content_block_start", "index": index,
                           "content_block": {"type": "thinking", "thinking": "", "signature": ""}})
            for piece in block["pieces"]:
                events.append({"type": "content_block_delta", "index": index,
                               "delta": {"type": "thinking_delta", "thinking": piece}})
            events.append({"type": "content_block_delta", "index": index,
                           "delta": {"type": "signature_delta", "signature": block["signature"]}})
        elif block["type"] == "text":
            events.append({"type": "content_block_start", "index": index,
                           "content_block": {"type": "text", "text": ""}})
            for piece in block["pieces"]:
                events.append({"type": "content_block_delta", "index": index,
                               "delta": {"type": "text_delta", "text": piece}})
        elif block["type"] == "tool_use":
            events.append({"type": "content_block_start", "index": index,
                           "content_block": {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}})
            text = json.dumps(block["input"])
            for start in range(0, len(text), 7):
                events.append({"type": "content_block_delta", "index": index,
                               "delta": {"type": "input_json_delta", "partial_json": text[start:start + 7]}})
        events.append({"type": "content_block_stop", "index": index})
    usage = {"output_tokens": output_tokens}
    if thinking_tokens is not None:
        usage["output_tokens_details"] = {"thinking_tokens": thinking_tokens}
    events.append({"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                   "usage": usage})
    events.append({"type": "message_stop"})
    return events


class MockMessagesAPI:
    """Answers POST /v1/messages from a script and records the request bodies and headers."""

    def __init__(self, *responders):
        self.responders = list(responders)
        self.requests: list[dict] = []
        self.headers: list[dict] = []
        self.errors: list[str] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        self.headers.append(dict(request.headers))
        if not self.responders:
            self.errors.append("unexpected request")
            return httpx2.Response(500, json={"type": "error", "error": {"type": "api_error", "message": "no script"}})
        try:
            result = self.responders.pop(0)(body)
        except AssertionError as e:
            self.errors.append(str(e))
            return httpx2.Response(400, json={"type": "error", "error": {"type": "invalid_request_error", "message": str(e)}})
        if isinstance(result, dict):
            return httpx2.Response(200, json=result)
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=sse(result))

    def client(self) -> anthropic.AsyncAnthropic:
        return anthropic.AsyncAnthropic(
            api_key="test-key", max_retries=0,
            http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(self.handler)),
        )


async def collect(config, messages, api, **kwargs):
    events = []
    async for event in run_agent(config, messages, system_prompt="You are a test.", client=api.client(), **kwargs):
        events.append(event)
    assert not api.errors, api.errors
    return events


def tokens_of(events):
    return "".join(data for kind, data in events if kind == "token")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_conversion():
    history = [
        {"role": "system", "content": "Extra system note."},
        {"role": "assistant", "content": "Hello! How can I help?"},
        {"role": "user", "content": [
            {"type": "text", "text": "What is in this image?"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG_DATA}"}},
            {"type": "image_url", "image_url": {"url": "https://example.com/cat.jpg"}},
        ]},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "toolu_1", "type": "function", "function": {"name": "lookup", "arguments": '{"key": "a"}'}}]},
        {"role": "tool", "tool_call_id": "toolu_1", "content": "result a"},
        {"role": "tool", "tool_call_id": "toolu_2", "content": "Error: boom", "_is_error": True},
        {"role": "user", "content": "And now?"},
    ]
    system, messages = to_anthropic_messages(history, "Base prompt.")
    assert system == "Base prompt.\n\nExtra system note."
    assert messages[0] == {"role": "user", "content": [{"type": "text", "text": HISTORY_START_PLACEHOLDER}]}
    assert messages[1] == {"role": "assistant", "content": [{"type": "text", "text": "Hello! How can I help?"}]}
    image, url_image = messages[2]["content"][1], messages[2]["content"][2]
    assert image == {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": PNG_DATA}}
    assert url_image == {"type": "image", "source": {"type": "url", "url": "https://example.com/cat.jpg"}}
    assert messages[3] == {"role": "assistant", "content": [
        {"type": "tool_use", "id": "toolu_1", "name": "lookup", "input": {"key": "a"}}]}
    # Both tool results and the next user text land in one user message, results first
    assert messages[4]["role"] == "user" and len(messages) == 5
    assert [b["type"] for b in messages[4]["content"]] == ["tool_result", "tool_result", "text"]
    assert messages[4]["content"][1]["is_error"] is True and "is_error" not in messages[4]["content"][0]


async def test_tool_loop_with_thinking_passback():
    def turn1(body):
        assert body["system"] == "You are a test."
        assert body["thinking"] == {"type": "adaptive", "display": "summarized"}, body.get("thinking")
        assert body["output_config"] == {"effort": "high"}
        assert body["max_tokens"] == DEFAULT_MAX_TOKENS_STREAMING
        assert "temperature" not in body and "top_p" not in body, "sampling parameters must not be sent"
        assert "tool_choice" not in body
        assert body["cache_control"] == {"type": "ephemeral"}
        assert [t["name"] for t in body["tools"]] == ["lookup", "broken"]
        assert body["tools"][0]["input_schema"]["required"] == ["key"]
        return message_events([
            {"type": "thinking", "pieces": ["I should ", "look up a and b."], "signature": "sig-1"},
            {"type": "tool_use", "id": "toolu_a", "name": "lookup", "input": {"key": "a"}},
            {"type": "tool_use", "id": "toolu_b", "name": "broken", "input": {}},
        ], "tool_use", input_tokens=100, output_tokens=40, cache_read=0, thinking_tokens=12)

    def turn2(body):
        assistant = body["messages"][1]
        assert assistant["role"] == "assistant"
        # The thinking block comes back unchanged, with its signature, before the tool_use blocks
        assert assistant["content"][0] == {"type": "thinking", "thinking": "I should look up a and b.", "signature": "sig-1"}
        assert [b["type"] for b in assistant["content"]] == ["thinking", "tool_use", "tool_use"]
        results = body["messages"][2]
        assert results["role"] == "user" and [b["tool_use_id"] for b in results["content"]] == ["toolu_a", "toolu_b"]
        assert json.loads(results["content"][0]["content"]) == {"key": "a", "value": "A"}
        assert results["content"][1]["is_error"] is True and "no connection" in results["content"][1]["content"]
        return message_events([
            {"type": "thinking", "pieces": ["b failed; answer with a."], "signature": "sig-2"},
            {"type": "text", "pieces": ["The value ", "is A."]},
        ], "end_turn", input_tokens=40, output_tokens=20, cache_read=150)

    api = MockMessagesAPI(turn1, turn2)
    events = await collect(make_config(), [{"role": "user", "content": "Look up a and b"}], api, tools=TOOLS)

    assert tokens_of(events) == "The value is A."
    steps = [data for kind, data in events if kind == "step"]
    thinking = [s for s in steps if s.type == "thought"]
    assert [s.content for s in thinking] == ["", "I should look up a and b.", "", "b failed; answer with a."]
    assert thinking[0].id == thinking[1].id
    calls = [s for s in steps if s.type == "tool_call"]
    results = [s for s in steps if s.type == "tool_result"]
    assert [c.callId for c in calls] == ["toolu_a", "toolu_b"] and sorted(r.callId for r in results) == ["toolu_a", "toolu_b"]
    usage = events[-1][1]
    assert events[-1][0] == "usage"
    # input = uncached input + cache reads; reasoning from output_tokens_details
    assert (usage.input_tokens, usage.output_tokens, usage.cached_input_tokens, usage.reasoning_tokens) == (290, 60, 150, 12), usage
    version = api.headers[0].get("anthropic-version")
    print(f"      (anthropic-version sent: {version})")


async def test_effort_mapping_and_no_thinking():
    def check(body):
        assert body["output_config"] == {"effort": "low"}, body.get("output_config")
        assert "thinking" not in body, "reasoning='none' must not send thinking"
        assert body["max_tokens"] == 4096
        assert "tools" not in body
        return message_events([{"type": "text", "pieces": ["ok"]}], "end_turn")

    api = MockMessagesAPI(check)
    config = make_config(reasoning="none", reasoning_effort="minimal", max_output_tokens=4096, supports_tools=False)
    events = await collect(config, [{"role": "user", "content": "x"}], api, tools=TOOLS)
    assert tokens_of(events) == "ok"


async def test_step_limit_uses_tool_choice_none():
    def wants_tool(body):
        return message_events([{"type": "tool_use", "id": "toolu_1", "name": "lookup", "input": {"key": "a"}}], "tool_use")

    def last_call(body):
        assert body["tool_choice"] == {"type": "none"}
        assert "tools" in body, "tools stay declared (the history contains tool_use blocks)"
        last = body["messages"][-1]
        assert last["role"] == "user" and last["content"][-1] == {"type": "text", "text": STEP_LIMIT_NOTE}
        return message_events([{"type": "text", "pieces": ["Done."]}], "end_turn")

    api = MockMessagesAPI(wants_tool, last_call)
    events = await collect(make_config(), [{"role": "user", "content": "x"}], api, tools=TOOLS, max_steps=2)
    assert tokens_of(events) == "Done."


async def test_refusal():
    api = MockMessagesAPI(lambda body: message_events([], "refusal"))
    events = await collect(make_config(), [{"role": "user", "content": "x"}], api, tools=TOOLS)
    assert tokens_of(events) == REFUSAL_NOTE


async def test_complete():
    def answer(body):
        assert "thinking" not in body and "tools" not in body and "temperature" not in body
        assert body["system"] == "Titles." and body["max_tokens"] == 16000
        return {"id": "msg_c", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
                "content": [{"type": "thinking", "thinking": "", "signature": "s"},
                            {"type": "text", "text": "  A Short Title \n"}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 12, "output_tokens": 30}}

    api = MockMessagesAPI(answer)
    text, usage = await complete(make_config(), [{"role": "user", "content": "x"}], system_prompt="Titles.",
                                 client=api.client())
    assert not api.errors, api.errors
    assert text == "A Short Title" and usage.input_tokens == 12 and usage.output_tokens == 30


TESTS = [
    test_conversion,
    test_tool_loop_with_thinking_passback,
    test_effort_mapping_and_no_thinking,
    test_step_limit_uses_tool_choice_none,
    test_refusal,
    test_complete,
]


async def main() -> int:
    failures = 0
    print(f"anthropic SDK {anthropic.__version__}")
    for test in TESTS:
        try:
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
