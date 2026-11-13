"""
Offline test of the memory in a conversation's system prompt (backend/services/memory_snapshot.py).

    python -m backend.llm.tests.test_memory_snapshot

On a fake database: the first answer takes the memory as it is; while the conversation goes on the
prompt keeps that snapshot and its day, and what changed since (lines added and removed, a new day)
becomes a note; after a pause, or with another knowledge base or family mode, the prompt takes the
memory anew. The note goes at the start of the newest user message, also one with images.
"""
import asyncio
import sys
import time
import traceback
from datetime import date

from backend.services import memory_snapshot
from backend.services.memory_snapshot import NOTE_END, NOTE_START, change_note, prompt_memory, with_note

MONDAY, TUESDAY = date(2026, 11, 16), date(2026, 11, 17)
MEMORY = "## About the user\n- Likes foxes.\n- Lives in Vienna."


class FakeDB:
    """The snapshot table and the time of the newest answer."""

    def __init__(self):
        self.snapshots = {}
        self.last_answer = None
        self.saves = 0

    def get_memory_snapshot(self, conversation_id):
        return self.snapshots.get(conversation_id)

    def save_memory_snapshot(self, conversation_id, vault, family_mode, content, day):
        self.saves += 1
        self.snapshots[conversation_id] = {"conversation_id": conversation_id, "vault": vault,
                                           "family_mode": family_mode, "content": content, "day": day}

    def last_answer_time(self, conversation_id):
        return self.last_answer

    def answered(self, minutes_ago):
        self.last_answer = int((time.time() - minutes_ago * 60) * 1000)


def with_fake_db(test):
    async def run():
        fake, saved = FakeDB(), memory_snapshot.db
        memory_snapshot.db = fake
        try:
            await test(fake)
        finally:
            memory_snapshot.db = saved
    run.__name__ = test.__name__
    return run


async def test_change_note():
    assert change_note(MEMORY, MONDAY, MEMORY, MONDAY) is None
    # Lines moved or blank lines added: nothing to tell
    assert change_note(MEMORY, MONDAY, "\n- Lives in Vienna.\n\n## About the user\n- Likes foxes.\n", MONDAY) is None
    note = change_note(MEMORY, MONDAY, MEMORY.replace("- Lives in Vienna.", "- Lives in Graz.\n- Has a cat."), MONDAY)
    assert note.startswith(NOTE_START) and note.endswith(NOTE_END), note
    assert "Added:\n- Lives in Graz.\n- Has a cat." in note and "Removed:\n- Lives in Vienna." in note, note
    assert "Today is" not in note
    # A new day only
    assert change_note(MEMORY, MONDAY, MEMORY, TUESDAY) == f"{NOTE_START}\nToday is now Tuesday, 2026-11-17.\n{NOTE_END}"
    # From an empty memory
    note = change_note("", MONDAY, "- Likes foxes.", MONDAY)
    assert "Added:\n- Likes foxes." in note and "Removed" not in note, note


async def test_with_note():
    history = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"},
               {"role": "user", "content": "And now?"}]
    assert with_note(history, None) is history
    noted = with_note(history, "NOTE")
    assert noted[2] == {"role": "user", "content": "NOTE\n\nAnd now?"}, noted
    assert noted[:2] == history[:2] and history[2]["content"] == "And now?", "the history itself is unchanged"
    # A message with images: the note is its first part
    image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,Rk9Y"}}
    noted = with_note([{"role": "user", "content": [{"type": "text", "text": "Look"}, image]}], "NOTE")
    assert noted[0]["content"] == [{"type": "text", "text": "NOTE"}, {"type": "text", "text": "Look"}, image]
    # The newest user message, also before an assistant message (a tool loop's history)
    noted = with_note([*history, {"role": "assistant", "content": "Let me look."}], "NOTE")
    assert noted[2]["content"].startswith("NOTE") and noted[0]["content"] == "Hi"
    assert with_note([{"role": "assistant", "content": "x"}], "NOTE") == [{"role": "assistant", "content": "x"}]


@with_fake_db
async def test_snapshot_kept_while_the_conversation_goes_on(fake):
    # The first answer: the memory as it is, no note
    first = prompt_memory("c", MEMORY, 0, False, today=MONDAY)
    assert (first.content, first.day, first.note) == (MEMORY, MONDAY, None) and fake.saves == 1
    fake.answered(minutes_ago=2)
    # Unchanged: the same snapshot, no note, nothing stored
    again = prompt_memory("c", MEMORY, 0, False, today=MONDAY)
    assert (again.content, again.day, again.note) == (MEMORY, MONDAY, None) and fake.saves == 1
    # The agent saved a line: the prompt keeps the snapshot, the note has the line
    changed = MEMORY + "\n- Has a cat."
    kept = prompt_memory("c", changed, 0, False, today=MONDAY)
    assert kept.content == MEMORY and "Added:\n- Has a cat." in kept.note and fake.saves == 1, kept
    # Past midnight: the prompt's day stays, the note tells the new one
    late = prompt_memory("c", changed, 0, False, today=TUESDAY)
    assert late.day == MONDAY and "Today is now Tuesday" in late.note and "- Has a cat." in late.note, late


@with_fake_db
async def test_snapshot_taken_anew(fake):
    prompt_memory("c", MEMORY, 0, False, today=MONDAY)
    changed = MEMORY + "\n- Has a cat."
    # No answer yet (e.g. only the token indicator asked): the next answer takes it anew
    assert prompt_memory("c", changed, 0, False, today=MONDAY).note is None and fake.saves == 2
    # After a pause longer than the cache lasts
    fake.answered(minutes_ago=memory_snapshot.MEMORY_SNAPSHOT_REFRESH_MINUTES + 1)
    newer = changed + "\n- Plays chess."
    fresh = prompt_memory("c", newer, 0, False, today=TUESDAY)
    assert (fresh.content, fresh.day, fresh.note) == (newer, TUESDAY, None) and fake.saves == 3, fresh
    # Another knowledge base (the agent changed) or family mode: anew, even right after an answer
    fake.answered(minutes_ago=1)
    assert prompt_memory("c", "- Other vault.", 7, False, today=TUESDAY).content == "- Other vault."
    assert prompt_memory("c", "- Visible only.", 7, True, today=TUESDAY).content == "- Visible only."
    assert fake.saves == 5
    # An empty memory is kept as empty
    assert prompt_memory("d", None, 0, False, today=TUESDAY).content == ""


TESTS = [test_change_note, test_with_note, test_snapshot_kept_while_the_conversation_goes_on,
         test_snapshot_taken_anew]


async def main() -> int:
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
