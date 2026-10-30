"""
Offline test of the conversation history builder (OpenAI message format).

    python -m backend.llm.tests.test_history

Uses a fake database and a temporary FILES_DIR: images go to vision models as
image_url parts, text-only models get the attachment placeholder (so they can
call get_file_content), earlier attachments become placeholders, empty
assistant messages are skipped, regenerating cuts the history at the
message being regenerated, also within the same second, and the history is
cut to the newest messages that fit the model's context window.
"""
import asyncio
import json
import os
import sys
import tempfile
import traceback

from backend.config import DEFAULT_CONTEXT_WINDOW
from backend.llm.smoke_test import _png
from backend.llm.types import ModelConfig
from backend.services import file_utils
from backend.services.conversation_history import (
    CHARS_PER_TOKEN,
    ConversationHistoryBuilder,
    OUTPUT_RESERVE,
    estimate_tokens,
    history_token_budget,
)

# The config is loaded before this module runs, so point the file lookup at a temporary directory
FILES_DIR = tempfile.mkdtemp(prefix="history-test-")
file_utils.FILES_DIR = FILES_DIR


class FakeDB:
    """Just get_messages_by_conversation, with the real query's filters; ties in time come back unordered."""

    def __init__(self, rows):
        self.rows = rows

    def get_messages_by_conversation(self, conversation_id, before_timestamp=None, limit=30):
        rows = [r for r in self.rows if before_timestamp is None or r["time"] < before_timestamp]
        # ORDER BY time DESC leaves ties unordered; return them in the worst order
        return sorted(rows, key=lambda r: (r["time"], -r["id"]), reverse=True)[:limit]


def user(id, time, text, attachments=None):
    content = json.dumps({"content": text, "attachments": attachments}) if attachments else text
    return {"id": id, "time": time, "roleName": "user", "content": content, "type": "text"}


def assistant(id, time, text):
    return {"id": id, "time": time, "roleName": "Assistant", "content": text, "type": "agent"}


IMAGE = {"fileId": "img1", "fileName": "red.png", "mimeType": "image/png", "fileSize": 100}
ROWS = [
    user(1000_000, 1000, "Look at this", [IMAGE]),
    assistant(1000_500, 1000, "It is red."),
    assistant(1001_000, 1001, ""),            # a failed answer without text
    user(1002_000, 1002, "And this one?", [{**IMAGE, "fileId": "img2"}]),
    assistant(1002_400, 1002, "Also red."),   # same second as its question
]


async def test_vision_model_gets_image():
    messages, attachments = await ConversationHistoryBuilder(FakeDB(ROWS[:4])).build_history("c", supports_vision=True)
    assert [m["role"] for m in messages] == ["user", "assistant", "user"], messages
    # Earlier attachment: placeholder; latest: image part
    assert "[Attachment: red.png (fileId: img1) - Image]" in messages[0]["content"]
    latest = messages[2]["content"]
    assert latest[0] == {"type": "text", "text": "And this one?"}
    assert latest[1]["type"] == "image_url" and latest[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert len(attachments) == 2


async def test_text_model_gets_placeholder():
    messages, _ = await ConversationHistoryBuilder(FakeDB(ROWS[:4])).build_history("c", supports_vision=False)
    latest = messages[2]["content"]
    assert isinstance(latest, str) and "(fileId: img2)" in latest, latest


async def test_regenerate_cuts_at_message():
    builder = ConversationHistoryBuilder(FakeDB(ROWS))
    messages, _ = await builder.build_history("c", before_message=ROWS[4], supports_vision=False)
    # The question from the same second is kept, the answer being regenerated is not
    assert messages[-1]["role"] == "user" and messages[-1]["content"].startswith("And this one?"), messages
    assert all(m["content"] != "Also red." for m in messages)


def config(**overrides):
    return ModelConfig(id=1, display_name="Test", model_id="test", provider_id=1, provider_name="Test",
                       kind="openai_compatible", base_url=None, **overrides)


# 30 exchanges of 300 characters each (about 100 tokens per message)
LONG_ROWS = [row for n in range(30) for row in (
    user(2000_000 + n * 1000, 2000 + n, f"Question {n:02d} " + "q" * 288),
    assistant(2000_500 + n * 1000, 2000 + n, f"Answer {n:02d} " + "a" * 290),
)]


async def test_history_fits_token_budget():
    builder = ConversationHistoryBuilder(FakeDB(LONG_ROWS))
    everything, _ = await builder.build_history("c", token_budget=None)
    assert len(everything) == 60
    messages, _ = await builder.build_history("c", token_budget=1000)
    # The newest messages that fit, in order, and nothing older than what was dropped
    assert sum(estimate_tokens(m["content"]) for m in messages) <= 1000
    assert len(messages) == 1000 // estimate_tokens(LONG_ROWS[0]["content"]), len(messages)
    assert messages == everything[-len(messages):]


async def test_latest_question_survives_tiny_budget():
    rows = LONG_ROWS[:-1]  # ends with an unanswered question
    messages, _ = await ConversationHistoryBuilder(FakeDB(rows)).build_history("c", token_budget=10)
    assert len(messages) == 1 and messages[0]["content"].startswith("Question 29"), messages


async def test_budget_from_context_window():
    big = history_token_budget(config(context_window=524288))
    assert big == 524288 - OUTPUT_RESERVE - 52428, big
    # max_output_tokens is reserved for the answer, the system prompt and tools are subtracted
    prompt = "x" * 3000
    assert history_token_budget(config(context_window=524288, max_output_tokens=64000), prompt) == \
        524288 - 64000 - 52428 - 3000 // CHARS_PER_TOKEN
    # Models without a context window get DEFAULT_CONTEXT_WINDOW, the answer at most a quarter of it
    assert history_token_budget(config()) == \
        DEFAULT_CONTEXT_WINDOW - DEFAULT_CONTEXT_WINDOW // 4 - int(DEFAULT_CONTEXT_WINDOW * 0.1)


TESTS = [test_vision_model_gets_image, test_text_model_gets_placeholder, test_regenerate_cuts_at_message,
         test_history_fits_token_budget, test_latest_question_survives_tiny_budget, test_budget_from_context_window]


async def main() -> int:
    for file_id in ("img1", "img2"):
        with open(os.path.join(FILES_DIR, f"{file_id}.png"), "wb") as f:
            f.write(_png(8, 8, (255, 0, 0)))
    failures = 0
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
