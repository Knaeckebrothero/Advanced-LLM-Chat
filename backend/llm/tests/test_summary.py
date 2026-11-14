"""
Offline test of the summary of a conversation's oldest messages (backend/services/conversation_summary.py).

    python -m backend.llm.tests.test_summary

Against the fake OpenAI server: the oldest messages are summarized only once
the history passes the trigger, down to the share kept word for word (whole
exchanges); the
messages are folded in chunks sized for the model's window, each pass merging
the summary of the previous one (and the stored summary); a reply without the
sections or cut off at the output limit is retried, and after the last attempt
the summary fails with the usage of every attempt; and the history starts with
the stored summary instead of the messages it covers. Through the message
endpoints (on a fake database): stream-generate summarizes before it answers
once the history passes the trigger, and POST /api/message/summarize
summarizes every message on request (409, 422 and 502 included).
"""
import asyncio
import json
import sys
import time
import traceback
from contextlib import contextmanager
from dataclasses import replace

import httpx

from backend.llm.tests.fake_openai_server import (
    FakeOpenAIServer, chunk, completion, tool_call_delta, usage_chunk,
)
from backend.llm.prompts import IDENTITY_PROMPT, INSTRUCTIONS_HEADING, hide_prompt
from backend.llm.tests.test_history import LONG_ROWS, FakeDB, assistant, system, user
from backend.llm.tools import Tool, ToolRegistry
from backend.llm.types import KIND_OPENAI_COMPATIBLE, ModelConfig
from backend.services import conversation_summary
from backend.services.conversation_history import (
    CONTINUE_NOTE,
    SUMMARY_CONTINUE,
    SUMMARY_LEAD_IN,
    TOOL_RECORD_KEY,
    ConversationHistoryBuilder,
    estimate_tokens,
)
from backend.services.conversation_summary import (
    SUMMARY_KEEP,
    SUMMARY_PROMPT,
    SUMMARY_TRIGGER,
    TOOL_RESULT_CHARS,
    SummaryFailed,
    messages_to_summarize,
    plan_chunks,
    summarize,
    summary_target_tokens,
    transcript_parts,
)

# No waiting between the attempts of a pass
conversation_summary.BACKOFF_SECONDS = (0.0, 0.0)

GOOD_SUMMARY = """## Topic and Goal
- The user asked numbered questions.

## User Requests (verbatim)
- (none)

## About the User
- (none)

## Facts and Decisions
- Every question got an answer.

## Open Threads
- (none)"""


def make_config(base_url: str, **overrides) -> ModelConfig:
    config = ModelConfig(
        id=7, display_name="Fake", model_id="fake-model", provider_id=1, provider_name="Fake",
        kind=KIND_OPENAI_COMPATIBLE, base_url=base_url, api_key="test",
    )
    return replace(config, **overrides)


def truncated(content: str) -> dict:
    response = completion(content)
    response["choices"][0]["finish_reason"] = "length"
    return response


async def entries_of(rows):
    entries, _ = await ConversationHistoryBuilder(FakeDB(rows)).build_entries("c")
    return entries


async def test_summarizes_only_past_the_trigger(server):
    entries = await entries_of(LONG_ROWS)  # 60 messages of about 100 tokens
    total = sum(estimate_tokens(m["content"]) for _, m in entries)
    assert messages_to_summarize(entries, None, int(total / SUMMARY_TRIGGER) + 10) == 0

    budget = 4000
    count = messages_to_summarize(entries, None, budget)
    kept = sum(estimate_tokens(m["content"]) for _, m in entries[count:])
    assert kept <= budget * SUMMARY_KEEP - summary_target_tokens(budget), kept
    # Whole exchanges: the kept messages start with a question, and one more exchange would not have fit
    assert entries[count][1]["role"] == "user" and entries[count - 1][1]["role"] == "assistant", count
    exchange = sum(estimate_tokens(m["content"]) for _, m in entries[count - 2:count])
    assert kept + exchange > budget * SUMMARY_KEEP - summary_target_tokens(budget)
    # A stored summary counts toward the history
    assert messages_to_summarize(entries[-30:], None, 4000) == 0
    assert messages_to_summarize(entries[-30:], {"content": "x" * 2400 * 3}, 4000) > 0


async def test_latest_question_is_never_summarized(server):
    rows = LONG_ROWS[:-1]  # ends with an unanswered question
    entries = await entries_of(rows)
    count = messages_to_summarize(entries, None, 600)
    assert count == len(entries) - 1 and entries[count][1]["content"].startswith("Question 29"), count


async def test_fold_in_chunks_merges_prior_summary(server):
    requests = []

    def answer(body):
        requests.append(body)
        return completion(GOOD_SUMMARY + f"\n- pass {len(requests)}", prompt_tokens=100, completion_tokens=50)

    entries = await entries_of(LONG_ROWS[:40])
    # A small window: the 40 messages (about 4,000 tokens) need several passes
    config = make_config(server.base_url, context_window=8000, max_output_tokens=1000)
    server.script(*[answer] * 10)
    summary, usage = await summarize(config, entries, "## Topic and Goal\n- An older summary.", 9000)
    assert not server.errors, server.errors
    assert len(requests) >= 2, len(requests)
    assert summary.endswith(f"- pass {len(requests)}"), summary
    assert usage.input_tokens == 100 * len(requests) and usage.output_tokens == 50 * len(requests)

    first, second = (r["messages"] for r in requests[:2])
    assert first[0] == {"role": "system", "content": SUMMARY_PROMPT}
    assert "<prior-summary>\n## Topic and Goal\n- An older summary.\n</prior-summary>" in first[1]["content"]
    assert "[User]: Question 00" in first[1]["content"] and "[Assistant]: Answer 00" in first[1]["content"]
    # The second pass merges the first pass's summary and goes on where the first chunk ended
    assert "- pass 1\n</prior-summary>" in second[1]["content"]
    assert "Question 00" not in second[1]["content"]
    assert "[Assistant]: Answer 19" in requests[-1]["messages"][1]["content"]


async def test_bad_reply_is_retried(server):
    server.script(
        lambda body: completion("Sure! Question 1 was about the weather."),  # no sections
        lambda body: truncated(GOOD_SUMMARY[:80]),                          # cut off
        lambda body: completion("```markdown\n" + GOOD_SUMMARY + "\n```"),   # fenced, otherwise fine
    )
    entries = await entries_of(LONG_ROWS[:20])
    summary, usage = await summarize(make_config(server.base_url), entries, None, 9000)
    assert not server.errors, server.errors
    assert summary == GOOD_SUMMARY, summary
    # The rejected first reply counts; the cut-off one raised before its usage was read
    assert usage.input_tokens == 20, usage


async def test_failure_keeps_usage(server):
    server.script(*[lambda body: completion("I can't help with that.")] * 3)
    entries = await entries_of(LONG_ROWS[:20])
    try:
        await summarize(make_config(server.base_url), entries, None, 9000)
        raise AssertionError("expected SummaryFailed")
    except SummaryFailed as e:
        assert e.reason == "no_sections", e.reason
        assert e.usage.input_tokens == 30 and e.usage.output_tokens == 15, e.usage
    assert len(server.requests) == 3 and not server.errors


async def test_summary_must_be_smaller(server):
    # Too short to ask the model at all (only happens on request, POST /api/message/summarize)
    entries = await entries_of([user(1000, 1, "Hi there"), assistant(1500, 1, "Hello!")])
    try:
        await summarize(make_config(server.base_url), entries, None, 9000)
        raise AssertionError("expected SummaryFailed")
    except SummaryFailed as e:
        assert e.reason == "too_short", e.reason
    assert not server.requests, len(server.requests)

    # Long enough to try, but the summary comes out longer than the messages
    facts = "\n".join(f"- Fact number {i} came up." for i in range(80))
    server.script(lambda body: completion(GOOD_SUMMARY + "\n" + facts))
    entries = await entries_of([user(1000, 1, "Tell me more. " * 120), assistant(1500, 1, "Here is more.")])
    try:
        await summarize(make_config(server.base_url), entries, None, 9000)
        raise AssertionError("expected SummaryFailed")
    except SummaryFailed as e:
        assert e.reason == "not_smaller", e.reason
    assert len(server.requests) == 1, len(server.requests)


async def test_on_request_scales_the_length(server):
    # Before an answer, the length follows the budget; on request, also what the summary covers
    assert summary_target_tokens(90000) == 4000
    assert summary_target_tokens(90000, covered_tokens=3000) == 1000
    assert summary_target_tokens(90000, covered_tokens=600) == 250
    assert summary_target_tokens(2000, covered_tokens=60000) == 500

    server.script(lambda body: completion(GOOD_SUMMARY))
    entries = await entries_of([user(1000, 1, "Tell me more. " * 120), assistant(1500, 1, "Here is more. " * 120)])
    covered = sum(estimate_tokens(message["content"]) for _, message in entries)
    summary, _ = await summarize(make_config(server.base_url, context_window=128000), entries, None, 90000,
                                 on_request=True)
    assert summary == GOOD_SUMMARY
    request = server.requests[0]["messages"][-1]["content"]
    assert f"under about {int(covered / 3)} tokens" in request, request[-120:]

    # Longer than twice the asked length is fine on request, as long as it is shorter than the messages
    longer = GOOD_SUMMARY + "\n" + "\n".join(f"- Fact number {i} came up." for i in range(90))
    assert 2 * int(covered / 3) < estimate_tokens(longer) < covered
    server.script(lambda body: completion(longer))
    summary, _ = await summarize(make_config(server.base_url, context_window=128000), entries, None, 90000,
                                 on_request=True)
    assert summary == longer


async def test_oversized_message_is_split(server):
    chunks = plan_chunks(["[User]: " + "x" * 9000, "[Assistant]: ok"], 1000)
    assert len(chunks) == 4, [len(c) for c in chunks]
    assert chunks[0].startswith("[part 1/4] [User]: xxx") and chunks[-1].endswith("[Assistant]: ok")
    assert all(estimate_tokens(c) <= 1000 for c in chunks)


class SummaryDB(FakeDB):
    def __init__(self, rows, summary):
        super().__init__(rows)
        self.summary = summary

    def get_conversation_summary(self, conversation_id):
        return self.summary


async def test_history_starts_with_summary(server):
    summary = {"covers_until": LONG_ROWS[39]["id"], "message_count": 40, "content": GOOD_SUMMARY}
    builder = ConversationHistoryBuilder(SummaryDB(LONG_ROWS, summary))
    messages, _ = await builder.build_history("c", token_budget=100000)
    assert len(messages) == 21, len(messages)
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == f"{SUMMARY_LEAD_IN}\n\n{GOOD_SUMMARY}\n\n{SUMMARY_CONTINUE}"
    assert messages[1]["content"].startswith("Question 20"), messages[1]
    # A small budget leaves out messages, never the summary
    messages, _ = await builder.build_history("c", token_budget=estimate_tokens(messages[0]["content"]) + 500)
    assert messages[0]["content"].startswith(SUMMARY_LEAD_IN) and len(messages) == 6, len(messages)
    # Regenerating a message the summary covers: the messages, not the summary
    messages, _ = await builder.build_history("c", before_message=LONG_ROWS[11])
    assert len(messages) == 11 and messages[0]["content"].startswith("Question 00"), messages[0]


class EndpointDB(FakeDB):
    """What the message endpoints use: conversations, the stored summary and the answers they save."""

    def __init__(self, rows, summary=None):
        super().__init__(rows)
        self.summary = summary
        self.answers = []
        self.conversation = {}  # What update_conversation() set

    def get_conversation_by_id(self, conversation_id, user_id=None):
        return {"id": conversation_id, "persona_id": None, **self.conversation}

    def update_conversation(self, conversation_id, user_id=None, **values):
        self.conversation.update(values)
        return self.get_conversation_by_id(conversation_id)

    def get_conversation_summary(self, conversation_id):
        return self.summary

    def save_conversation_summary(self, conversation_id, covers_until, message_count, content, model_name=None):
        self.summary = {"conversation_id": conversation_id, "covers_until": covers_until,
                        "message_count": message_count, "content": content, "model_name": model_name,
                        "created_at": 1}
        return self.summary

    def create_agent_message(self, **message):
        self.answers.append(message)

    # The memory a conversation's prompt shows (backend/services/memory_snapshot.py)
    def get_memory_snapshot(self, conversation_id):
        return getattr(self, "memory_snapshot", None)

    def save_memory_snapshot(self, conversation_id, vault, family_mode, content, day):
        self.memory_snapshot = {"conversation_id": conversation_id, "vault": vault, "family_mode": family_mode,
                                "content": content, "day": day}

    def last_answer_time(self, conversation_id):
        return max((row["id"] for row in self.rows if row.get("type") == "agent"), default=None)


@contextmanager
def message_api(fake_db, config):
    """
    An httpx client for the message endpoints (backend/api/messages.py) on fake_db, answered by config
    as a signed-in user; no rate limit.
    """
    from fastapi import FastAPI
    from backend.api import messages
    from backend.services import memory_snapshot
    from backend.security.auth import get_current_user
    from backend.security.guest_limits import guest_write, rate_limit_guest

    app = FastAPI()
    app.include_router(messages.router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": 1, "email": "a@example.com", "is_guest": False}
    app.dependency_overrides[rate_limit_guest] = app.dependency_overrides[guest_write] = lambda: None
    saved = messages.db, messages._resolve_model, messages.verify_conversation_ownership, memory_snapshot.db
    messages.db = memory_snapshot.db = fake_db
    messages._resolve_model = lambda user, conversation_id, model_id=None: config
    messages.verify_conversation_ownership = lambda conversation_id, user_id: True
    try:
        yield httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    finally:
        messages.db, messages._resolve_model, messages.verify_conversation_ownership, memory_snapshot.db = saved


def summary_or_answer(body):
    """A summary for a summary call (not streamed), a short answer for the agent (streamed)."""
    if body.get("stream"):
        return [chunk(content="The answer."), chunk(finish_reason="stop"), usage_chunk(100, 3)]
    return completion(GOOD_SUMMARY, prompt_tokens=50, completion_tokens=40)


def sse_events(text):
    """The (event, data) pairs of an SSE body."""
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        lines = block.strip().splitlines()
        event = next((line[6:].strip() for line in lines if line.startswith("event:")), None)
        data = "\n".join(line[5:].lstrip() for line in lines if line.startswith("data:"))
        if event:
            events.append((event, data))
    return events


async def test_stream_generate_summarizes_past_the_trigger(server):
    # 60 messages of about 100 tokens and a question; a window whose budget they pass 80% of
    rows = LONG_ROWS + [user(9000_000, 9000, "And now?")]
    fake_db = EndpointDB(rows)
    config = make_config(server.base_url, context_window=10000, supports_tools=False)
    server.script(*[summary_or_answer] * 5)
    with message_api(fake_db, config) as client:
        response = await client.post("/api/message/stream-generate", json={"conversationId": "c"})
    assert response.status_code == 200, response.text
    events = sse_events(response.text)
    names = [name for name, _ in events]
    assert names[0] == "message_start" and names[-1] == "done", names
    assert "error" not in names, events

    # The step shows the summary being written, then done; the summary event carries it
    steps = [json.loads(data) for name, data in events if name == "step"]
    assert [step["title"].split(" ")[0] for step in steps] == ["Summarizing", "Summarized"], steps
    summary = json.loads(next(data for name, data in events if name == "summary"))
    stored = fake_db.summary
    assert summary["coversUntil"] == stored["covers_until"] and summary["content"] == GOOD_SUMMARY, summary
    folded = [row for row in rows if row["id"] <= stored["covers_until"]]
    assert stored["message_count"] == len(folded) and 0 < len(folded) < len(rows), stored
    assert folded[-1]["roleName"] == "Assistant", "whole exchanges are folded"

    # The answer starts from the summary, then the messages after it
    answer_request = next(request for request in server.requests if request.get("stream"))
    history = [m for m in answer_request["messages"] if m["role"] != "system"]
    assert history[0]["content"].startswith(SUMMARY_LEAD_IN), history[0]
    assert len(history) == 1 + len(rows) - len(folded), len(history)
    # The saved answer counts the summary's model calls too
    summary_calls = sum(1 for request in server.requests if not request.get("stream"))
    done = json.loads(events[-1][1])
    assert done["usage"]["inputTokens"] == 100 + 50 * summary_calls, done["usage"]
    assert fake_db.answers[0]["content"] == "The answer." and fake_db.answers[0]["status"] == "complete"


async def test_summarize_on_request(server):
    # 10 messages of about 100 tokens: far below the trigger, summarized only on request
    rows = LONG_ROWS[:10]
    fake_db = EndpointDB(rows)
    config = make_config(server.base_url, context_window=128000, supports_tools=False)
    with message_api(fake_db, config) as client:
        server.script(summary_or_answer)
        response = await client.post("/api/message/summarize", json={"conversationId": "c"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["coversUntil"] == rows[-1]["id"] and body["messageCount"] == 10, body
        assert body["content"] == GOOD_SUMMARY and body["modelName"] == "Fake", body
        covered = sum(estimate_tokens(message["content"]) for _, message in await entries_of(rows))
        assert f"under about {int(covered / 3)} tokens" in server.requests[0]["messages"][-1]["content"]

        # Nothing after the summary
        response = await client.post("/api/message/summarize", json={"conversationId": "c"})
        assert response.status_code == 409, response.text
        assert len(server.requests) == 1

        # New messages are merged into the stored summary (questions 05 to 07)
        fake_db.rows = LONG_ROWS[:16]
        server.script(summary_or_answer)
        response = await client.post("/api/message/summarize", json={"conversationId": "c"})
        assert response.status_code == 200, response.text
        assert response.json()["messageCount"] == 16 and response.json()["coversUntil"] == LONG_ROWS[15]["id"]
        request = server.requests[1]["messages"][-1]["content"]
        assert "<prior-summary>" in request and "Question 05" in request and "Question 04" not in request

        # A model that fails every attempt: 502, the summary stays
        fake_db.rows = LONG_ROWS[:22]
        server.script(*[lambda body: completion("I can't help with that.")] * 3)
        response = await client.post("/api/message/summarize", json={"conversationId": "c"})
        assert response.status_code == 502 and "no_sections" in response.json()["detail"], response.text
        assert fake_db.summary["message_count"] == 16

    # Too short: 422 without a model call
    server.reset()
    with message_api(EndpointDB([user(1000, 1, "Hi"), assistant(1500, 1, "Hello!")]), config) as client:
        response = await client.post("/api/message/summarize", json={"conversationId": "c"})
    assert response.status_code == 422, response.text
    assert not server.requests


async def test_tool_calls_are_summarized_with_the_answer(server):
    tool_record = [
        {"role": "assistant", "content": "Let me look.", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": '{"file": "fox.png"}'}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "fox.png: " + "pixels " * 1000},
        {"role": "assistant", "content": "A fox in the snow."},
    ]
    entries = [(1, {"role": "user", "content": "What is in fox.png?"}),
               (2, {"role": "assistant", "content": "Let me look.\n\nA fox in the snow.", TOOL_RECORD_KEY: tool_record})]
    parts = transcript_parts(entries)
    assert parts[:3] == ["[User]: What is in fox.png?", "[Assistant]: Let me look.",
                         '[Assistant called the tool read_file]: {"file": "fox.png"}'], parts[:3]
    # A long result is cut: what mattered of it is in the answer
    assert parts[3].startswith("[Tool result]: fox.png: pixels") and parts[3].endswith(" […]"), parts[3][-40:]
    assert len(parts[3]) < TOOL_RESULT_CHARS + 30 and parts[4] == "[Assistant]: A fox in the snow."
    # The answer counts with its calls and results when deciding what to fold
    budget = 3000
    rows = [(n, {"role": role, "content": "x" * 300}) for n, role in enumerate(["user", "assistant"] * 3, start=10)]
    assert messages_to_summarize([*entries, *rows], None, budget) > 0
    plain = [entries[0], (2, {"role": "assistant", "content": entries[1][1]["content"]})]
    assert messages_to_summarize([*plain, *rows], None, budget) == 0


class StoringDB(EndpointDB):
    """Keeps the answers the endpoint saves as rows, with their tool records, for the next answer."""

    def create_agent_message(self, **message):
        super().create_agent_message(**message)
        self.rows.append({"id": message["message_id"], "time": message["time"], "roleName": message["role_name"],
                          "content": message["content"], "type": "agent"})
        if message.get("tool_record"):
            # Through JSON, as the database keeps it (a JSONB column)
            self.tool_records[message["message_id"]] = json.loads(json.dumps(message["tool_record"]))


async def test_stream_generate_keeps_and_replays_tool_calls(server):
    from backend.api import messages
    from backend.services.mcp.tools import McpToolset

    async def lookup(key: str) -> dict:
        return {"key": key, "value": f"value-of-{key}"}

    tools = ToolRegistry([Tool(name="lookup", description="Look up a key", func=lookup, parameters={
        "type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]})])

    async def no_mcp(current_user, conversation, config, tools, answer_id=None):
        return tools, McpToolset()

    def calls_the_tool(body):
        return [chunk(content="Let me look."),
                chunk(tool_calls=[tool_call_delta(0, id="lookup:0", name="lookup", arguments='{"key": "alpha"}')]),
                chunk(finish_reason="tool_calls"), usage_chunk(50, 5)]

    def answers(body):
        return [chunk(content="Alpha is value-of-alpha."), chunk(finish_reason="stop"), usage_chunk(80, 6)]

    question = user(1000_000, 1000, "What is alpha?")
    fake_db = StoringDB([question])
    config = make_config(server.base_url, context_window=100000, supports_tools=True)
    saved = messages._agent_tools, messages._mcp_tools, messages.auto_hide_definition
    messages._agent_tools = lambda current_user, conversation, config, *rest: tools
    messages._mcp_tools = no_mcp
    messages.auto_hide_definition = lambda user_id: ""  # No database here
    try:
        server.script(calls_the_tool, answers)
        with message_api(fake_db, config) as client:
            response = await client.post("/api/message/stream-generate", json={"conversationId": "c"})
            assert response.status_code == 200 and "event: done" in response.text, response.text
            stored = fake_db.answers[0]
            assert stored["content"] == "Let me look.\n\nAlpha is value-of-alpha.", stored["content"]
            tool_record = stored["tool_record"]
            assert [m["role"] for m in tool_record] == ["assistant", "tool", "assistant"], tool_record
            assert tool_record[0]["content"] == "Let me look." and tool_record[0]["tool_calls"][0]["id"] == "lookup:0"
            assert json.loads(tool_record[1]["content"]) == {"key": "alpha", "value": "value-of-alpha"}
            assert tool_record[2] == {"role": "assistant", "content": "Alpha is value-of-alpha."}
            last_request = server.requests[-1]["messages"]

            # The next answer gets the call and its result back, and its request starts with the last one
            follow_up = {"id": stored["message_id"] + 1000, "time": stored["time"] + 1, "roleName": "user",
                         "content": "Did you look it up?", "type": "text"}
            fake_db.rows.append(follow_up)

            def next_answer(body):
                assert body["messages"][:len(last_request)] == last_request, body["messages"]
                assert body["messages"][len(last_request):] == [
                    {"role": "assistant", "content": "Alpha is value-of-alpha."},
                    {"role": "user", "content": "Did you look it up?"}], body["messages"][len(last_request):]
                return [chunk(content="Yes, with lookup."), chunk(finish_reason="stop"), usage_chunk(120, 5)]

            server.script(next_answer)
            response = await client.post("/api/message/stream-generate", json={"conversationId": "c"})
            assert response.status_code == 200 and "event: done" in response.text, response.text
            assert not server.errors, server.errors
            assert fake_db.answers[1]["content"] == "Yes, with lookup." and not fake_db.answers[1]["tool_record"]

            # The token indicator counts the calls and results too
            sized = await client.post("/api/message/context-size", json={"conversationId": "c"})
            assert sized.status_code == 200, sized.text
            size = sized.json()
            assert size["messageCount"] == 4 and size["leftOutCount"] == 0, size
            texts = sum(estimate_tokens(row["content"]) for row in fake_db.rows)
            assert size["historyTokens"] > texts + estimate_tokens(tool_record[1]["content"]), (size, texts)
    finally:
        messages._agent_tools, messages._mcp_tools, messages.auto_hide_definition = saved


def continued(previous: dict, body: dict) -> list:
    """
    The messages a request adds to an earlier one, after checking that it starts like it word for
    word: the same tools and settings, and all of the earlier one's messages first. A provider's
    prompt cache only hits on such a start.
    """
    settings_of = lambda request: {key: value for key, value in request.items() if key != "messages"}
    assert settings_of(body) == settings_of(previous), (settings_of(previous), settings_of(body))
    count = len(previous["messages"])
    assert body["messages"][:count] == previous["messages"], (previous["messages"], body["messages"])
    return body["messages"][count:]


async def test_every_request_continues_the_one_before(server):
    """
    How Kimi K3 answers (its reasoning passed back, also of earlier answers, two rounds of tools,
    the memory in the system prompt), through stream-generate: every model call of an answer, and the first one of the
    next answer, continues the request before it, so the provider's prompt cache can hit. When the
    memory changes, the system prompt keeps its snapshot and the change goes in a note with the
    newest message (backend/services/memory_snapshot.py), so only the last exchange is new.
    """
    from backend.api import messages
    from backend.services.mcp.tools import McpToolset

    async def lookup(key: str) -> dict:
        return {"key": key, "value": f"value-of-{key}"}

    async def memory_add(line: str) -> str:
        return "Saved."

    tools = ToolRegistry([
        Tool(name="lookup", description="Look up a key", func=lookup, parameters={
            "type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}),
        Tool(name="memory_add", description="Add a line to the memory", func=memory_add, parameters={
            "type": "object", "properties": {"line": {"type": "string"}}, "required": ["line"]}),
    ])

    class Memory:
        content = "## About the user\n- Likes foxes."

        def get_memory(self, user_id, vault, family_mode=False):
            return {"content": self.content}

    async def no_mcp(current_user, conversation, config, tools, answer_id=None):
        return tools, McpToolset()

    def looks_up(key, call_id):
        def turn(body):
            return [chunk(reasoning_content=f"I need {key}."), chunk(content=f"Looking up {key}."),
                    chunk(tool_calls=[tool_call_delta(0, id=call_id, name="lookup",
                                                      arguments=json.dumps({"key": key}))]),
                    chunk(finish_reason="tool_calls"), usage_chunk(100, 10)]
        return turn

    def answers(text):
        def turn(body):
            return [chunk(reasoning_content="I have it."), chunk(content=text), chunk(finish_reason="stop"),
                    usage_chunk(100, 10)]
        return turn

    async def asks(text):
        # Ids are the server's clock in milliseconds: the question's now, the answer's a little later
        now = max(fake_db.rows[-1]["id"] + 1, int(time.time() * 1000))
        fake_db.rows.append({"id": now, "time": now, "roleName": "user", "content": text, "type": "text"})
        await asyncio.sleep(0.01)

    fake_db = StoringDB([user(1000_000, 1000, "What are alpha and beta?")])
    config = make_config(server.base_url, context_window=100000, supports_tools=True,
                         reasoning="always", reasoning_passback=True)
    saved = (messages._agent_tools, messages._mcp_tools, messages.auto_hide_definition, messages.kb,
             messages.persona_vault)
    messages._agent_tools = lambda current_user, conversation, config, *rest: tools
    messages._mcp_tools = no_mcp
    messages.auto_hide_definition = lambda user_id: ""  # No database here
    memory = messages.kb = Memory()
    messages.persona_vault = lambda current_user, conversation: 0
    try:
        with message_api(fake_db, config) as client:
            # An answer with two rounds of tools: three model calls
            server.script(looks_up("alpha", "lookup:0"), looks_up("beta", "lookup:1"),
                          answers("Alpha and beta are found."))
            response = await client.post("/api/message/stream-generate", json={"conversationId": "c"})
            assert response.status_code == 200 and "event: done" in response.text, response.text
            first = list(server.requests)
            assert len(first) == 3, len(first)
            assert "Likes foxes." in first[0]["messages"][0]["content"], first[0]["messages"][0]
            assert [tool["function"]["name"] for tool in first[0]["tools"]] == ["lookup", "memory_add"]
            for previous, body in zip(first, first[1:]):
                added = continued(previous, body)
                assert [m["role"] for m in added] == ["assistant", "tool"], added
                assert added[0].get("reasoning_content"), added  # passed back within the answer

            # The next answer continues the last request with the answer's text (with the reasoning
            # that led to it) and the new question
            await asks("And gamma?")
            server.script(answers("Gamma is unknown."))
            response = await client.post("/api/message/stream-generate", json={"conversationId": "c"})
            assert response.status_code == 200 and "event: done" in response.text, response.text
            second = server.requests[-1]
            assert continued(first[-1], second) == [
                {"role": "assistant", "content": "Alpha and beta are found.", "reasoning_content": "I have it."},
                {"role": "user", "content": "And gamma?"}], second["messages"]

            # And so does the one after an answer without tools
            await asks("Thanks.")
            server.script(answers("You're welcome."))
            response = await client.post("/api/message/stream-generate", json={"conversationId": "c"})
            assert response.status_code == 200 and "event: done" in response.text, response.text
            third = server.requests[-1]
            assert continued(second, third) == [
                {"role": "assistant", "content": "Gamma is unknown.", "reasoning_content": "I have it."},
                {"role": "user", "content": "Thanks."}], third["messages"]

            # The memory changed (the agent saved a line, or the review ran): the system prompt keeps
            # its snapshot, the line goes in a note at the start of the newest message
            memory.content += "\n- Has a cat."
            await asks("Bye.")
            server.script(answers("Bye!"))
            response = await client.post("/api/message/stream-generate", json={"conversationId": "c"})
            assert response.status_code == 200 and "event: done" in response.text, response.text
            fourth = server.requests[-1]
            added = continued(third, fourth)
            assert added[0] == {"role": "assistant", "content": "You're welcome.", "reasoning_content": "I have it."}, added
            note, question = added[1]["content"].split("\n\n", 1)
            assert note.startswith("<memory-update>") and "Added:\n- Has a cat." in note, note
            assert question == "Bye." and "Has a cat" not in fourth["messages"][0]["content"]

            # The next request starts like that one up to its newest message: the note moved on,
            # it was never stored
            await asks("One more thing.")
            server.script(answers("Yes?"))
            response = await client.post("/api/message/stream-generate", json={"conversationId": "c"})
            assert response.status_code == 200 and "event: done" in response.text, response.text
            fifth = server.requests[-1]
            assert fifth["messages"][:len(fourth["messages"]) - 1] == fourth["messages"][:-1]
            assert fifth["messages"][len(fourth["messages"]) - 1:-1] == [
                {"role": "user", "content": "Bye."},
                {"role": "assistant", "content": "Bye!", "reasoning_content": "I have it."}], fifth["messages"]
            assert fifth["messages"][-1]["content"].endswith("\n\nOne more thing.") and \
                "- Has a cat." in fifth["messages"][-1]["content"]
            assert all("<memory-update>" not in row["content"] for row in fake_db.rows), "never stored"
            assert not server.errors, server.errors
    finally:
        (messages._agent_tools, messages._mcp_tools, messages.auto_hide_definition, messages.kb,
         messages.persona_vault) = saved


async def test_system_prompt_is_shown_and_can_be_replaced(server):
    # Manual editing shows the system prompt as the conversation's first message, and can replace it
    from backend.services import hidden_content
    rows = [user(1000, 1, "Hi"), assistant(1500, 1, "Hello!"), system(1600, 2, "Be brief."), user(2000, 2, "And now?")]
    fake_db = EndpointDB(rows)
    config = make_config(server.base_url, context_window=128000, supports_tools=False)
    instructions = f"{INSTRUCTIONS_HEADING}\nBe brief."
    generate = {"conversationId": "c", "aiParticipant": "Assistant"}
    where = {"conversationId": "c"}

    async def sent_system(client, headers=None):
        """The system message of the request an answer makes; None without one."""
        server.script(summary_or_answer)
        response = await client.post("/api/message/stream-generate", json=generate, headers=headers)
        assert response.status_code == 200 and "event: done" in response.text, response.text
        first = server.requests[-1]["messages"][0]
        return first["content"] if first["role"] == "system" else None

    with message_api(fake_db, config) as client:
        # Built from the agent: shown without the conversation's system messages, which follow it
        shown = (await client.get("/api/message/system-prompt", params=where)).json()
        assert shown == {"content": IDENTITY_PROMPT, "custom": False, "tokens": estimate_tokens(IDENTITY_PROMPT)}, shown
        assert await sent_system(client) == f"{IDENTITY_PROMPT}\n\n{instructions}"

        # The conversation's own: sent as it is
        response = await client.put("/api/message/system-prompt", json={**where, "content": "You are a pirate."})
        assert response.status_code == 200 and response.json()["custom"] is True, response.text
        assert response.json()["content"] == "You are a pirate." and fake_db.conversation == {"system_prompt": "You are a pirate."}
        assert (await client.get("/api/message/system-prompt", params=where)).json()["content"] == "You are a pirate."
        assert await sent_system(client) == f"You are a pirate.\n\n{instructions}"

        # None at all: the system messages are all of it, and without them there is no system message
        response = await client.put("/api/message/system-prompt", json={**where, "content": ""})
        assert response.json() == {"content": "", "custom": True, "tokens": 0}, response.text
        assert await sent_system(client) == instructions
        fake_db.rows = [row for row in rows if row["roleName"] != "system"]
        assert await sent_system(client) is None
        fake_db.rows = rows

        # Back to the one built from the agent
        response = await client.put("/api/message/system-prompt", json={**where, "content": None})
        assert response.json()["custom"] is False and response.json()["content"] == IDENTITY_PROMPT, response.text
        assert fake_db.conversation == {"system_prompt": None}
        assert (await client.put("/api/message/system-prompt", json={**where, "content": "x" * 200_001})).status_code == 422

        # A device in family mode isn't shown hidden lines or the section on hidden content, and a
        # save from it keeps both; its answers get the section, but not the hidden lines
        section = hide_prompt("surprise parties", with_knowledge_base=False)
        own = f"You are a pirate.\n\n{section}\n\n## Your memory:\n- likes tea\n- plans a surprise party #hidden"
        fake_db.conversation = {"system_prompt": own}
        family = {hidden_content.HEADER: "1"}
        saved_enabled, hidden_content.FAMILY_MODE_ENABLED = hidden_content.FAMILY_MODE_ENABLED, True
        try:
            assert (await client.get("/api/message/system-prompt", params=where)).json()["content"] == own
            shown = (await client.get("/api/message/system-prompt", params=where, headers=family)).json()["content"]
            assert shown == "You are a pirate.\n\n## Your memory:\n- likes tea", shown
            sent = await sent_system(client, family)
            assert "<what-to-hide>" in sent and "likes tea" in sent and "surprise party #hidden" not in sent, sent
            response = await client.put("/api/message/system-prompt", headers=family,
                                        json={**where, "content": shown.replace("pirate", "sailor")})
            assert response.json()["content"] == shown.replace("pirate", "sailor"), response.text
            stored = fake_db.conversation["system_prompt"]
            assert stored.startswith("You are a sailor.") and "- plans a surprise party #hidden" in stored, stored
            assert stored.endswith(section), stored
        finally:
            hidden_content.FAMILY_MODE_ENABLED = saved_enabled


async def test_generate_after_an_answer_asks_the_model_to_go_on(server):
    # Generate after an answer (manual editing): the model gets a note in the user's place, shown as a step
    rows = [user(1000, 1, "Tell me a story."), assistant(1500, 1, "Once upon a time there was a fox.")]
    fake_db = EndpointDB(rows)
    config = make_config(server.base_url, context_window=128000, supports_tools=False)
    with message_api(fake_db, config) as client:
        server.script(summary_or_answer)
        response = await client.post("/api/message/stream-generate",
                                     json={"conversationId": "c", "aiParticipant": "Assistant"})
        assert response.status_code == 200 and "event: done" in response.text, response.text
        sent = [(message["role"], message["content"]) for message in server.requests[-1]["messages"]]
        assert sent[-2:] == [("assistant", "Once upon a time there was a fox."), ("user", CONTINUE_NOTE)], sent
        steps = [json.loads(data) for event, data in sse_events(response.text) if event == "step"]
        assert [step["title"] for step in steps] == ["Asked to go on"] and CONTINUE_NOTE in steps[0]["content"], steps
        assert fake_db.answers[-1]["steps"][0]["title"] == "Asked to go on", "the step is stored with the answer"

        # After a message of the user nothing is added
        fake_db.rows = rows + [user(2000, 2, "And then?")]
        server.script(summary_or_answer)
        response = await client.post("/api/message/stream-generate",
                                     json={"conversationId": "c", "aiParticipant": "Assistant"})
        assert server.requests[-1]["messages"][-1] == {"role": "user", "content": "And then?"}
        assert not [event for event, _ in sse_events(response.text) if event == "step"]


TESTS = [test_summarizes_only_past_the_trigger, test_latest_question_is_never_summarized,
         test_fold_in_chunks_merges_prior_summary, test_bad_reply_is_retried, test_failure_keeps_usage,
         test_summary_must_be_smaller, test_on_request_scales_the_length, test_oversized_message_is_split,
         test_history_starts_with_summary, test_stream_generate_summarizes_past_the_trigger,
         test_summarize_on_request, test_tool_calls_are_summarized_with_the_answer,
         test_stream_generate_keeps_and_replays_tool_calls, test_every_request_continues_the_one_before,
         test_system_prompt_is_shown_and_can_be_replaced, test_generate_after_an_answer_asks_the_model_to_go_on]


async def main() -> int:
    failures = 0
    with FakeOpenAIServer() as server:
        for test in TESTS:
            server.reset()
            try:
                await test(server)
                print(f"PASS  {test.__name__}")
            except Exception:
                failures += 1
                print(f"FAIL  {test.__name__}")
                traceback.print_exc()
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
