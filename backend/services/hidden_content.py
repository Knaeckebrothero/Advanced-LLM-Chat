"""
Family mode: conversations, agents, notes and single lines of notes can be hidden, and a device in
family mode sends the header X-Family-Mode: 1 with its requests. The server then leaves the hidden
content out of what it shows and of what the agents of its answers see.

A line is hidden if it has the tag #hidden (case-insensitive, as a whole tag: not #hidden-art or #hiddenx); a
heading with the tag hides its section up to the next heading of the same or a higher level. Hiding
only removes lines, so restore_hidden() can put them back when text edited without them is saved.

What a hidden conversation writes into a knowledge base that isn't hidden is marked: a new note as a
whole, new lines with the tag (tag_lines(), tag_new_lines()). Agents with the tool group auto_hide also
mark on their own: the conversation (hide_chat, mark_conversation()), notes and memory lines (the
hidden parameter of the knowledge base tools). A mark records who set it (hidden_by): agents never change
what the user decided. Best effort, not a lock: the data stays where it is, and what a model writes in
its own words is only marked where the code or the model can tell.
"""
import difflib
import re
from typing import Optional

from fastapi import Request
from sqlalchemy import text

from backend.config import AUTO_HIDE_DEFINITION, FAMILY_MODE_ENABLED
from backend.database import db

HEADER = "X-Family-Mode"
TAG = "#hidden"

_TAG_RE = re.compile(r"(?<!\S)#hidden(?![\w/-])", re.IGNORECASE)
_TRAILING_TAG_RE = re.compile(r"\s*(?<!\S)#hidden(?![\w/-])\s*$", re.IGNORECASE)
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:\s|$)")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
# Lines that a tag at the end would break: a rule (---), a table's delimiter row (| --- | :-: |)
_STRUCTURE_RE = re.compile(r"^\s*(?:([-*_])(?:\s*\1){2,}|\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?)\s*$")

# A conversation (alias c) that is hidden: marked, or its agent is
CONVERSATION_SQL = "(c.hidden OR EXISTS (SELECT 1 FROM personas np WHERE np.id = c.persona_id AND np.hidden))"


def family_mode(request: Request) -> bool:
    """FastAPI dependency: the device is in family mode (and family mode is available)."""
    return FAMILY_MODE_ENABLED and request.headers.get(HEADER, "").strip() == "1"


# =========================================================================
# Lines
# =========================================================================

def has_tag(line: str) -> bool:
    return bool(_TAG_RE.search(line))


def strip_trailing_tag(value: str) -> tuple[str, bool]:
    """(the text without a #hidden at its end, whether it had one)."""
    stripped = _TRAILING_TAG_RE.sub("", value)
    return stripped, stripped != value


def _heading_level(line: str) -> Optional[int]:
    match = _HEADING_RE.match(line)
    return len(match.group(1)) if match else None


def hidden_mask(lines: list[str]) -> list[bool]:
    """Per line: hidden, because it has the tag or is in the section of a heading that has it."""
    hidden, section, fenced = [], None, False
    for line in lines:
        if _FENCE_RE.match(line):
            fenced = not fenced
            level = None
        else:
            level = None if fenced else _heading_level(line)
        if level is not None:
            if section is not None and level <= section:
                section = None
            if section is None and has_tag(line):
                section = level
        hidden.append(section is not None or has_tag(line))
    return hidden


def has_hidden(content: Optional[str]) -> bool:
    return bool(content) and has_tag(content)


def visible(content: Optional[str]) -> Optional[str]:
    """The content without its hidden lines and sections (only lines removed, nothing else changed)."""
    if not has_hidden(content):
        return content
    lines = content.split("\n")
    return "\n".join(line for line, hidden in zip(lines, hidden_mask(lines)) if not hidden)


def restore_hidden(old: str, new_visible: str) -> str:
    """
    The new text with the hidden lines of the old one put back: new_visible was edited from
    visible(old), so a save must not delete what the editor never saw. Each block of hidden lines
    goes after the visible line it followed in the old text; if that line was changed or removed,
    to where the change is in the new text.
    """
    if not has_hidden(old):
        return new_visible
    old_lines = old.split("\n")
    hidden = hidden_mask(old_lines)
    shown = [line for line, is_hidden in zip(old_lines, hidden) if not is_hidden]
    new_lines = new_visible.split("\n")

    # Blocks of hidden lines, each after the k-th visible line of the old text (-1: at the start)
    blocks: list[tuple[int, list[str]]] = []
    k = -1
    for line, is_hidden in zip(old_lines, hidden):
        if not is_hidden:
            k += 1
        elif blocks and blocks[-1][0] == k:
            blocks[-1][1].append(line)
        else:
            blocks.append((k, [line]))

    # Where the old visible lines are in the new text: the position to insert after old line k
    after: dict[int, int] = {-1: 0}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, shown, new_lines, autojunk=False).get_opcodes():
        for i in range(i1, i2):
            if tag == "equal":
                after[i] = j1 + (i - i1) + 1
            elif tag == "replace":
                after[i] = j1 + min(i - i1 + 1, j2 - j1)
            else:  # delete
                after[i] = j1

    result, start = [], 0
    for k, block in blocks:
        position = max(start, after.get(k, len(new_lines)))
        result += new_lines[start:position] + block
        start = position
    return "\n".join(result + new_lines[start:])


def _taggable(line: str) -> bool:
    return bool(line.strip()) and _heading_level(line) is None and not _STRUCTURE_RE.match(line) \
        and not has_tag(line)


def _tagged(line: str) -> str:
    return f"{line.rstrip()} {TAG}"


def tag_lines(content: str) -> str:
    """Every line of text gets the tag (not headings, rules, code blocks or lines that have it)."""
    return tag_new_lines("", content)


def tag_new_lines(old: str, new: str) -> str:
    """The lines of new that old doesn't have get the tag (like tag_lines())."""
    remaining: dict[str, int] = {}
    for line in old.split("\n"):
        remaining[line] = remaining.get(line, 0) + 1
    result, fenced = [], False
    for line in new.split("\n"):
        if _FENCE_RE.match(line):
            fenced = not fenced
            result.append(line)
            continue
        if remaining.get(line):
            remaining[line] -= 1
            result.append(line)
        else:
            result.append(_tagged(line) if not fenced and _taggable(line) else line)
    return "\n".join(result)


# =========================================================================
# Conversations and agents
# =========================================================================

def conversation_is_hidden(conversation_id: Optional[str]) -> bool:
    """The conversation is hidden, or its agent is."""
    if not conversation_id:
        return False
    with db.connection() as conn:
        return bool(conn.execute(text(f"SELECT {CONVERSATION_SQL} FROM conversations c WHERE c.id = :id"),
                                 {"id": conversation_id}).scalar())


def vault_is_hidden(vault: int) -> bool:
    """The knowledge base is the own one of a hidden agent (the shared one, 0, never is)."""
    if not vault:
        return False
    with db.connection() as conn:
        return bool(conn.execute(text("SELECT hidden FROM personas WHERE id = :id"), {"id": vault}).scalar())


def mark_conversation(conversation_id: str, hidden: bool = True) -> tuple[bool, str]:
    """
    An agent hides its conversation, or takes its own mark back (the tool hide_chat).

    Returns:
        (whether it changed, the text for the model). Nothing changes if the user decided (hidden_by
        'user'), the conversation is hidden through its agent, or it is so already; an agent takes back
        only a mark an agent set (a mark of unknown origin, e.g. imported, counts as the user's).
    """
    with db.connection() as conn:
        row = conn.execute(text(
            "SELECT c.hidden, c.hidden_by, coalesce(p.hidden, false) AS agent_hidden FROM conversations c "
            "LEFT JOIN personas p ON p.id = c.persona_id WHERE c.id = :id FOR UPDATE OF c"
        ), {"id": conversation_id}).mappings().first()
        if row is None:
            return False, "This conversation isn't stored yet; nothing was marked."
        if row["agent_hidden"]:
            return False, "This conversation is hidden already, because you, its agent, are."
        if row["hidden"] == hidden:
            return False, ("The conversation is hidden already." if hidden
                           else "The conversation isn't hidden; nothing to take back.")
        if row["hidden_by"] == "user":
            return False, (f"The user decided this conversation is {'not ' if not row['hidden'] else ''}hidden, so "
                           f"it stays as it is. Don't mark it again.")
        if not hidden and row["hidden_by"] != "agent":
            return False, "The conversation was hidden by the user, not by you, so the mark stays."
        conn.execute(text("UPDATE conversations SET hidden = :hidden, hidden_by = 'agent' WHERE id = :id"),
                     {"id": conversation_id, "hidden": hidden})
    return True, ("Hid the conversation. Family mode hides it now; the user can take "
                  "the mark back." if hidden else "Took your hidden mark of the conversation back.")


def auto_hide_definition_of(settings: Optional[dict]) -> str:
    """What agents hide on their own for a user_settings row: the user's text, else the server's."""
    own = (settings or {}).get("auto_hide_prompt")
    return (own if own is not None else AUTO_HIDE_DEFINITION).strip()


def auto_hide_definition(user_id: Optional[int]) -> str:
    """What agents hide on their own for a user ("": nothing, they get no tool for it)."""
    if not FAMILY_MODE_ENABLED:
        return ""
    if user_id is None:
        return AUTO_HIDE_DEFINITION
    with db.connection() as conn:
        row = conn.execute(text("SELECT auto_hide_prompt FROM user_settings WHERE user_id = :id"),
                           {"id": user_id}).mappings().first()
    return auto_hide_definition_of(dict(row) if row else None)


def hidden_conversations(user_id: int) -> set[str]:
    """The ids of the user's hidden conversations (marked, or of a hidden agent)."""
    with db.connection() as conn:
        return set(conn.execute(text(f'SELECT c.id FROM conversations c WHERE c."userId" = :user_id AND {CONVERSATION_SQL}'),
                                {"user_id": user_id}).scalars())
