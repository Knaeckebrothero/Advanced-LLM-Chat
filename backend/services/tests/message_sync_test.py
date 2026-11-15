#!/usr/bin/env python3
"""
Test of the messages a browser syncs (GET /api/conversation/{id}/messages), through the real app
(FastAPI's test client) and a real Postgres.

A browser brings a conversation up to date by asking for its newest messages and merging them by
id. The request must not depend on times: a time is in seconds, an answer carries the second its
generation started in (the same as the message it answers) and is stored only when it is
complete. A browser that asked for "the messages later than my newest" in between never got the
answer.

Covers: the newest messages by id, oldest first, with an answer of the same second as its message
that is stored later; the page before a message (before_id), which never ends between a message
and its answer; the number of messages (default, limit, its bounds); a message inserted between
two others; what an agent message and a message with attachments look like; an empty
conversation; that only the owner gets a conversation's messages; and that the route of older
versions of the app still answers.

It creates the database <POSTGRES_DB>_sync_test if needed (or --database, whose name must contain
"test") and deletes its own test users, so it never touches the real database:

    python backend/services/tests/message_sync_test.py

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
TEST_EMAILS = ("sync-test-1@example.com", "sync-test-2@example.com")

# A message, and its answer 121 ms later: ids are the server's clock in milliseconds, times in seconds
SECOND = 1794741599
USER = SECOND * 1000 + 458
ANSWER = SECOND * 1000 + 579


def configure(database: str) -> None:
    """The backend's settings for this test, set before it reads its configuration."""
    os.environ.update({
        "POSTGRES_DB": database,
        "DATABASE_URL": "",
        "AUTH_MODE": "mock",
        "CORS_ORIGINS": ORIGIN,
        "FRONTEND_URL": ORIGIN,
        "USE_DEV_CERTS": "False",
        "FILES_DIR": tempfile.mkdtemp(prefix="sync-test-files-"),
        "FILESYSTEM_PATH": tempfile.mkdtemp(prefix="sync-test-filesystem-"),
        "MODEL_CATALOG_FILE": "",
        "MEMORY_REVIEW_ENABLED": "false",
    })


# Set by main(), once the backend is imported
app = None
db = None


class Browser:
    """A signed-in browser: a test client with its own cookies and CSRF header."""

    def __init__(self, email: str = None):
        from fastapi.testclient import TestClient
        # https, or the client would not send the Secure cookies back
        self.client = TestClient(app, base_url="https://testserver")
        if email:
            response = self.post("/api/auth/mock-login", json={"email": email})
            assert response.status_code == 200, response.text

    def post(self, path: str, **kwargs):
        headers = {"Origin": ORIGIN}
        token = self.client.cookies.get("csrf_token")
        if token:
            headers["X-CSRF-Token"] = token
        return self.client.post(path, headers=headers, **kwargs)

    def conversation(self) -> str:
        response = self.post("/api/conversation/create", json={"name": "Sync test", "participants": ["user", "Assistant"]})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def messages(self, conversation_id: str, **params) -> list[dict]:
        response = self.client.get(f"/api/conversation/{conversation_id}/messages", params=params)
        assert response.status_code == 200, f"{response.status_code} {response.text}"
        return response.json()

    def ids(self, conversation_id: str, **params) -> list[int]:
        return [message["id"] for message in self.messages(conversation_id, **params)]


def exchange(conversation_id: str, number: int) -> tuple[int, int]:
    """Store a message and its answer as the app does: one minute apart, each pair in one second."""
    user_id, answer_id = USER + number * 60000, ANSWER + number * 60000
    db.create_message(user_id, conversation_id, "user", f"Message {number}", user_id // 1000)
    db.create_agent_message(answer_id, conversation_id, "Assistant", user_id // 1000, f"Answer {number}", steps=[])
    return user_id, answer_id


def test_answer_stored_after_a_sync():
    """The answer shares its second with its message and is stored later: the next sync has it."""
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()

    db.create_message(USER, conversation_id, "user", "Hello", SECOND)
    assert browser.ids(conversation_id) == [USER]

    # stream-generate stamped the answer when it started, and stores it now
    db.create_agent_message(ANSWER, conversation_id, "Assistant", SECOND, "Hi there", steps=[])
    messages = browser.messages(conversation_id)
    assert [m["id"] for m in messages] == [USER, ANSWER]
    assert messages[0]["time"] == messages[1]["time"] == SECOND

    # What the browser used to ask: the messages later than its newest. The answer is not later
    old = browser.client.get(f"/api/conversation/messages/{conversation_id}/{SECOND + 60}/20",
                             params={"after_timestamp": SECOND})
    assert old.status_code == 200 and old.json() == [], old.text


def test_newest_by_id_and_the_page_before():
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    pairs = [exchange(conversation_id, number) for number in range(3)]
    all_ids = [message_id for pair in pairs for message_id in pair]

    assert browser.ids(conversation_id) == all_ids
    # The newest three start with an answer: its message, of the same second, is the page before
    assert browser.ids(conversation_id, limit=3) == all_ids[3:]
    assert browser.ids(conversation_id, limit=3, before_id=all_ids[3]) == all_ids[:3]
    assert browser.ids(conversation_id, limit=2, before_id=all_ids[3]) == all_ids[1:3]
    assert browser.ids(conversation_id, before_id=all_ids[0]) == []

    # A message inserted between two others (manual editing) has an id between theirs
    inserted = db.insert_message_next_to(conversation_id, all_ids[2], True, "system", "Be brief")
    assert all_ids[1] < inserted["id"] < all_ids[2]
    assert browser.ids(conversation_id) == [*all_ids[:2], inserted["id"], *all_ids[2:]]


def test_number_of_messages():
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    all_ids = [message_id for number in range(30) for message_id in exchange(conversation_id, number)]

    assert browser.ids(conversation_id) == all_ids[-20:]
    assert browser.ids(conversation_id, limit=50) == all_ids[-50:]
    assert browser.ids(conversation_id, limit=1) == all_ids[-1:]
    for limit in (0, -1, 51, "many"):
        response = browser.client.get(f"/api/conversation/{conversation_id}/messages", params={"limit": limit})
        assert response.status_code == 422, f"limit={limit}: {response.status_code}"


def test_what_a_message_looks_like():
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    attachments = [{"fileId": "f1", "fileName": "notes.pdf", "mimeType": "application/pdf", "fileSize": 12}]
    db.create_message(USER, conversation_id, "user", json.dumps({"content": "See this", "attachments": attachments}),
                      SECOND)
    steps = [{"id": "s1", "type": "thought", "title": "Thinking", "content": "Hm", "timestamp": ANSWER}]
    usage = {"inputTokens": 10, "outputTokens": 5, "reasoningTokens": None, "cachedInputTokens": None,
             "cost": 0.0001, "currency": "EUR"}
    db.create_agent_message(ANSWER, conversation_id, "Assistant", SECOND, "A file", steps=steps,
                            model_name="Model", usage=usage)

    message, answer = browser.messages(conversation_id)
    assert message["type"] == "text" and message["content"] == "See this", message
    assert message["attachments"] == attachments, message
    assert answer["type"] == "agent" and answer["finalResponse"] == "A file", answer
    assert answer["status"] == "complete" and answer["modelName"] == "Model", answer
    assert [step["id"] for step in answer["steps"]] == ["s1"] and answer["usage"]["cost"] == 0.0001, answer
    assert "agent_steps" not in answer and "memory_vault" not in answer, answer


def test_empty_conversation():
    browser = Browser(TEST_EMAILS[0])
    assert browser.messages(browser.conversation()) == []


def test_only_the_owner():
    owner, other = Browser(TEST_EMAILS[0]), Browser(TEST_EMAILS[1])
    conversation_id = owner.conversation()
    exchange(conversation_id, 0)

    for client in (other.client, Browser().client):
        response = client.get(f"/api/conversation/{conversation_id}/messages")
        assert response.status_code in (401, 403), f"{response.status_code} {response.text}"
        assert "Message 0" not in response.text
    assert other.client.get("/api/conversation/no-such-conversation/messages").status_code == 403
    assert len(owner.messages(conversation_id)) == 2


def test_older_app_versions_still_get_messages():
    """The route the app used before: the messages before a time, by the browser's clock."""
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    all_ids = [message_id for number in range(2) for message_id in exchange(conversation_id, number)]

    response = browser.client.get(f"/api/conversation/messages/{conversation_id}/{SECOND + 3600}/20")
    assert response.status_code == 200, response.text
    assert sorted(message["id"] for message in response.json()) == all_ids
    answer = next(message for message in response.json() if message["id"] == all_ids[1])
    assert answer["finalResponse"] == "Answer 0" and answer["status"] == "complete", answer


TESTS = [
    test_answer_stored_after_a_sync,
    test_newest_by_id_and_the_page_before,
    test_number_of_messages,
    test_what_a_message_looks_like,
    test_empty_conversation,
    test_only_the_owner,
    test_older_app_versions_still_get_messages,
]


def delete_test_users() -> None:
    """The test users with their conversations (and so their messages) and sessions."""
    from sqlalchemy import delete, select
    from backend.database.tables import conversations, sessions, users
    with db.connection() as conn:
        ids = [row[0] for row in conn.execute(select(users.c.id).where(users.c.email.in_(TEST_EMAILS)))]
        conn.execute(delete(conversations).where(conversations.c.userId.in_(ids)))
        conn.execute(delete(sessions).where(sessions.c.user_id.in_(ids)))
        conn.execute(delete(users).where(users.c.id.in_(ids)))


def main() -> int:
    global app, db
    env_file = dotenv_values(find_dotenv())
    base = os.environ.get("POSTGRES_DB") or env_file.get("POSTGRES_DB") or "llm_chat"
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--database", default=f"{base}_sync_test",
                        help="Test database, created if needed (default: <POSTGRES_DB>_sync_test)")
    args = parser.parse_args()
    if "test" not in args.database:
        print(f"Refusing to run against '{args.database}': the name must contain 'test'")
        return 2
    configure(args.database)

    from backend import config
    logging.disable(logging.CRITICAL)
    from backend.database.db_init import create_database_if_not_exists, migrate_schema
    create_database_if_not_exists(config.POSTGRES_HOST, config.POSTGRES_PORT, config.POSTGRES_USER,
                                  config.POSTGRES_PASSWORD, args.database, logging.getLogger("sync-test"))
    from backend.database import db as database
    from backend.main import app as backend_app
    app, db = backend_app, database
    migrate_schema(db.engine, logging.getLogger("sync-test"))
    db.init_tables()

    failures = 0
    for test in TESTS:
        delete_test_users()
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
