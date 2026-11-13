"""
The agent's memory as a conversation's system prompt shows it (docs/knowledge_base.md, "The memory in
the prompt").

A provider's prompt cache only reads the part of a request that starts like an earlier one, word for
word. The memory sits in the system prompt, ahead of the whole history: a prompt that took the memory
fresh for every answer lost the cache whenever the memory changed (the agent saved a line, the memory
review or the nightly consolidation ran, a new day began), and the next answer paid the full input
price for the whole history once more.

So a conversation keeps a snapshot of the memory, as the Claude apps do (their memory stays as it was
when the conversation or the session began; what changes reaches the model as a note in the
conversation, or in the next one):

- The snapshot is taken at the conversation's first answer, and again once nothing was answered for
  MEMORY_SNAPSHOT_REFRESH_MINUTES (the provider's cache is gone by then anyway) or the conversation's
  knowledge base or family mode changed.
- Meanwhile the system prompt shows it with its day, unchanged, and what changed since (lines added
  and removed, a new day) goes to the model as a note at the start of the newest user message
  (change_note(), with_note()). The note moves on with every new message and is never stored, so a
  change only costs the last exchange.
- The agent's own saves in this conversation are also in its history, as its tool calls and results.
"""
import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from backend.config import MEMORY_SNAPSHOT_REFRESH_MINUTES
from backend.database import db
from backend.llm.prompts import memory_today

log = logging.getLogger(__name__)

NOTE_START = "<memory-update>"
NOTE_END = "</memory-update>"
NOTE_CHANGED = ("Your memory changed since the start of this conversation; the memory in your instructions "
                "is still the one from then. The lines that changed:")


@dataclass
class PromptMemory:
    """The memory an answer's system prompt shows, and the note on what changed since."""
    content: Optional[str]  # The memory as the prompt shows it; None or '' = empty
    day: date               # The day the prompt calls today
    note: Optional[str]     # For the newest user message (with_note()); None = nothing changed


def prompt_memory(conversation_id: str, memory: Optional[str], vault: int, family_mode: bool,
                  today: Optional[date] = None) -> PromptMemory:
    """
    The memory for the system prompt of the conversation's next answer: its snapshot, with a note on
    what changed since, or the memory as it is now (stored as the new snapshot).

    Args:
        conversation_id: The conversation.
        memory: The memory as it is now (the memory note's content, without hidden lines for a
            device in family mode); None = empty.
        vault: Its knowledge base (0: the user's shared one, else the persona's id).
        family_mode: Whether the answer is for a device in family mode.
        today: The day as it is now (memory_today() unless given).
    """
    today = today or memory_today()
    current = (memory or "").strip()
    snapshot = db.get_memory_snapshot(conversation_id)
    reason = _refresh_reason(conversation_id, snapshot, vault, family_mode)
    if reason:
        db.save_memory_snapshot(conversation_id, vault, family_mode, current, today)
        log.debug(f"Memory snapshot of {conversation_id} taken ({reason})")
        return PromptMemory(current, today, None)
    note = change_note(snapshot["content"], snapshot["day"], current, today)
    if note:
        log.debug(f"Memory of {conversation_id} changed since its snapshot: a note goes with the newest message")
    return PromptMemory(snapshot["content"], snapshot["day"], note)


def _refresh_reason(conversation_id: str, snapshot: Optional[dict], vault: int, family_mode: bool) -> str:
    """Why the prompt takes the memory as it is now, '' to keep the snapshot."""
    if snapshot is None:
        return "the first one"
    if snapshot["vault"] != vault or bool(snapshot["family_mode"]) != family_mode:
        return "another knowledge base or family mode"
    last = db.last_answer_time(conversation_id)
    if last is None:
        return "no answer yet"
    if time.time() * 1000 - last > MEMORY_SNAPSHOT_REFRESH_MINUTES * 60_000:
        return "after a pause"
    return ""


def _lines(memory: str) -> List[str]:
    return [line.strip() for line in (memory or "").splitlines() if line.strip()]


def change_note(old: str, old_day: date, new: str, today: date) -> Optional[str]:
    """
    The note on what changed between the memory the prompt shows (old, of old_day) and the memory as
    it is now: the lines added and removed, and a new day. None when nothing changed.
    """
    old_lines, new_lines = _lines(old), _lines(new)
    old_set, new_set = set(old_lines), set(new_lines)
    added = [line for line in new_lines if line not in old_set]
    removed = [line for line in old_lines if line not in new_set]
    parts = []
    if added or removed:
        parts.append(NOTE_CHANGED)
        if added:
            parts.append("Added:\n" + "\n".join(added))
        if removed:
            parts.append("Removed:\n" + "\n".join(removed))
    if today != old_day:
        parts.append(f"Today is now {today:%A}, {today.isoformat()}.")
    if not parts:
        return None
    return "\n".join([NOTE_START, *parts, NOTE_END])


def with_note(messages: List[dict], note: Optional[str]) -> List[dict]:
    """The history with the note at the start of its newest user message (a new list; the rest is shared)."""
    if not note:
        return messages
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, list):
            content = [{"type": "text", "text": note}, *content]
        else:
            content = f"{note}\n\n{content or ''}"
        return [*messages[:index], {**message, "content": content}, *messages[index + 1:]]
    return messages
