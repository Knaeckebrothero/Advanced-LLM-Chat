#!/usr/bin/env python3
"""
Test of side chats (docs/side_chats.md), through the real app (FastAPI's test client), a real
Postgres and the fake OpenAI server as the model.

A side chat is a conversation of its own, forked from a message of another one: its history is
its parent's messages up to that message, then its own, and its system prompt is its parent's.
It is kept until it is deleted, can be made a conversation of its own (which copies its parent's
messages and their files into it), and survives the deletion of the message it was forked from.

Covers: creating one (it takes the parent's agent, model, own system prompt and hidden mark; no
side chat of a side chat, of another user's conversation or at a message that isn't the
parent's); the conversation list's fields; the history (the parent's messages up to the fork with
their tool records, not the later ones, the parent's system messages up to the fork, the request
beginning as the parent's does, the parent's summary only when it covers no later message, no
summary of its own); answering while the parent's answer runs; the files it sees; deleting the
fork message and editing an earlier one; making it a conversation (copies with their tool
records, versions and files, ids before its own messages, independent of the parent from then
on); deleting a conversation with its side chats kept or deleted; the export; the search over
past chats naming the parent; hidden with the parent; and that only the owner can do any of it.

It creates the database <POSTGRES_DB>_side_test if needed (or --database, whose name must contain
"test") and deletes its own test users, so it never touches the real database:

    python backend/services/tests/side_chats_test.py

Exit code 0 if every check passed.
"""
import argparse
import json
import logging
import os
import sys
import tempfile
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import dotenv_values, find_dotenv  # noqa: E402

ORIGIN = "https://chat.test"
TEST_EMAILS = ("side-test-1@example.com", "side-test-2@example.com")
FILES_DIR = tempfile.mkdtemp(prefix="side-test-files-")

SECOND = 1794741000
Q1, S1, A1 = SECOND * 1000 + 100, SECOND * 1000 + 200, SECOND * 1000 + 300   # before the fork, A1 the fork
Q2, A2, S2 = (SECOND + 60) * 1000, (SECOND + 60) * 1000 + 300, (SECOND + 61) * 1000  # after the fork
RECORD = [{"role": "assistant", "content": None,
           "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}]},
          {"role": "tool", "tool_call_id": "call_1", "content": "a fact from the lookup"},
          {"role": "assistant", "content": "Frankfurt cases pull apart two ideas"}]


def configure(database: str) -> None:
    """The backend's settings for this test, set before it reads its configuration."""
    os.environ.update({
        "POSTGRES_DB": database,
        "DATABASE_URL": "",
        "AUTH_MODE": "mock",
        "CORS_ORIGINS": ORIGIN,
        "FRONTEND_URL": ORIGIN,
        "USE_DEV_CERTS": "False",
        "FILES_DIR": FILES_DIR,
        "FILESYSTEM_PATH": tempfile.mkdtemp(prefix="side-test-filesystem-"),
        "MODEL_CATALOG_FILE": "",
        "MEMORY_REVIEW_ENABLED": "false",
    })


# Set by main(), once the backend is imported
app = None
db = None
server = None


class Browser:
    """A signed-in browser: a test client with its own cookies and CSRF header."""

    def __init__(self, email: str):
        from fastapi.testclient import TestClient
        self.client = TestClient(app, base_url="https://testserver")
        response = self.post("/api/auth/mock-login", json={"email": email})
        assert response.status_code == 200, response.text

    def headers(self) -> dict:
        headers = {"Origin": ORIGIN}
        token = self.client.cookies.get("csrf_token")
        if token:
            headers["X-CSRF-Token"] = token
        return headers

    def post(self, path: str, **kwargs):
        return self.client.post(path, headers=self.headers(), **kwargs)

    def delete(self, path: str, **kwargs):
        return self.client.delete(path, headers=self.headers(), **kwargs)

    def user_id(self) -> int:
        from backend.security.auth import validate_session
        return validate_session(self.client.cookies.get("session"))["user_id"]

    def create(self, **body):
        return self.post("/api/conversation/create",
                         json={"name": "Side test", "participants": ["user", "Assistant"], **body})

    def conversation(self) -> str:
        response = self.create()
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def side_chat(self, parent_id: str, fork_id: int) -> str:
        response = self.create(parentId=parent_id, forkMessageId=fork_id, name="A side chat")
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def messages(self, conversation_id: str) -> list[dict]:
        response = self.client.get(f"/api/conversation/{conversation_id}/messages?limit=50")
        assert response.status_code == 200, f"{response.status_code} {response.text}"
        return response.json()

    def stream(self, conversation_id: str, **body) -> dict:
        """stream-generate to its end: {event: data} of the last event of each kind."""
        response = self.post("/api/message/stream-generate", json={"conversationId": conversation_id, **body})
        assert response.status_code == 200, f"{response.status_code} {response.text}"
        events = {}
        for event, data in sse_events(response.text):
            events[event] = data if event == "token" else json.loads(data)
        assert "done" in events, events
        return events


def sse_events(text: str) -> list[tuple[str, str]]:
    """The (event, data) pairs of an SSE body."""
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        lines = block.strip().splitlines()
        event = next((line[6:].strip() for line in lines if line.startswith("event:")), None)
        data = "\n".join(line[5:].lstrip() for line in lines if line.startswith("data:"))
        if event:
            events.append((event, data))
    return events


def answer(text: str):
    """A responder of the fake model: this text, streamed."""
    from backend.llm.tests.fake_openai_server import chunk, usage_chunk
    return lambda body: [chunk(content=text), chunk(finish_reason="stop"), usage_chunk(10, 3)]


def ask(browser: Browser, conversation_id: str, text: str, reply: str = "An answer") -> dict:
    """A user message in the conversation, answered by the fake model; the request the model got."""
    import time
    message_id = int(time.time() * 1000)
    db.create_message(message_id, conversation_id, "user", text, message_id // 1000)
    server.script(answer(reply))
    browser.stream(conversation_id)
    return server.requests[-1]


def history_text(request: dict) -> str:
    """The messages of a request to the model (without the system prompt), as one text."""
    return json.dumps([m for m in request["messages"] if m["role"] != "system"], ensure_ascii=False)


def system_text(request: dict) -> str:
    return "\n".join(m["content"] for m in request["messages"] if m["role"] == "system")


def seed(conversation_id: str, user_id: int) -> dict:
    """
    The parent: a question with a photo, an instruction, the answer (the fork, it called a tool), then
    a question and an answer after the fork (with a file of its own) and a later instruction.
    """
    from backend.services import file_store
    photo = file_store.store(b"\x89PNG fake photo", user_id, name="fox.png", mime_type="image/png")
    later = file_store.store(b"later notes", user_id, name="later.txt", mime_type="text/plain")
    db.create_message(Q1, conversation_id, "user", json.dumps({
        "content": "What is a Frankfurt case?",
        "attachments": [{"fileId": photo["file_id"], "name": "fox.png", "mimeType": "image/png"}]}), SECOND)
    db.create_message(S1, conversation_id, "system", "Answer like a patient teacher.", SECOND)
    db.create_agent_message(A1, conversation_id, "Assistant", SECOND, "Frankfurt cases pull apart two ideas",
                            steps=[{"id": "s1", "type": "tool_call", "title": "Looking up", "content": "{}",
                                    "timestamp": A1, "metadata": {"files": [{"fileId": photo["file_id"]}]}}],
                            tool_record=RECORD)
    db.create_message(Q2, conversation_id, "user", json.dumps({
        "content": "And the consequence argument?",
        "attachments": [{"fileId": later["file_id"], "name": "later.txt", "mimeType": "text/plain"}]}), SECOND + 60)
    db.create_agent_message(A2, conversation_id, "Assistant", SECOND + 60, "It goes from the past and the laws")
    db.create_message(S2, conversation_id, "system", "Now answer in rhymes.", SECOND + 61)
    return {"photo": photo["file_id"], "later": later["file_id"]}


def conversation_row(conversation_id: str) -> dict:
    return db.get_conversation_by_id(conversation_id) or {}


def file_ids(browser: Browser, conversation_id: str) -> set[str]:
    response = browser.client.get(f"/api/files?conversationId={conversation_id}")
    assert response.status_code == 200, response.text
    return {entry["fileId"] for entry in response.json()}


# =========================================================================
# The tests
# =========================================================================

def test_creating_a_side_chat():
    me, other = Browser(TEST_EMAILS[0]), Browser(TEST_EMAILS[1])
    parent = me.conversation()
    seed(parent, me.user_id())
    db.update_conversation(parent, system_prompt="You are a philosophy tutor.", hidden=True, hidden_by="user")
    side = me.side_chat(parent, A1)
    row = conversation_row(side)
    assert (row["parent_id"], row["fork_message_id"], row["side_chat"]) == (parent, A1, True), row
    assert row["system_prompt"] == "You are a philosophy tutor.", "the parent's own system prompt"
    assert row["hidden"] and row["hidden_by"] == "user", "the parent's hidden mark"

    listed = {c["id"]: c for c in me.client.get("/api/conversations").json()}
    assert listed[side]["sideChat"] is True and listed[side]["parentId"] == parent, listed[side]
    assert listed[side]["forkMessageId"] == A1
    assert listed[parent]["sideChat"] is False and listed[parent]["parentId"] is None

    # Not at a message of another conversation, not of a side chat, not of another user's conversation
    elsewhere = me.conversation()
    db.create_message(Q1 + 7, elsewhere, "user", "Elsewhere", SECOND)
    assert me.create(parentId=parent, forkMessageId=Q1 + 7).status_code == 400
    assert me.create(parentId=parent).status_code == 400
    assert me.create(parentId=side, forkMessageId=A1).status_code == 400
    assert other.create(parentId=parent, forkMessageId=A1).status_code == 404


def test_history_of_a_side_chat():
    me = Browser(TEST_EMAILS[0])
    parent = me.conversation()
    seed(parent, me.user_id())
    side = me.side_chat(parent, A1)

    request = ask(me, side, "Explain it like I'm new to philosophy")
    history = history_text(request)
    assert "What is a Frankfurt case?" in history and "a fact from the lookup" in history, \
        "the parent's messages up to the fork, with the tool calls of its answer"
    assert "Explain it like I'm new to philosophy" in history
    assert "consequence argument" not in history and "the past and the laws" not in history, \
        "nothing after the fork"
    system = system_text(request)
    assert "patient teacher" in system and "rhymes" not in system, "the parent's system messages up to the fork"

    # The side chat's own messages follow; its answers are its own
    request = ask(me, side, "And who was Frankfurt?")
    history = history_text(request)
    assert history.index("Explain it like") < history.index("An answer") < history.index("who was Frankfurt")
    assert len(me.messages(side)) == 4, "two questions and two answers of its own"
    assert len(me.messages(parent)) == 6, "the parent is unchanged"

    # The request begins as the parent's does: same system prompt and the same messages up to the fork
    db.delete_message(S2, parent)
    db.delete_message(A2, parent)
    db.delete_message(Q2, parent)
    parent_request = ask(me, parent, "Back in the main chat")
    side_request = ask(me, side, "One more on the side")
    assert parent_request["messages"][0] == side_request["messages"][0], "the same system prompt"
    fork_end = next(i for i, m in enumerate(side_request["messages"]) if m.get("content") == RECORD[-1]["content"])
    assert parent_request["messages"][:fork_end + 1] == side_request["messages"][:fork_end + 1], \
        "the same messages up to the fork"


def test_answers_while_the_parent_answers():
    from backend.services import answer_runs
    me = Browser(TEST_EMAILS[0])
    parent = me.conversation()
    seed(parent, me.user_id())
    side = me.side_chat(parent, A1)
    original = answer_runs.running
    answer_runs.running = lambda conversation_id: object() if conversation_id == parent else original(conversation_id)
    try:
        assert me.post("/api/message/stream-generate", json={"conversationId": parent}).status_code == 409
        ask(me, side, "Meanwhile, on the side")
    finally:
        answer_runs.running = original


def test_summary():
    me = Browser(TEST_EMAILS[0])
    parent = me.conversation()
    seed(parent, me.user_id())
    side = me.side_chat(parent, A1)

    # The parent's summary covers only messages up to the fork: the side chat's history starts with it
    db.save_conversation_summary(parent, Q1, 1, "SUMMARY: the user asked about a fox photo")
    history = history_text(ask(me, side, "Side question"))
    assert "SUMMARY: the user asked" in history and "What is a Frankfurt case?" not in history
    assert "Frankfurt cases pull apart" in history

    # A summary that covers a later message doesn't fit: the messages instead
    db.save_conversation_summary(parent, A2, 5, "LATER SUMMARY of the whole talk")
    history = history_text(ask(me, side, "Another side question"))
    assert "LATER SUMMARY" not in history and "What is a Frankfurt case?" in history

    # A side chat isn't summarized on request
    response = me.post("/api/message/summarize", json={"conversationId": side})
    assert response.status_code == 409, response.text
    assert db.get_conversation_summary(side) is None


def test_files_of_a_side_chat():
    me = Browser(TEST_EMAILS[0])
    parent = me.conversation()
    files = seed(parent, me.user_id())
    side = me.side_chat(parent, A1)
    seen = file_ids(me, side)
    assert files["photo"] in seen, "the parent's files up to the fork"
    assert files["later"] not in seen, "not those of later messages"
    assert file_ids(me, parent) >= {files["photo"], files["later"]}


def test_fork_message_deleted_and_earlier_edited():
    me = Browser(TEST_EMAILS[0])
    parent = me.conversation()
    seed(parent, me.user_id())
    side = me.side_chat(parent, A1)
    db.delete_message(A1, parent)
    db.update_message(Q1, parent, "What is a Frankfurt case, really?", version=1)
    assert conversation_row(side)["side_chat"], "the side chat stays"
    history = history_text(ask(me, side, "Still there?"))
    assert "Frankfurt cases pull apart" not in history, "the deleted message is gone from its context"
    assert "really?" in history, "until it is a conversation of its own, the parent is read as it is now"
    assert "consequence argument" not in history


def test_made_a_conversation():
    from backend.services import file_store
    me = Browser(TEST_EMAILS[0])
    parent = me.conversation()
    files = seed(parent, me.user_id())
    db.store_answer_version(A1, parent, SECOND + 5, "A second version of the answer")
    side = me.side_chat(parent, A1)
    ask(me, side, "Explain it simply", reply="Picture Jones and Black")

    response = me.post(f"/api/conversation/{side}/promote")
    assert response.status_code == 200, response.text
    assert response.json()["sideChat"] is False and response.json()["parentId"] == parent
    messages = me.messages(side)
    texts = [m.get("finalResponse") or m.get("content") for m in messages]
    assert texts[:3] == ["What is a Frankfurt case?", "Answer like a patient teacher.",
                         "A second version of the answer"], texts
    assert texts[3:] == ["Explain it simply", "Picture Jones and Black"], texts
    ids = [m["id"] for m in messages]
    assert ids == sorted(ids) and len(set(ids)) == len(ids), "in order, the copies before its own messages"
    assert not set(ids[:3]) & {Q1, S1, A1}, "copies with ids of their own"
    assert messages[2]["alternativeCount"] == 2, "the other version of the answer came along"
    assert conversation_row(side)["fork_message_id"] == ids[2], "it names the copy of the fork message now"

    # Its files are copies: the copied message refers to them, and they are its own
    seen = file_ids(me, side)
    assert files["photo"] not in seen and files["later"] not in seen
    copy = next(iter(seen))
    assert copy in json.dumps(messages[0]), "the copied message attaches the copy"
    assert file_store.get_file_path(copy).read_bytes() == b"\x89PNG fake photo"
    alternatives = db.get_conversation_alternatives(side)[ids[2]]
    assert db.get_tool_record(ids[2]) is None and alternatives[0]["tool_record"] == RECORD, \
        "the version that called the tool keeps its tool record"
    assert copy in json.dumps(alternatives[0]["agent_steps"]), "the copied steps refer to the copied file"

    # From now on the parent doesn't reach it: an edit, the summary, even its deletion
    db.update_message(Q1, parent, "Changed in the parent", version=1)
    history = history_text(ask(me, side, "Go on"))
    assert "What is a Frankfurt case?" in history and "Changed in the parent" not in history
    assert me.delete(f"/api/conversation/{parent}").status_code == 200
    assert len(me.messages(side)) == 7 and file_store.get_file_path(copy) is not None
    assert me.post(f"/api/conversation/{side}/promote").status_code == 200, "a conversation stays as it is"


def test_deleting_a_conversation_with_side_chats():
    me = Browser(TEST_EMAILS[0])
    for side_chats in ("keep", None, "delete"):
        parent = me.conversation()
        seed(parent, me.user_id())
        first, second = me.side_chat(parent, A1), me.side_chat(parent, Q2)
        ask(me, first, "On the side")
        query = f"?sideChats={side_chats}" if side_chats else ""
        assert me.delete(f"/api/conversation/{parent}{query}").status_code == 200
        assert db.get_conversation_by_id(parent) is None
        if side_chats == "delete":
            assert db.get_conversation_by_id(first) is None and db.get_conversation_by_id(second) is None
        else:
            # Kept as conversations of their own (also by an app that doesn't say), with the messages they need
            assert not conversation_row(first)["side_chat"] and not conversation_row(second)["side_chat"]
            assert len(me.messages(first)) == 3 + 2 and len(me.messages(second)) == 4
            history = history_text(ask(me, first, "Still here"))
            assert "What is a Frankfurt case?" in history and "On the side" in history
    assert me.delete(f"/api/conversation/{me.conversation()}?sideChats=later").status_code == 422


def test_export_and_past_chats():
    from backend.services import past_chats
    from backend.services.tools.chat_tools import _heading
    me = Browser(TEST_EMAILS[0])
    parent = me.conversation()
    seed(parent, me.user_id())
    side = me.side_chat(parent, A1)
    ask(me, side, "Explain it simply", reply="Picture Jones and Black")

    exported = me.client.get(f"/api/conversation/{side}/export").json()
    contents = [m.get("content") for m in exported["messages"]]
    assert contents[0] == "What is a Frankfurt case?" and contents[-1] == "Picture Jones and Black", contents
    assert "It goes from the past and the laws" not in contents, "with its context, nothing after the fork"

    with db.connection() as conn:
        from sqlalchemy import text
        conn.execute(text('UPDATE messages SET memory_vault = 0 WHERE "conversationId" IN (:a, :b)'),
                     {"a": parent, "b": side})
    listed = past_chats.list_chats(past_chats.Scope(me.user_id(), 0, False))["conversations"]
    entry = next(c for c in listed if c["id"] == side)
    assert entry["side_chat_of"] == {"id": parent, "title": "Side test"}, entry
    assert f"a side chat of conversation {parent}" in _heading(entry)
    assert "side_chat_of" not in next(c for c in listed if c["id"] == parent)


def test_hidden_with_its_parent():
    from backend.services import hidden_content
    from backend.catalog.resolver import conversation_hidden
    me = Browser(TEST_EMAILS[0])
    parent = me.conversation()
    seed(parent, me.user_id())
    side = me.side_chat(parent, A1)
    assert not hidden_content.conversation_is_hidden(side)
    db.update_conversation(parent, hidden=True, hidden_by="user")
    assert hidden_content.conversation_is_hidden(side), "hidden with its parent"
    assert conversation_hidden(conversation_row(side))
    assert me.post(f"/api/conversation/{side}/promote").status_code == 200
    assert not hidden_content.conversation_is_hidden(side), "a conversation of its own has its own mark"


def test_only_the_owner():
    me, other = Browser(TEST_EMAILS[0]), Browser(TEST_EMAILS[1])
    parent = me.conversation()
    seed(parent, me.user_id())
    side = me.side_chat(parent, A1)
    assert other.post(f"/api/conversation/{side}/promote").status_code == 404
    assert other.post("/api/message/stream-generate", json={"conversationId": side}).status_code == 403
    assert other.client.get(f"/api/conversation/{side}/export").status_code == 404
    assert conversation_row(side)["side_chat"]


TESTS = [
    test_creating_a_side_chat,
    test_history_of_a_side_chat,
    test_answers_while_the_parent_answers,
    test_summary,
    test_files_of_a_side_chat,
    test_fork_message_deleted_and_earlier_edited,
    test_made_a_conversation,
    test_deleting_a_conversation_with_side_chats,
    test_export_and_past_chats,
    test_hidden_with_its_parent,
    test_only_the_owner,
]


def delete_test_users() -> None:
    """The test users with their conversations (and so their messages), files and sessions."""
    from sqlalchemy import delete, select, update
    from backend.database.tables import conversations, sessions, uploaded_files, users
    with db.connection() as conn:
        ids = [row[0] for row in conn.execute(select(users.c.id).where(users.c.email.in_(TEST_EMAILS)))]
        conn.execute(update(conversations).where(conversations.c.userId.in_(ids)).values(parent_id=None))
        conn.execute(delete(conversations).where(conversations.c.userId.in_(ids)))
        conn.execute(delete(uploaded_files).where(uploaded_files.c.user_id.in_(ids)))
        conn.execute(delete(sessions).where(sessions.c.user_id.in_(ids)))
        conn.execute(delete(users).where(users.c.id.in_(ids)))


def main() -> int:
    global app, db, server
    env_file = dotenv_values(find_dotenv())
    base = os.environ.get("POSTGRES_DB") or env_file.get("POSTGRES_DB") or "llm_chat"
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--database", default=f"{base}_side_test",
                        help="Test database, created if needed (default: <POSTGRES_DB>_side_test)")
    args = parser.parse_args()
    if "test" not in args.database:
        print(f"Refusing to run against '{args.database}': the name must contain 'test'")
        return 2
    configure(args.database)

    from backend import config
    logging.disable(logging.CRITICAL)
    from backend.database.db_init import create_database_if_not_exists, migrate_schema
    create_database_if_not_exists(config.POSTGRES_HOST, config.POSTGRES_PORT, config.POSTGRES_USER,
                                  config.POSTGRES_PASSWORD, args.database, logging.getLogger("side-test"))
    from backend.database import db as database
    from backend.main import app as backend_app
    from backend.api import messages as messages_api
    from backend.llm.tests.fake_openai_server import FakeOpenAIServer
    from backend.llm.tests.test_openai_loop import make_config
    app, db = backend_app, database
    migrate_schema(db.engine, logging.getLogger("side-test"))
    db.init_tables()

    failures = 0
    with FakeOpenAIServer() as fake:
        server = fake
        model = make_config(fake.base_url, supports_tools=False)
        messages_api._resolve_model = lambda user, conversation_id, model_id=None: model
        messages_api._resolve_model_or_503 = lambda user, conversation_id, model_id=None: model
        for test in TESTS:
            delete_test_users()
            fake.reset()
            try:
                test()
                print(f"PASS  {test.__name__}")
            except Exception:
                failures += 1
                print(f"FAIL  {test.__name__}")
                traceback.print_exc()
    delete_test_users()
    db.close_all()
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
