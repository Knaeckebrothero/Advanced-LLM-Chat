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
the stored summary instead of the messages it covers.
"""
import asyncio
import sys
import traceback
from dataclasses import replace

from backend.llm.tests.fake_openai_server import FakeOpenAIServer, completion
from backend.llm.tests.test_history import LONG_ROWS, FakeDB, assistant, user
from backend.llm.types import KIND_OPENAI_COMPATIBLE, ModelConfig
from backend.services import conversation_summary
from backend.services.conversation_history import (
    SUMMARY_CONTINUE,
    SUMMARY_LEAD_IN,
    ConversationHistoryBuilder,
    estimate_tokens,
)
from backend.services.conversation_summary import (
    SUMMARY_KEEP,
    SUMMARY_PROMPT,
    SUMMARY_TRIGGER,
    SummaryFailed,
    messages_to_summarize,
    plan_chunks,
    summarize,
    summary_target_tokens,
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
    server.script(lambda body: completion(GOOD_SUMMARY))
    entries = await entries_of([user(1000, 1, "Hi there"), assistant(1500, 1, "Hello!")])
    try:
        await summarize(make_config(server.base_url), entries, None, 9000)
        raise AssertionError("expected SummaryFailed")
    except SummaryFailed as e:
        assert e.reason == "not_smaller", e.reason


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


TESTS = [test_summarizes_only_past_the_trigger, test_latest_question_is_never_summarized,
         test_fold_in_chunks_merges_prior_summary, test_bad_reply_is_retried, test_failure_keeps_usage,
         test_summary_must_be_smaller, test_oversized_message_is_split, test_history_starts_with_summary]


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
