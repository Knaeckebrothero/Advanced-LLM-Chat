# backend/services/past_chats.py
"""
The user's earlier conversations for the agent (docs/past_chats.md): search them with a regular
expression, list them, read them.

An agent sees only the messages of its memory: messages.memory_vault, set when a message is
stored (a trigger in schema.sql) or when the memory review reads it, is the shared knowledge base
(0) or an agent's own one (its personas.id). The tools (backend/services/tools/chat_tools.py) bind
the user and the memory, so the model can't reach other chats. The current conversation counts
like any other.

The search is SRW's kb_grep (grep_notes() in src/shared/runtime/services/knowledge_store.py of
Superhuman-Remote-Worker), adapted: Postgres picks the candidate messages (the trigram index on
message_search_text(content)) and also takes out their matching lines with the lines around them,
so one regex engine does both and the statement timeout covers all of it.
"""
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.database import db
from backend.llm.prompts import memory_time_zone

log = logging.getLogger(__name__)

PATTERN_MAX_CHARS = 256          # From SRW: a longer pattern is an easy way to make Postgres work hard
STATEMENT_TIMEOUT_MS = 5000      # Per search, both queries
LINE_CHARS = 300                 # A matching line, cut around the match
CONTEXT_CHARS = 150              # The line before and after it
OPENING_CHARS = 300              # How a conversation starts, or its summary, in a list
READ_MAX_MESSAGES = 30
READ_MAX_CHARS = 15_000          # Per chat_read call, also for one message in full
READ_MESSAGE_CHARS = 3_000       # A message among others

# Postgres error codes
_INVALID_REGEX = "2201B"
_QUERY_CANCELED = "57014"

# Python's inline flags at the start, e.g. (?i): Postgres takes options only at the very start, where the search puts its own
_INLINE_FLAGS_RE = re.compile(r"^\(\?[a-zA-Z]+\)")
# The characters a regular expression gives a meaning (Postgres AREs); a backslash makes them literal
_REGEX_SPECIAL = set("\\^$.|?*+()[]{}")


class ChatSearchError(ValueError):
    """A request the tools refuse, with a message for the model."""


@dataclass(frozen=True)
class Scope:
    """Whose chats, of which memory: what the tools bind."""
    user_id: int
    vault: int


# =========================================================================
# Patterns and dates
# =========================================================================

def postgres_regex(pattern: str) -> str:
    """
    A regular expression as models write it (Python, JavaScript, grep -E) for Postgres: \\b and \\B
    outside brackets become \\y and \\Y (Postgres reads \\b as a backspace), and inline flags at the
    start such as (?i) are dropped (the search is case-insensitive and per line anyway).
    """
    pattern = _INLINE_FLAGS_RE.sub("", pattern, count=1)
    out, i, in_bracket = [], 0, False
    while i < len(pattern):
        char = pattern[i]
        if char == "\\" and i + 1 < len(pattern):
            escaped = pattern[i + 1]
            out.append({"b": "\\y", "B": "\\Y"}[escaped] if escaped in "bB" and not in_bracket else char + escaped)
            i += 2
        elif not in_bracket and char == "[":
            # A ] right after [ or [^ is a literal ]
            start = i + 1 + (pattern[i + 1:i + 2] == "^")
            start += pattern[start:start + 1] == "]"
            out.append(pattern[i:start])
            i, in_bracket = start, True
        elif in_bracket and char == "[" and pattern[i + 1:i + 2] in (":", ".", "="):
            # [:alpha:], [.x.], [=e=] inside a bracket
            end = pattern.find(pattern[i + 1] + "]", i + 2)
            end = len(pattern) - 2 if end < 0 else end
            out.append(pattern[i:end + 2])
            i = end + 2
        else:
            in_bracket = in_bracket and char != "]"
            out.append(char)
            i += 1
    return "".join(out)


def literal_regex(value: str) -> str:
    """A regular expression that matches the text as it is."""
    return "".join("\\" + char if char in _REGEX_SPECIAL else char for char in value)


def _search_regex(pattern: Optional[str], literal: bool) -> str:
    """The pattern as the Postgres regular expression the search runs, per line ((?n))."""
    pattern = (pattern or "").strip()
    if not pattern:
        raise ChatSearchError("Give a pattern: a regular expression such as \"lisbon|lissabon\", or a text with literal")
    if len(pattern) > PATTERN_MAX_CHARS:
        raise ChatSearchError(f"The pattern is longer than {PATTERN_MAX_CHARS} characters; search for its "
                              f"most telling part")
    return "(?n)" + (literal_regex(pattern) if literal else postgres_regex(pattern))


def _moment(value: Optional[str], name: str) -> Optional[int]:
    """A date or time from the model (ISO, in the memory's time zone) as a message id: the server's clock in ms."""
    if value is None or not str(value).strip():
        return None
    try:
        moment = datetime.fromisoformat(str(value).strip())
    except ValueError:
        raise ChatSearchError(f"{name} must be a date or time like 2026-11-03 or 2026-11-03T18:00, not {value!r}")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=memory_time_zone())
    return int(moment.timestamp() * 1000)


def when(message_id: Optional[int]) -> str:
    """A message's time (its id) in the memory's time zone."""
    if not message_id:
        return "?"
    return datetime.fromtimestamp(message_id / 1000, memory_time_zone()).strftime("%Y-%m-%d %H:%M")


def _period(after: Optional[str], before: Optional[str], params: dict, column: str = "m.id") -> str:
    """The SQL conditions of a period (after: from then on; before: until before then), with their parameters."""
    conditions = []
    params["after"], params["before"] = _moment(after, "after"), _moment(before, "before")
    if params["after"] is not None:
        conditions.append(f"{column} >= :after")
    if params["before"] is not None:
        conditions.append(f"{column} < :before")
    if params["after"] is not None and params["before"] is not None and params["after"] >= params["before"]:
        raise ChatSearchError("after must be earlier than before")
    return "".join(f" AND {condition}" for condition in conditions)


# =========================================================================
# Messages
# =========================================================================

def message_parts(content: Optional[str]) -> tuple[str, list[str]]:
    """
    A stored message's text and the names of its attachments: content is plain text, or a JSON
    object with "content" and "attachments" (as message_search_text() in schema.sql reads it).
    """
    content = content or ""
    if content.startswith("{"):
        try:
            parsed = json.loads(content)
        except ValueError:
            return content, []
        if isinstance(parsed, dict) and "content" in parsed:
            names = [att.get("name") or att.get("fileName") or "file" for att in parsed.get("attachments") or []
                     if isinstance(att, dict)]
            body = parsed.get("content")
            return (body if isinstance(body, str) else "" if body is None else json.dumps(body)), names
    return content, []


def role_of(role_name: Optional[str]) -> str:
    """'user', 'assistant' or 'system' for a stored roleName ('user', 'Assistant', ...)."""
    role = (role_name or "").lower()
    return role if role in ("user", "system") else "assistant"


def _cut(value: str, width: int, keep_end: bool = False) -> str:
    """A text on one line, at most about width characters: its start, or its end."""
    value = " ".join(value.split())
    if len(value) <= width:
        return value
    return "…" + value[-width:].lstrip() if keep_end else value[:width].rstrip() + "…"


def _around(line: str, position: int, width: int = LINE_CHARS) -> str:
    """A line on one line, cut to about width characters around the match at position (1-based)."""
    line = line.strip()
    if len(line) <= width:
        return " ".join(line.split())
    start = max(0, min(max(position - 1, 0) - width // 3, len(line) - width))
    part = " ".join(line[start:start + width].split())
    return ("…" if start > 0 else "") + part + ("…" if start + width < len(line) else "")


# Messages of a user's conversations in one memory; the search leaves out system messages
_SCOPE = """
    FROM messages m
    JOIN conversations c ON c.id = m."conversationId"
    WHERE c."userId" = :user_id AND m.memory_vault = :vault
"""
_NOT_SYSTEM = """ AND lower(m."roleName") <> 'system'"""


def _conversation_info(conn, scope: Scope, ids: list[str]) -> dict[str, dict]:
    """Title, agent, number of messages and first and last message of conversations, in the memory."""
    if not ids:
        return {}
    rows = conn.execute(text("""
        SELECT c.id, c.name, c.persona_id, p.name AS agent, count(*) AS messages,
               min(m.id) AS first_id, max(m.id) AS last_id
        FROM messages m
        JOIN conversations c ON c.id = m."conversationId"
        LEFT JOIN personas p ON p.id = c.persona_id
        WHERE c."userId" = :user_id AND m.memory_vault = :vault AND c.id = ANY(:ids)
        GROUP BY c.id, p.name
    """), {"user_id": scope.user_id, "vault": scope.vault, "ids": ids}).mappings()
    return {row["id"]: _info(row) for row in rows}


def _info(row) -> dict:
    agent = row["agent"] or ("a deleted agent" if row["persona_id"] is not None else None)
    return {"id": row["id"], "title": row["name"], "agent": agent, "message_count": row["messages"],
            "first": row["first_id"], "last": row["last_id"]}


# =========================================================================
# The tools' work
# =========================================================================

def search(scope: Scope, pattern: str, literal: bool = False, after: Optional[str] = None,
           before: Optional[str] = None, limit: int = 30) -> dict:
    """
    The lines of the memory's messages (not system messages) that match a regular expression,
    case-insensitive, newest first, with the non-empty lines before and after.

    Args:
        pattern: A regular expression (postgres_regex() takes \\b and inline flags), or with literal a text.
        after, before: The period (ISO dates or times in the memory's time zone).
        limit: Number of lines; also the number of candidate messages, since each has a matching line.

    Returns:
        {"conversations": [conversation info with "hits": [{"id", "role", "k", "line", "before", "after"}]],
         "lines": shown lines, "messages": matching messages in all, "matching_conversations": in all}.
        Conversations in the order of their newest hit.

    Raises:
        ChatSearchError: No pattern, too long, invalid, too slow, or a bad date.
    """
    params = {"user_id": scope.user_id, "vault": scope.vault, "regex": _search_regex(pattern, literal),
              "limit": limit}
    period = _period(after, before, params)
    match = "message_search_text(m.content) ~* :regex"
    lines_sql = rf"""
        WITH candidates AS (
            SELECT m.id, m."conversationId" AS conversation_id, m."roleName" AS role_name,
                   message_search_text(m.content) AS body
            {_SCOPE}{_NOT_SYSTEM} AND {match}{period}
            ORDER BY m.id DESC
            LIMIT :limit
        ), lines AS (
            SELECT candidates.id, candidates.conversation_id, candidates.role_name, line.body, line.n,
                   row_number() OVER w AS k,
                   lag(line.body) OVER w AS line_before, lead(line.body) OVER w AS line_after
            FROM candidates, regexp_split_to_table(candidates.body, E'\n') WITH ORDINALITY AS line(body, n)
            WHERE btrim(line.body) <> ''
            WINDOW w AS (PARTITION BY candidates.id ORDER BY line.n)
        )
        SELECT id, conversation_id, role_name, body, k, line_before, line_after,
               regexp_instr(body, :regex, 1, 1, 0, 'i') AS position
        FROM lines
        WHERE body ~* :regex
        ORDER BY id DESC, n
        LIMIT :limit
    """
    count_sql = f"""
        SELECT count(*) AS messages, count(DISTINCT m."conversationId") AS conversations
        {_SCOPE}{_NOT_SYSTEM} AND {match}{period}
    """
    try:
        with db.connection() as conn:
            conn.execute(text(f"SET LOCAL statement_timeout = {int(STATEMENT_TIMEOUT_MS)}"))
            rows = conn.execute(text(lines_sql), params).mappings().all()
            totals = conn.execute(text(count_sql), params).mappings().one()
            info = _conversation_info(conn, scope, list(dict.fromkeys(row["conversation_id"] for row in rows)))
    except DBAPIError as e:
        failure = _search_failed(e)
        if failure is None:
            raise
        raise failure from e

    result ={"conversations": [], "lines": len(rows), "messages": totals["messages"],
              "matching_conversations": totals["conversations"]}
    grouped: dict[str, dict] = {}
    for row in rows:
        conversation = grouped.get(row["conversation_id"])
        if conversation is None:
            conversation = grouped[row["conversation_id"]] = {**info[row["conversation_id"]], "hits": []}
            result["conversations"].append(conversation)
        conversation["hits"].append({
            "id": row["id"],
            "role": role_of(row["role_name"]),
            "k": row["k"],  # The line's number among the message's non-empty lines
            "line": _around(row["body"], row["position"] or 0),
            "before": _cut(row["line_before"], CONTEXT_CHARS, keep_end=True) if row["line_before"] else None,
            "after": _cut(row["line_after"], CONTEXT_CHARS) if row["line_after"] else None,
        })
    return result


def _search_failed(error: DBAPIError) -> Optional[ChatSearchError]:
    """A ChatSearchError for an invalid pattern or a search that took too long; else None."""
    original = error.orig
    code = getattr(original, "pgcode", None) or getattr(original, "sqlstate", None)
    if code == _INVALID_REGEX:
        diag = getattr(original, "diag", None)
        detail = (getattr(diag, "message_primary", None) or str(original)).strip()
        return ChatSearchError(f"The pattern is not a valid regular expression ({detail}). Escape special "
                               f"characters with a backslash, or set literal to search for the text as it is.")
    if code == _QUERY_CANCELED:
        log.warning(f"A search over past chats took longer than {STATEMENT_TIMEOUT_MS} ms")
        return ChatSearchError("The search took too long. Make the pattern more specific, e.g. with a word of "
                               "three or more letters, or limit it with after and before.")
    return None


def list_chats(scope: Scope, after: Optional[str] = None, before: Optional[str] = None, limit: int = 10) -> dict:
    """
    The memory's conversations with messages in the period, most recent first, with how they start:
    the summary of their earlier part (if every message it covers is in the memory), else the first
    message of the user.

    Returns:
        {"conversations": [conversation info with "summary" or "opening"], "total": with messages in the period}.
    """
    params = {"user_id": scope.user_id, "vault": scope.vault, "limit": limit}
    period = _period(after, before, params)
    in_period = f"bool_or(TRUE{period})" if period else "TRUE"
    with db.connection() as conn:
        rows = conn.execute(text(f"""
            SELECT c.id, c.name, c.persona_id, p.name AS agent, count(*) AS messages,
                   min(m.id) AS first_id, max(m.id) AS last_id,
                   (SELECT s.content FROM conversation_summaries s
                     WHERE s.conversation_id = c.id
                       AND NOT EXISTS (SELECT 1 FROM messages x WHERE x."conversationId" = c.id
                                       AND x.id <= s.covers_until AND x.memory_vault IS DISTINCT FROM :vault)
                   ) AS summary,
                   (SELECT message_search_text(f.content) FROM messages f
                     WHERE f."conversationId" = c.id AND f.memory_vault = :vault AND lower(f."roleName") = 'user'
                     ORDER BY f.id LIMIT 1) AS opening
            FROM messages m
            JOIN conversations c ON c.id = m."conversationId"
            LEFT JOIN personas p ON p.id = c.persona_id
            WHERE c."userId" = :user_id AND m.memory_vault = :vault
            GROUP BY c.id, p.name
            HAVING {in_period}
            ORDER BY max(m.id) DESC
            LIMIT :limit
        """), params).mappings().all()
        total = conn.execute(text(f"""
            SELECT count(DISTINCT m."conversationId") {_SCOPE}{period}
        """), params).scalar_one()
    conversations = []
    for row in rows:
        conversation = _info(row)
        if row["summary"]:
            conversation["summary"] = _cut(row["summary"], OPENING_CHARS)
        elif row["opening"]:
            conversation["opening"] = _cut(row["opening"], OPENING_CHARS)
        conversations.append(conversation)
    return {"conversations": conversations, "total": total}


def read_chat(scope: Scope, conversation: str, message: Optional[int] = None,
              messages_before: Optional[int] = None, messages_after: Optional[int] = None) -> dict:
    """
    Messages of one conversation in the memory: around a message, or from the start. Long messages
    are cut, one message alone (0 before and after) only at READ_MAX_CHARS.

    Returns:
        Conversation info (with "message_count", in the memory) with "messages" ([{"id", "role",
        "text", "attachments", "length", "cut"}]), "position" (1-based number of the first shown),
        "earlier" and "later" (messages not shown).

    Raises:
        ChatSearchError: No such conversation in the memory, or no such message in it.
    """
    conversation = (conversation or "").strip()
    with db.connection() as conn:
        ids = conn.execute(text(f"""
            SELECT m.id {_SCOPE} AND c.id = :conversation ORDER BY m.id
        """), {"user_id": scope.user_id, "vault": scope.vault, "conversation": conversation}).scalars().all()
        if not ids:
            raise ChatSearchError(f"No conversation {conversation!r} among your past chats; take the id from "
                                  f"chat_search or chat_list")
        if message is None:
            index, before = 0, 0
            after = 10 if messages_after is None else messages_after
        else:
            if message not in ids:
                raise ChatSearchError(f"The conversation has no message {message}; read it from the start "
                                      f"without message, or take a message id from chat_search")
            index = ids.index(message)
            before = 3 if messages_before is None else messages_before
            after = 8 if messages_after is None else messages_after
        # No more before it than there are, so near the start the rest of the 30 go after it
        before = max(0, min(int(before), index, READ_MAX_MESSAGES - 1))
        after = max(0, min(int(after), READ_MAX_MESSAGES - 1 - before))
        window = ids[index - before:index + after + 1]
        rows = conn.execute(text("""
            SELECT id, "roleName" AS role_name, content FROM messages WHERE id = ANY(:ids) ORDER BY id
        """), {"ids": window}).mappings().all()
        info = _conversation_info(conn, scope, [conversation])[conversation]

    alone = len(window) == 1
    budget, shown = READ_MAX_CHARS, []
    for row in rows:
        body, attachments = message_parts(row["content"])
        body = body.strip()
        limit = min(budget, READ_MAX_CHARS if alone else READ_MESSAGE_CHARS)
        if shown and limit < 200:
            break  # The budget is spent: the rest are "later"
        shown.append({"id": row["id"], "role": role_of(row["role_name"]), "text": body[:limit].rstrip(),
                      "attachments": attachments, "length": len(body), "cut": len(body) > limit})
        budget -= min(len(body), limit)
    first = ids.index(shown[0]["id"])
    last = ids.index(shown[-1]["id"])
    return {**info, "messages": shown, "position": first + 1, "earlier": first, "later": len(ids) - last - 1}
