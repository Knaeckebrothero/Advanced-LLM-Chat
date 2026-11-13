#!/usr/bin/env python3
"""
Test of the agents' search over past chats (docs/past_chats.md) against a real Postgres: the memory
every message belongs to, the search, list and read behind the chat_* tools, and the tools as the
model calls them (through the tool registry).

Covers: messages.memory_vault set when a message is stored (no agent, an agent without the
knowledge base, with "all tools", disabled, a guest's conversation, shared and own memory; the
agent changed in the middle of a conversation or deleted later; db.py's insert paths); the
one-time fill-in of existing messages (also of deleted agents, from their notes); the memory review
claiming the messages it read that belong to no memory (only up to its mark, not after a failure,
an imported conversation through review_conversation() against the fake OpenAI server of
backend/llm/tests); message_search_text() and message_parts() (JSON with attachments, text that
looks like JSON); the search (alternatives, parts of words, case, \\b, ^ on a later line, literal
text, a malformed pattern, the length cap, system messages and attachments left out, the lines
around a hit without blank lines, a long line cut around the match, the count beyond the shown
lines, the period, the scope: other users, other memories, the current conversation); that the
trigram index serves the search; a search that takes too long; chat_list (order, period, the
summary only when the memory has every message it covers); chat_read (from the start, around a
message, paging, cuts, one message alone, the budget, a conversation of two memories, unknown
conversations and messages); the tools' texts and refusals; a deleted conversation.

It creates the database <POSTGRES_DB>_chats_test if needed (or --database, whose name must contain
"test") and deletes its own test users, so it never touches the real database:

    python backend/services/tests/past_chats_test.py

Exit code 0 if every check passed.
"""
import argparse
import asyncio
import logging
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make the backend package importable when run as a script
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import delete, insert, select, text, update  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

from backend import config  # noqa: E402
from backend.database.db import Database, backfill_message_memory  # noqa: E402
from backend.database.tables import conversation_summaries, conversations, messages, personas, users  # noqa: E402
from backend.llm.prompts import memory_time_zone  # noqa: E402
from backend.llm.tools import ToolInputError, ToolText, tools_for_groups  # noqa: E402
from backend.services import knowledge_base, past_chats  # noqa: E402
from backend.services.knowledge_base import Writer  # noqa: E402
from backend.services.past_chats import ChatSearchError, Scope  # noqa: E402

TEST_EMAILS = ("chats-test-1@example.com", "chats-test-2@example.com", "chats-test-guest@example.com")
TEST_PERSONA_PREFIX = "Chat test agent"
GUEST = 2  # Index of the guest in user_ids

db: Database = None  # The test database, set in main()
user_ids: list[int] = []
_conversation_count = [0]


def at(day: int, minute: int = 0, second: int = 0) -> int:
    """A message id: noon on a day of October 2026 in the memory's time zone, in milliseconds."""
    moment = datetime(2026, 10, day, 12, minute, second, tzinfo=memory_time_zone())
    return int(moment.timestamp() * 1000)


def add_persona(name: str, tools, own_memory: bool = False, enabled: bool = True) -> int:
    with db.connection() as conn:
        return conn.execute(insert(personas).values(
            name=f"{TEST_PERSONA_PREFIX} {name}", system_prompt="You help.", tools=tools, own_memory=own_memory,
            enabled=enabled).returning(personas.c.id)).scalar_one()


def add_conversation(user_index: int, persona_id, name: str = "Chat") -> str:
    _conversation_count[0] += 1
    conversation_id = f"chats-test-{_conversation_count[0]}"
    with db.connection() as conn:
        conn.execute(insert(conversations).values(id=conversation_id, userId=user_ids[user_index], name=name,
                                                  persona_id=persona_id))
    return conversation_id


def add_message(conversation_id: str, role: str, content: str, message_id: int) -> int:
    with db.connection() as conn:
        conn.execute(insert(messages).values(id=message_id, conversationId=conversation_id, roleName=role,
                                             content=content, time=message_id // 1000))
    return message_id


def set_persona(conversation_id: str, persona_id) -> None:
    with db.connection() as conn:
        conn.execute(update(conversations).where(conversations.c.id == conversation_id).values(persona_id=persona_id))


def vault_of(message_id: int):
    with db.connection() as conn:
        return conn.execute(select(messages.c.memory_vault).where(messages.c.id == message_id)).scalar_one()


def scope(user_index: int = 0, vault: int = 0) -> Scope:
    return Scope(user_id=user_ids[user_index], vault=vault)


def refused(call, *args, **kwargs) -> str:
    try:
        result = call(*args, **kwargs)
    except ChatSearchError as e:
        return str(e)
    raise AssertionError(f"should have been refused, got: {result}")


def hit_lines(result: dict) -> list[str]:
    return [hit["line"] for conversation in result["conversations"] for hit in conversation["hits"]]


def cleanup(conn) -> None:
    """Delete the test users with their conversations (and so their notes) and the test agents."""
    test_users = select(users.c.id).where(users.c.email.in_(TEST_EMAILS))
    test_conversations = select(conversations.c.id).where(conversations.c.userId.in_(test_users))
    conn.execute(delete(messages).where(messages.c.conversationId.in_(test_conversations)))
    conn.execute(delete(conversations).where(conversations.c.userId.in_(test_users)))
    conn.execute(delete(users).where(users.c.email.in_(TEST_EMAILS)))
    conn.execute(delete(personas).where(personas.c.name.startswith(TEST_PERSONA_PREFIX)))


def reset() -> None:
    with db.connection() as conn:
        cleanup(conn)
        user_ids[:] = [conn.execute(insert(users).values(email=email, name="Chats test", is_guest=index == GUEST)
                                    .returning(users.c.id)).scalar_one()
                       for index, email in enumerate(TEST_EMAILS)]


# =========================================================================
# Which memory a message belongs to
# =========================================================================

async def test_memory_on_insert():
    shared = add_persona("shared", ["knowledge_base"])
    own = add_persona("own", ["files", "knowledge_base"], own_memory=True)
    cases = {
        "shared memory": (shared, 0),
        "own memory": (own, own),
        "no knowledge base": (add_persona("plain", ["files"]), None),
        "all tools": (add_persona("everything", None), None),
        "disabled": (add_persona("disabled", ["knowledge_base"], enabled=False), None),
        "no agent": (None, None),
    }
    for day, (name, (persona_id, expected)) in enumerate(cases.items(), 1):
        message_id = add_message(add_conversation(0, persona_id, name), "user", "hello", at(day))
        assert vault_of(message_id) == expected, (name, vault_of(message_id), expected)
    # A guest has no memory, even with such an agent
    assert vault_of(add_message(add_conversation(GUEST, shared), "user", "hi", at(7))) is None

    # The agent changed in the middle: each part keeps the memory of its time
    conversation = add_conversation(0, own, "Switched")
    first = add_message(conversation, "user", "Only for the own agent", at(8))
    set_persona(conversation, shared)
    second = add_message(conversation, "Assistant", "For everyone", at(8, 1))
    assert (vault_of(first), vault_of(second)) == (own, 0)
    # Deleting the agent keeps what its chats belong to; editing a message doesn't move it
    with db.connection() as conn:
        conn.execute(delete(personas).where(personas.c.id == own))
        conn.execute(update(messages).where(messages.c.id == first).values(content="Edited"))
    assert vault_of(first) == own

    # db.py's insert paths: a message, an agent's answer, one inserted between, an import
    conversation = add_conversation(0, shared, "Paths")
    db.create_message(at(9), conversation, "user", "created", at(9) // 1000)
    db.create_agent_message(at(9, 1), conversation, "Assistant", at(9, 1) // 1000, "answer")
    inserted = db.insert_message_next_to(conversation, at(9), False, "user", "between")
    assert vault_of(at(9)) == vault_of(at(9, 1)) == vault_of(inserted["id"]) == 0
    imported = db.import_conversation("chats-test-import", user_ids[0], "Imported", datetime(2024, 1, 1),
                                      datetime(2024, 1, 1), [{"id": at(10), "roleName": "user", "content": "old"}])
    assert imported and vault_of(at(10)) is None, "an import has no agent, so no memory"


async def test_message_text():
    cases = [
        ("Plain text", "Plain text", []),
        ('{"content": "With a file", "attachments": [{"name": "vet.pdf", "fileId": "file_1"}]}',
         "With a file", ["vet.pdf"]),
        ('{"content": null, "attachments": []}', "", []),
        ('{"other": 1}', '{"other": 1}', []),
        ("{ not json at all", "{ not json at all", []),
        ("", "", []),
    ]
    with db.connection() as conn:
        for content, expected, names in cases:
            found = conn.execute(text("SELECT message_search_text(:content)"), {"content": content}).scalar_one()
            assert found == expected, (content, found)
            assert past_chats.message_parts(content) == (expected, names), (content, past_chats.message_parts(content))
    # Text that starts like JSON is stored fine, although the index reads it
    conversation = add_conversation(0, add_persona("json", ["knowledge_base"]))
    add_message(conversation, "user", "{ broken: json", at(1))
    assert past_chats.search(scope(), "broken")["lines"] == 1


async def test_backfill_of_existing_messages():
    shared = add_persona("still here", ["knowledge_base"])
    own_gone = add_persona("own, deleted", ["knowledge_base"], own_memory=True)
    shared_gone = add_persona("shared, deleted", ["knowledge_base"])
    silent_gone = add_persona("silent, deleted", ["knowledge_base"])
    conversations_by_case = {
        "existing agent": add_conversation(0, shared),
        "deleted, with notes in its own vault": add_conversation(0, own_gone),
        "deleted, wrote to the shared vault": add_conversation(0, shared_gone),
        "deleted, no notes": add_conversation(0, silent_gone),
        "no agent": add_conversation(0, None),
    }
    ids = {}
    for day, (case, conversation) in enumerate(conversations_by_case.items(), 1):
        ids[case] = add_message(conversation, "user", case, at(day))
    knowledge_base.create_note(Writer(user_ids[0], vault=own_gone), "Own note", "Kept by the own agent.")
    knowledge_base.create_note(Writer(user_ids[0], conversation_id=conversations_by_case[
        "deleted, wrote to the shared vault"]), "Shared note", "Written from that chat.")
    kept = add_message(add_conversation(0, None), "user", "has one already", at(9))
    with db.connection() as conn:
        conn.execute(delete(personas).where(personas.c.id.in_([own_gone, shared_gone, silent_gone])))
        # As before the column existed
        conn.execute(update(messages).where(messages.c.id.in_(list(ids.values()))).values(memory_vault=None))
        conn.execute(update(messages).where(messages.c.id == kept).values(memory_vault=77))
        filled = backfill_message_memory(conn)
    assert filled == 3, filled
    expected = {"existing agent": 0, "deleted, with notes in its own vault": own_gone,
                "deleted, wrote to the shared vault": 0, "deleted, no notes": None, "no agent": None}
    assert {case: vault_of(message_id) for case, message_id in ids.items()} == expected
    assert vault_of(kept) == 77, "a message with a memory keeps it"


async def test_review_claims_messages_without_memory():
    shared = add_persona("reviewer", ["knowledge_base"])
    own = add_persona("own reviewer", ["knowledge_base"], own_memory=True)
    conversation = add_conversation(0, None, "Imported chat")
    first = add_message(conversation, "user", "From 2024", at(1))
    second = add_message(conversation, "Assistant", "Old answer", at(1, 1))
    third = add_message(conversation, "user", "Later", at(1, 2))
    with db.connection() as conn:
        conn.execute(update(messages).where(messages.c.id == first).values(memory_vault=own))  # Already in a memory
        before = conn.execute(select(messages.c.updated_at).where(messages.c.id == second)).scalar_one()
    set_persona(conversation, shared)
    # A failed review claims nothing
    db.set_memory_review(conversation, reviewed_until=second, failed=True, vault=0)
    assert vault_of(second) is None
    db.set_memory_review(conversation, reviewed_until=second, vault=0)
    assert (vault_of(first), vault_of(second), vault_of(third)) == (own, 0, None), "only up to the mark, only without one"
    with db.connection() as conn:
        after = conn.execute(select(messages.c.updated_at).where(messages.c.id == second)).scalar_one()
    assert after == before, "joining a memory is not a change of the message"

    # The whole way: an imported chat gets an agent with the knowledge base, then "Save to memory"
    from backend.catalog import resolver
    from backend.llm.tests.fake_openai_server import FakeOpenAIServer, chunk, usage_chunk
    from backend.llm.tests.test_openai_loop import make_config
    from backend.services import memory_review

    imported = add_conversation(0, None, "Imported 2023")
    old = [add_message(imported, role, words, at(2, minute))
           for minute, (role, words) in enumerate([("user", "My grandmother's recipe for Apfelstrudel"),
                                                   ("Assistant", "Here is how she might have made it")])]
    assert all(vault_of(message_id) is None for message_id in old)
    assert past_chats.search(scope(), "apfelstrudel")["lines"] == 0
    set_persona(imported, shared)
    saved = memory_review.db, memory_review.resolve_memory_model, resolver.db
    memory_review.db = resolver.db = db
    try:
        with FakeOpenAIServer() as server:
            memory_review.resolve_memory_model = lambda user, conv: make_config(server.base_url, reasoning="never")
            server.script(lambda body: [chunk(content="Nothing new to save"), chunk(finish_reason="stop"),
                                        usage_chunk(10, 3)])
            result = await memory_review.review_conversation(imported)
            assert result.status == "done" and not server.errors, (result, server.errors)
    finally:
        memory_review.db, memory_review.resolve_memory_model, resolver.db = saved
    assert all(vault_of(message_id) == 0 for message_id in old)
    assert past_chats.search(scope(), "apfelstrudel")["lines"] == 1


# =========================================================================
# Search
# =========================================================================

def chats_for_search() -> dict:
    """A user's chats in the shared memory, one in an agent's own, one of another user."""
    shared = add_persona("search", ["knowledge_base"])
    own = add_persona("diary", ["knowledge_base"], own_memory=True)
    trip = add_conversation(0, shared, "Lisbon trip")
    add_message(trip, "user", "We plan a trip to Lisbon in May.\n\nMy mother wants to come along.", at(3))
    add_message(trip, "Assistant", "Lissabon im Mai ist schön.\nThe category of hotels matters.\nA cat café too?", at(3, 1))
    add_message(trip, "system", "Always mention Lisbon.", at(3, 2))
    add_message(trip, "user", '{"content": "Here is the plan", "attachments": [{"name": "lisbon-plan.pdf"}]}',
                at(3, 3))
    family = add_conversation(0, shared, "Family")
    add_message(family, "user", "Meine Mutter hat Geburtstag.\nfirst line\nTODO: buy flowers", at(10))
    add_message(family, "Assistant", "Wie alt wird deine MUTTER?", at(10, 1))
    diary = add_conversation(0, own, "Diary")
    add_message(diary, "user", "Private: my mother and I argued.", at(12))
    other = add_conversation(1, add_persona("other user's", ["knowledge_base"]), "Not yours")
    add_message(other, "user", "Another user's mother.", at(12, 1))
    return {"trip": trip, "family": family, "diary": diary, "own": own}


async def test_search_matches():
    chats = chats_for_search()
    found = past_chats.search(scope(), r"\bmother\b|mutter|mama")
    assert hit_lines(found) == ["Wie alt wird deine MUTTER?", "Meine Mutter hat Geburtstag.",
                                "My mother wants to come along."], hit_lines(found)
    assert [c["title"] for c in found["conversations"]] == ["Family", "Lisbon trip"], "newest hit first"
    assert (found["messages"], found["matching_conversations"]) == (3, 2), found
    family = found["conversations"][0]
    assert (family["agent"], family["message_count"], family["id"]) == (f"{TEST_PERSONA_PREFIX} search", 2,
                                                                        chats["family"])
    assert [hit["role"] for hit in family["hits"]] == ["assistant", "user"]
    # A part of a word, any case; \b is a word boundary (Postgres's \y)
    assert hit_lines(past_chats.search(scope(), "lisbo")) == ["We plan a trip to Lisbon in May."]
    assert hit_lines(past_chats.search(scope(), r"\bcat\b")) == ["A cat café too?"]
    assert len(hit_lines(past_chats.search(scope(), "cat"))) == 2, "a part of a word finds category too"
    assert hit_lines(past_chats.search(scope(), "lissabon|LISBON")) == ["Lissabon im Mai ist schön.",
                                                                         "We plan a trip to Lisbon in May."]
    assert hit_lines(past_chats.search(scope(), "SCHÖN")) == ["Lissabon im Mai ist schön."], "umlauts in any case"
    # ^ and $ per line, also on a later line of a message
    assert hit_lines(past_chats.search(scope(), "^todo")) == ["TODO: buy flowers"]
    assert hit_lines(past_chats.search(scope(), "line$")) == ["first line"]
    # Literal text: dots and pluses are themselves
    add_message(chats["family"], "user", "I code in C++ and a.b.", at(11))
    add_message(chats["family"], "user", "Not axb.", at(11, 1))
    assert hit_lines(past_chats.search(scope(), "C++", literal=True)) == ["I code in C++ and a.b."]
    assert past_chats.search(scope(), "a.b", literal=True)["messages"] == 1
    assert past_chats.search(scope(), "a.b")["messages"] == 2, "as a regular expression . is any character"
    # System messages and attachment names are not searched; the text of a message with attachments is
    assert past_chats.search(scope(), "always mention")["lines"] == 0
    assert past_chats.search(scope(), "lisbon-plan|fileId")["lines"] == 0
    assert hit_lines(past_chats.search(scope(), "here is the plan")) == ["Here is the plan"]


async def test_search_lines_and_limits():
    chats_for_search()
    conversation = add_conversation(0, add_persona("long", ["knowledge_base"]), "Long")
    long_line = "word " * 200 + "NEEDLE in the middle " + "word " * 200
    add_message(conversation, "Assistant", f"Intro\n\n\n{long_line}\n\nOutro", at(20))
    hit = past_chats.search(scope(), "needle")["conversations"][0]["hits"][0]
    assert hit["before"] == "Intro" and hit["after"] == "Outro", "blank lines are skipped"
    assert "NEEDLE" in hit["line"] and hit["line"].startswith("…") and hit["line"].endswith("…"), hit["line"]
    assert len(hit["line"]) <= past_chats.LINE_CHARS + 2, len(hit["line"])
    first = past_chats.search(scope(), "we plan")["conversations"][0]["hits"][0]
    assert first["before"] is None and first["after"] == "My mother wants to come along."
    # More matches than lines shown: the count says how many in all
    limited = past_chats.search(scope(), "mother|mutter|lisbon|lissabon", limit=2)
    assert limited["lines"] == 2 and limited["messages"] == 4 and limited["matching_conversations"] == 2, limited
    # Refused
    assert "not a valid regular expression" in refused(past_chats.search, scope(), "(unclosed")
    assert "longer than 256" in refused(past_chats.search, scope(), "x" * 257)
    assert "Give a pattern" in refused(past_chats.search, scope(), "  ")
    assert "must be a date" in refused(past_chats.search, scope(), "x", after="last week")
    assert "earlier than before" in refused(past_chats.search, scope(), "x", after="2026-10-05", before="2026-10-04")
    # A search that takes too long is refused with advice (the timeout itself is Postgres's)
    timeout = DBAPIError("SELECT", {}, type("QueryCanceled", (Exception,), {"pgcode": "57014"})())
    assert "took too long" in str(past_chats._search_failed(timeout))
    assert past_chats._search_failed(DBAPIError("SELECT", {}, Exception("other"))) is None


async def test_search_scope_and_period():
    chats = chats_for_search()
    # The agent's own memory: only its own chats; the shared memory doesn't see them; another user sees nothing
    own = past_chats.search(scope(vault=chats["own"]), "mother")
    assert hit_lines(own) == ["Private: my mother and I argued."], own
    assert "Private" not in " ".join(hit_lines(past_chats.search(scope(), "mother|private")))
    assert hit_lines(past_chats.search(scope(1), "mother")) == ["Another user's mother."]
    assert past_chats.search(scope(1, chats["own"]), "mother")["lines"] == 0
    # A message without memory is found by nobody
    add_message(add_conversation(0, None, "No agent"), "user", "My mother, without memory", at(13))
    assert "My mother, without memory" not in hit_lines(past_chats.search(scope(), "mother"))
    # The period: after from a date on, before until before it
    assert [c["title"] for c in past_chats.search(scope(), "mother|mutter", after="2026-10-04")["conversations"]] \
        == ["Family"]
    assert [c["title"] for c in past_chats.search(scope(), "mother|mutter", before="2026-10-10")["conversations"]] \
        == ["Lisbon trip"]
    assert past_chats.search(scope(), "mother|mutter", after="2026-10-10T12:00:30", before="2026-10-11")["lines"] == 1
    # A deleted conversation is gone
    db.delete_conversation(chats["trip"], user_ids[0])
    assert "Lisbon trip" not in [c["title"] for c in past_chats.search(scope(), "mother|mutter")["conversations"]]


async def test_search_uses_the_trigram_index():
    with db.connection() as conn:
        assert conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")).first(), \
            "prepare_database() creates pg_trgm"
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(conn.execute(text(
            "EXPLAIN SELECT m.id FROM messages m WHERE message_search_text(m.content) ~* :regex"),
            {"regex": "(?n)" + past_chats.postgres_regex(r"\bmother\b|mutter")}).scalars())
    assert "idx_messages_search_trgm" in plan, plan


# =========================================================================
# List and read
# =========================================================================

async def test_list():
    chats = chats_for_search()
    listed = past_chats.list_chats(scope())
    assert listed["total"] == 2 and [c["title"] for c in listed["conversations"]] == ["Family", "Lisbon trip"]
    family, trip = listed["conversations"]
    assert family["opening"] == "Meine Mutter hat Geburtstag. first line TODO: buy flowers", family
    assert (trip["message_count"], trip["first"], trip["last"]) == (4, at(3), at(3, 3)), trip
    assert [c["title"] for c in past_chats.list_chats(scope(), after="2026-10-05")["conversations"]] == ["Family"]
    assert past_chats.list_chats(scope(), before="2026-10-01")["total"] == 0
    assert [c["title"] for c in past_chats.list_chats(scope(), limit=1)["conversations"]] == ["Family"]
    assert [c["title"] for c in past_chats.list_chats(scope(vault=chats["own"]))["conversations"]] == ["Diary"]
    # The summary of the earlier part instead of the opening, if the memory has every message it covers
    with db.connection() as conn:
        conn.execute(insert(conversation_summaries).values(conversation_id=chats["trip"], covers_until=at(3, 1),
                                                           message_count=2, content="Planning Lisbon with mother.",
                                                           created_at=0))
    trip = past_chats.list_chats(scope())["conversations"][1]
    assert trip.get("summary") == "Planning Lisbon with mother." and "opening" not in trip, trip
    with db.connection() as conn:
        conn.execute(update(messages).where(messages.c.id == at(3)).values(memory_vault=chats["own"]))
    trip = past_chats.list_chats(scope())["conversations"][1]
    assert "summary" not in trip and trip["opening"] == "Here is the plan", trip


async def test_read():
    persona_id = add_persona("reader", ["knowledge_base"])
    conversation = add_conversation(0, persona_id, "Long talk")
    ids = [add_message(conversation, "user" if n % 2 == 0 else "Assistant", f"Message number {n}", at(5, n))
           for n in range(40)]
    start = past_chats.read_chat(scope(), conversation)
    assert [m["text"] for m in start["messages"]] == [f"Message number {n}" for n in range(11)]
    assert (start["position"], start["earlier"], start["later"], start["messages"][0]["role"]) == (1, 0, 29, "user")
    around = past_chats.read_chat(scope(), conversation, message=ids[20])
    assert [m["id"] for m in around["messages"]] == ids[17:29] and (around["earlier"], around["later"]) == (17, 11)
    # At most 30 messages per call
    wide = past_chats.read_chat(scope(), conversation, message=ids[20], messages_before=25, messages_after=25)
    assert len(wide["messages"]) == 30 and wide["messages"][0]["id"] == ids[0], len(wide["messages"])
    # Long messages are cut, alone at more length; the budget ends a call early
    long_text = "x" * 20_000
    with db.connection() as conn:
        conn.execute(update(messages).where(messages.c.id.in_(ids[21:26])).values(content=long_text))
        conn.execute(update(messages).where(messages.c.id == ids[22]).values(
            content='{"content": "' + "y" * 5000 + '", "attachments": [{"name": "photo.jpg"}]}'))
    cut = past_chats.read_chat(scope(), conversation, message=ids[21], messages_before=0, messages_after=8)
    assert cut["messages"][0]["cut"] and len(cut["messages"][0]["text"]) == past_chats.READ_MESSAGE_CHARS
    assert cut["messages"][1]["attachments"] == ["photo.jpg"] and cut["messages"][1]["length"] == 5000
    assert len(cut["messages"]) == 5 and cut["later"] == 40 - 21 - 5, "the 15,000 characters are spent"
    alone = past_chats.read_chat(scope(), conversation, message=ids[21], messages_before=0, messages_after=0)
    assert len(alone["messages"]) == 1 and len(alone["messages"][0]["text"]) == past_chats.READ_MAX_CHARS
    # Unknown, of another user or another memory: the same answer
    for other_scope, conversation_id in ((scope(), "nope"), (scope(1), conversation), (scope(vault=persona_id),
                                                                                         conversation)):
        assert "No conversation" in refused(past_chats.read_chat, other_scope, conversation_id)
    assert "has no message 5" in refused(past_chats.read_chat, scope(), conversation, message=5)
    # A conversation of two memories: each sees its own part
    with db.connection() as conn:
        conn.execute(update(messages).where(messages.c.id.in_(ids[:10])).values(memory_vault=persona_id))
    shared_part = past_chats.read_chat(scope(), conversation)
    assert shared_part["messages"][0]["id"] == ids[10] and shared_part["message_count"] == 30, shared_part
    own_part = past_chats.read_chat(scope(vault=persona_id), conversation)
    assert [m["id"] for m in own_part["messages"]] == ids[:10] and own_part["later"] == 0, own_part


# =========================================================================
# The tools as the model calls them
# =========================================================================

async def test_tools():
    chats = chats_for_search()
    registry = tools_for_groups(["knowledge_base", "past_chats"], user_id=user_ids[0], vault=0)
    found = await registry.call("chat_search", {"pattern": r"\bmother\b|mutter", "max_matches": "2"})
    assert found.startswith("2 matching line(s); 3 message(s) in 2 conversation(s) match in all"), found
    assert f'Conversation {chats["family"]}: "Family" with {TEST_PERSONA_PREFIX} search, 2026-10-10 12:00 to ' \
           f'12:01, 2 message(s)' in found, found
    assert f"- message {at(10, 1)} (assistant, 2026-10-10 12:01):\n  > Wie alt wird deine MUTTER?" in found, found
    # Several matching lines of one message: one block, each line once (like grep -C1)
    merged = await registry.call("chat_search", {"pattern": "geburtstag|todo", "before": "2026-10-10T12:00:30"})
    assert merged.count(f"- message {at(10)} ") == 1, merged
    assert f"- message {at(10)} (user, 2026-10-10 12:00):\n  > Meine Mutter hat Geburtstag.\n    first line\n" \
           f"  > TODO: buy flowers\n" in merged, merged
    nothing = await registry.call("chat_search", {"pattern": "zebra"})
    assert nothing.startswith("No messages match"), nothing
    try:
        await registry.call("chat_search", {"pattern": "(oops"})
        raise AssertionError("an invalid pattern should be refused")
    except ToolInputError as e:
        assert "not a valid regular expression" in str(e) and "literal" in str(e)
    listed = await registry.call("chat_list", {})
    assert listed.startswith("2 conversation(s), most recent first:") and "Starts: Meine Mutter" in listed, listed
    read = await registry.call("chat_read", {"conversation": chats["trip"], "message": str(at(3, 1)),
                                             "messages_before": 0, "messages_after": 1})
    assert isinstance(read, ToolText) and read.metadata == {"chat": chats["trip"], "chatMessage": at(3, 1)}
    assert "Messages 2 to 3 of 4:" in read and "[message " in read and "system" in read, read
    assert "1 earlier message(s)" in read and "1 later message(s)" in read, read
    # A deleted agent is named as such
    with db.connection() as conn:
        conn.execute(delete(personas).where(personas.c.id == chats["own"]))
    own_registry = tools_for_groups(["knowledge_base", "past_chats"], user_id=user_ids[0], vault=chats["own"])
    assert "with a deleted agent" in await own_registry.call("chat_list", {})


TESTS = [test_memory_on_insert, test_message_text, test_backfill_of_existing_messages,
         test_review_claims_messages_without_memory, test_search_matches, test_search_lines_and_limits,
         test_search_scope_and_period, test_search_uses_the_trigram_index, test_list, test_read, test_tools]


async def run() -> int:
    failures = 0
    for test in TESTS:
        reset()
        try:
            await test()
            print(f"PASS  {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL  {test.__name__}")
            traceback.print_exc()
    with db.connection() as conn:
        cleanup(conn)
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


def main() -> int:
    global db
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--database", default=f"{config.POSTGRES_DB}_chats_test",
                        help="Test database, created if needed (default: <POSTGRES_DB>_chats_test)")
    args = parser.parse_args()
    if "test" not in args.database:
        print(f"Refusing to run against '{args.database}': the name must contain 'test'")
        return 2

    logging.basicConfig(level=logging.WARNING)
    for name in ("backend", "httpx"):
        logging.getLogger(name).setLevel(logging.WARNING)
    from backend.database.db_init import create_database_if_not_exists, migrate_schema
    create_database_if_not_exists(config.POSTGRES_HOST, config.POSTGRES_PORT, config.POSTGRES_USER,
                                  config.POSTGRES_PASSWORD, args.database, logging.getLogger("chats-test"))
    db = Database(database=args.database)
    # As app_init --prod does: add the columns a test database from an older version lacks, then the schema
    migrate_schema(db.engine, logging.getLogger("chats-test"))
    db.init_tables()
    past_chats.db = knowledge_base.db = db  # The stores' database; the tools call the stores
    try:
        return asyncio.run(run())
    finally:
        db.close_all()


if __name__ == "__main__":
    sys.exit(main())
