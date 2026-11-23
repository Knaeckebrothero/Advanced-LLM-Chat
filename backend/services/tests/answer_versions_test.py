#!/usr/bin/env python3
"""
Test of the versions of an answer (docs/answer_versions.md), through the real app (FastAPI's test
client), a real Postgres and the fake OpenAI server as the model.

Regenerate writes a new version of an answer: it keeps the answer's id (its place), gets the history
and the system messages before the answer, and keeps the version shown so far. Switching swaps the
version shown with another one, with its text, steps, model, rating and tool record; deleting the
version shown shows the next one. An answer that was stopped keeps what was written, as a new
message or a new version.

Covers: a regeneration (the model doesn't see the old text, nor a system message after it; the old
version keeps its rating and tool record); switching (everything swaps, the version counter goes
up so an edit of the old text is refused, a summary that covers the answer and the cached speech
go); a third version; a failed version without text, which the next one replaces; deleting the
version shown, down to one, and the whole answer with its versions; the export and import of a
conversation with them; a regenerateId the server doesn't have and one of a user message; stopping
a new answer and a regeneration with Stop (docs/background_answers.md), also before the model
wrote anything; and that only the owner can switch or delete versions.

It creates the database <POSTGRES_DB>_versions_test if needed (or --database, whose name must
contain "test") and deletes its own test users, so it never touches the real database:

    python backend/services/tests/answer_versions_test.py

Exit code 0 if every check passed.
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
import threading
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import dotenv_values, find_dotenv  # noqa: E402

ORIGIN = "https://chat.test"
TEST_EMAILS = ("versions-test-1@example.com", "versions-test-2@example.com")

SECOND = 1794741599
QUESTION = SECOND * 1000 + 100
ANSWER = SECOND * 1000 + 300
RECORD = [{"role": "assistant", "content": None,
           "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}]},
          {"role": "tool", "tool_call_id": "call_1", "content": "a fact"},
          {"role": "assistant", "content": "The first story"}]  # A record ends with the answer's text
FILES_DIR = tempfile.mkdtemp(prefix="versions-test-files-")


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
        "FILESYSTEM_PATH": tempfile.mkdtemp(prefix="versions-test-filesystem-"),
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
        # https, or the client would not send the Secure cookies back
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

    def user(self) -> dict:
        """The signed-in user as the endpoints get it (get_current_user())."""
        from backend.security.auth import validate_session
        return validate_session(self.client.cookies.get("session"))

    def conversation(self) -> str:
        response = self.post("/api/conversation/create",
                             json={"name": "Versions test", "participants": ["user", "Assistant"]})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def messages(self, conversation_id: str) -> list[dict]:
        response = self.client.get(f"/api/conversation/{conversation_id}/messages")
        assert response.status_code == 200, f"{response.status_code} {response.text}"
        return response.json()

    def stream(self, conversation_id: str, **body) -> dict:
        """stream-generate to its end: {event: data} of the last event of each kind, and all tokens."""
        response = self.post("/api/message/stream-generate", json={"conversationId": conversation_id, **body})
        assert response.status_code == 200, f"{response.status_code} {response.text}"
        events = {}
        for event, data in sse_events(response.text):
            events[event] = data if event == "token" else json.loads(data)
        return events

    def switch(self, conversation_id: str, message_id: int, position: int):
        return self.post("/api/message/alternatives/switch",
                         json={"conversationId": conversation_id, "messageId": message_id, "position": position})

    def delete_version(self, conversation_id: str, message_id: int):
        return self.post("/api/message/alternatives/delete",
                         json={"conversationId": conversation_id, "messageId": message_id})


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


def failure(body):
    """A responder of the fake model that refuses the request (400: the SDK doesn't retry it)."""
    raise AssertionError("refused on purpose")


def sent_text(request: dict) -> str:
    """Everything a request to the model holds, as one text."""
    return json.dumps(request.get("messages", []), ensure_ascii=False)


def seed(conversation_id: str) -> None:
    """A question and its answer, which called a tool and is rated."""
    db.create_message(QUESTION, conversation_id, "user", "Tell me a story", SECOND)
    db.create_agent_message(ANSWER, conversation_id, "Assistant", SECOND, "The first story",
                            steps=[{"id": "s1", "type": "tool_call", "title": "Looking up", "content": "{}",
                                    "timestamp": ANSWER}],
                            model_id=3, model_name="Old model", tool_record=RECORD)
    db.update_message_rating(ANSWER, conversation_id, 1)


def row(message_id: int) -> dict:
    from sqlalchemy import select
    from backend.database.tables import messages
    with db.connection() as conn:
        return dict(conn.execute(select(messages).where(messages.c.id == message_id)).fetchone()._mapping)


def alternatives(message_id: int) -> list[dict]:
    """The versions not shown: [(position, content, rating, tool_record)]."""
    from sqlalchemy import select
    from backend.database.tables import message_alternatives as table
    with db.connection() as conn:
        rows = conn.execute(select(table).where(table.c.message_id == message_id).order_by(table.c.position))
        return [(r.position, r.content, r.rating, r.tool_record) for r in rows]


def regenerated(browser: Browser, conversation_id: str, text: str) -> dict:
    """Regenerate the answer with this text; the done event."""
    server.script(answer(text))
    events = browser.stream(conversation_id, regenerateId=ANSWER)
    assert not server.errors, server.errors
    assert events["message_start"]["messageId"] == ANSWER, events["message_start"]
    assert "done" in events, events
    return events["done"]


def test_regenerate_keeps_the_earlier_version():
    """A new version keeps the id, gets the history before the answer, and the old one is kept."""
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    seed(conversation_id)
    # A system message after the answer is an instruction for the answers after it, not for this one
    db.create_message(ANSWER + 50, conversation_id, "system", "Speak like a pirate", SECOND)

    server.reset()
    done = regenerated(browser, conversation_id, "The second story")
    assert (done["version"], done["alternativePosition"], done["alternativeCount"]) == (2, 2, 2), done
    request = sent_text(server.requests[0])
    assert "Tell me a story" in request and "The first story" not in request, request
    assert "pirate" not in json.dumps(server.requests[0]), "the system message after the answer was sent"

    stored = row(ANSWER)
    assert (stored["content"], stored["rating"], stored["alternative_position"]) == ("The second story", None, 2)
    assert stored["model_name"] == "Fake Kimi" and db.get_tool_record(ANSWER) is None
    assert alternatives(ANSWER) == [(1, "The first story", 1, RECORD)], alternatives(ANSWER)

    answer_json = next(m for m in browser.messages(conversation_id) if m["id"] == ANSWER)
    assert (answer_json["alternativePosition"], answer_json["alternativeCount"]) == (2, 2), answer_json
    assert [m["id"] for m in browser.messages(conversation_id)] == [QUESTION, ANSWER, ANSWER + 50]
    question_json = browser.messages(conversation_id)[0]
    assert question_json["alternativeCount"] is None

    # A new answer at the end gets the system message, as before
    server.reset()
    server.script(answer("Arr"))
    browser.stream(conversation_id)
    assert "pirate" in json.dumps(server.requests[0])


def test_switching_swaps_everything():
    """Text, steps, model, rating and tool record swap; edits of the old text are refused."""
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    seed(conversation_id)
    regenerated(browser, conversation_id, "The second story")

    # Speech of the version shown, and a summary that covers the answer
    audio = Path(FILES_DIR) / f"tts_{conversation_id}_{ANSWER}.mp3"
    text = Path(FILES_DIR) / f"tts_{conversation_id}_{ANSWER}_preprocessed_1.txt"
    other = Path(FILES_DIR) / f"tts_{conversation_id}_{ANSWER}1.mp3"  # Another message's speech stays
    for path in (audio, text, other):
        path.write_text("speech")
    db.save_conversation_summary(conversation_id, covers_until=ANSWER, message_count=2, content="Summary")

    response = browser.switch(conversation_id, ANSWER, 1)
    assert response.status_code == 200, response.text
    shown = response.json()
    assert shown["content"] == "The first story" and shown["rating"] == 1, shown
    assert shown["modelName"] == "Old model" and shown["steps"][0]["id"] == "s1", shown
    assert (shown["alternativePosition"], shown["alternativeCount"], shown["version"]) == (1, 2, 3), shown
    assert db.get_tool_record(ANSWER) == RECORD
    assert alternatives(ANSWER) == [(2, "The second story", None, None)], alternatives(ANSWER)
    assert not audio.exists() and not text.exists() and other.exists()
    assert db.get_conversation_summary(conversation_id) is None

    # The copy of the browser that still shows the second story is out of date
    patch = browser.client.patch("/api/message/patch", headers=browser.headers(), json={
        "id": ANSWER, "conversationId": conversation_id, "content": "Edited", "version": 2})
    assert patch.status_code == 409, patch.text

    # The version shown is not among the others, nor is a version that doesn't exist
    assert browser.switch(conversation_id, ANSWER, 1).status_code == 404
    assert browser.switch(conversation_id, ANSWER, 5).status_code == 404
    assert browser.switch(conversation_id, QUESTION, 1).status_code == 404

    # The next answer gets the version shown
    server.reset()
    server.script(answer("The end"))
    browser.stream(conversation_id)
    assert "The first story" in sent_text(server.requests[0])
    assert "The second story" not in sent_text(server.requests[0])


def test_more_versions_and_failed_ones():
    """A third version comes last; a failed one without text is shown, then replaced."""
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    seed(conversation_id)
    regenerated(browser, conversation_id, "The second story")
    assert browser.switch(conversation_id, ANSWER, 1).status_code == 200

    done = regenerated(browser, conversation_id, "The third story")
    assert (done["alternativePosition"], done["alternativeCount"]) == (3, 3), done
    assert [a[:2] for a in alternatives(ANSWER)] == [(1, "The first story"), (2, "The second story")]

    # A version that fails before it writes anything is shown with its error
    server.reset()
    server.script(failure)
    events = browser.stream(conversation_id, regenerateId=ANSWER)
    server.reset()
    assert "error" in events and events["error"]["messageId"] == ANSWER, events
    assert (events["error"]["alternativePosition"], events["error"]["alternativeCount"]) == (4, 4), events
    assert row(ANSWER)["agent_status"] == "error"

    # The next version takes its place
    done = regenerated(browser, conversation_id, "The fourth story")
    assert (done["alternativePosition"], done["alternativeCount"]) == (4, 4), done
    assert [a[1] for a in alternatives(ANSWER)] == ["The first story", "The second story", "The third story"]


def test_deleting_versions():
    """Deleting the version shown shows the next one (the previous one after the last), down to one."""
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    seed(conversation_id)
    regenerated(browser, conversation_id, "B")
    regenerated(browser, conversation_id, "C")
    assert browser.switch(conversation_id, ANSWER, 2).status_code == 200

    response = browser.delete_version(conversation_id, ANSWER)
    assert response.status_code == 200, response.text
    shown = response.json()
    assert (shown["content"], shown["alternativePosition"], shown["alternativeCount"]) == ("C", 2, 2), shown
    assert [a[:2] for a in alternatives(ANSWER)] == [(1, "The first story")]

    shown = browser.delete_version(conversation_id, ANSWER).json()
    assert (shown["content"], shown["alternativePosition"], shown["alternativeCount"]) == \
        ("The first story", None, None), shown
    assert shown["rating"] == 1 and db.get_tool_record(ANSWER) == RECORD
    assert alternatives(ANSWER) == [] and row(ANSWER)["alternative_position"] is None

    # The last version is deleted with the message
    assert browser.delete_version(conversation_id, ANSWER).status_code == 404

    # Deleting an answer deletes its versions
    regenerated(browser, conversation_id, "D")
    response = browser.client.delete(f"/api/message/delete/{conversation_id}/{ANSWER}", headers=browser.headers())
    assert response.status_code == 204, response.text
    assert alternatives(ANSWER) == []


def test_export_and_import():
    """A conversation file keeps the versions and which one is shown."""
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    seed(conversation_id)
    regenerated(browser, conversation_id, "The second story")
    assert browser.switch(conversation_id, ANSWER, 1).status_code == 200

    exported = browser.client.get(f"/api/conversation/{conversation_id}/export").json()
    answer_entry = exported["messages"][1]
    assert answer_entry["content"] == "The first story" and answer_entry["alternativePosition"] == 1, answer_entry
    assert [v["content"] for v in answer_entry["alternatives"]] == ["The second story"], answer_entry
    assert answer_entry["alternatives"][0]["modelName"] == "Fake Kimi"

    response = browser.post("/api/conversation/import", json=exported)
    assert response.status_code == 201, response.text
    imported = browser.messages(response.json()["id"])
    assert imported[1]["content"] == "The first story", imported
    assert (imported[1]["alternativePosition"], imported[1]["alternativeCount"]) == (1, 2), imported[1]
    assert alternatives(imported[1]["id"])[0][1] == "The second story"

    # Versions of a user message, and a version that isn't there, are refused
    wrong = json.loads(json.dumps(exported))
    wrong["messages"][0]["alternatives"] = [{"time": "2026-01-01T00:00:00Z", "content": "x"}]
    assert browser.post("/api/conversation/import", json=wrong).status_code == 400
    wrong = json.loads(json.dumps(exported))
    wrong["messages"][1]["alternativePosition"] = 3
    assert browser.post("/api/conversation/import", json=wrong).status_code == 400


def test_what_can_be_regenerated():
    """An answer the server doesn't have gets a new one; a user message can't be regenerated."""
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    seed(conversation_id)
    server.reset()
    server.script(answer("A new answer"))
    events = browser.stream(conversation_id, regenerateId=ANSWER + 7)
    new_id = events["message_start"]["messageId"]
    assert new_id not in (ANSWER, ANSWER + 7) and events["done"]["alternativeCount"] is None, events
    assert row(new_id)["content"] == "A new answer"

    response = browser.post("/api/message/stream-generate",
                            json={"conversationId": conversation_id, "regenerateId": QUESTION})
    assert response.status_code == 400, response.text


class HeldAnswer:
    """A responder that writes one piece of text, then waits until it is released."""

    def __init__(self, first: str = None):
        self.first = first
        self.release = threading.Event()

    def __call__(self, body):
        from backend.llm.tests.fake_openai_server import chunk
        if self.first is not None:
            yield chunk(content=self.first)
        self.release.wait(10)


async def stop(browser: Browser, conversation_id: str, regenerate: bool = False, first: str = "Once upon") -> None:
    """
    Start an answer, then stop it with Stop (POST /api/message/stop, docs/background_answers.md)
    while the model call waits for more; closing the stream would not stop it.
    """
    from backend.api import messages as messages_api
    from backend.models.message import StopAnswerRequest, StreamGenerateRequest
    held = HeldAnswer(first)
    server.reset()
    server.script(held)
    request = StreamGenerateRequest(conversationId=conversation_id, regenerateId=ANSWER if regenerate else None)
    response = await messages_api.stream_generate(request, current_user=browser.user(), hide=False)
    stream = response.body_iterator
    try:
        run_id = None
        async for event in stream:
            if event["event"] == "message_start":
                run_id = json.loads(event["data"])["runId"]
            if event["event"] == "token" or (first is None and run_id):
                break
        await asyncio.sleep(0.3)  # Inside the model call, waiting for more
        result = await messages_api.stop_answer(StopAnswerRequest(conversationId=conversation_id, runId=run_id),
                                                current_user=browser.user())
        assert result.stopped, result
        await stream.aclose()
    finally:
        held.release.set()


def test_stopped_answers_are_kept():
    """A stopped answer keeps what was written: as a new message, or as a new version."""
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    seed(conversation_id)

    # A new answer
    asyncio.run(stop(browser, conversation_id))
    ids = [m["id"] for m in browser.messages(conversation_id)]
    assert len(ids) == 3, ids
    kept = row(ids[2])
    assert (kept["content"], kept["agent_status"]) == ("Once upon", "complete"), kept
    db.delete_message(ids[2], conversation_id)

    # A regeneration
    asyncio.run(stop(browser, conversation_id, regenerate=True))
    kept = row(ANSWER)
    assert (kept["content"], kept["alternative_position"]) == ("Once upon", 2), kept
    assert alternatives(ANSWER)[0][1] == "The first story"

    # Stopped before the model wrote anything: nothing changes
    asyncio.run(stop(browser, conversation_id, regenerate=True, first=None))
    assert row(ANSWER)["content"] == "Once upon" and len(alternatives(ANSWER)) == 1
    assert len(browser.messages(conversation_id)) == 2


def test_only_the_owner():
    """Another user can neither switch nor delete the versions of someone's answer."""
    owner = Browser(TEST_EMAILS[0])
    conversation_id = owner.conversation()
    seed(conversation_id)
    regenerated(owner, conversation_id, "The second story")
    stranger = Browser(TEST_EMAILS[1])
    assert stranger.switch(conversation_id, ANSWER, 1).status_code == 403
    assert stranger.delete_version(conversation_id, ANSWER).status_code == 403
    response = stranger.post("/api/message/stream-generate",
                             json={"conversationId": conversation_id, "regenerateId": ANSWER})
    assert response.status_code == 403
    assert row(ANSWER)["content"] == "The second story"


TESTS = [
    test_regenerate_keeps_the_earlier_version,
    test_switching_swaps_everything,
    test_more_versions_and_failed_ones,
    test_deleting_versions,
    test_export_and_import,
    test_what_can_be_regenerated,
    test_stopped_answers_are_kept,
    test_only_the_owner,
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
    global app, db, server
    env_file = dotenv_values(find_dotenv())
    base = os.environ.get("POSTGRES_DB") or env_file.get("POSTGRES_DB") or "llm_chat"
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--database", default=f"{base}_versions_test",
                        help="Test database, created if needed (default: <POSTGRES_DB>_versions_test)")
    args = parser.parse_args()
    if "test" not in args.database:
        print(f"Refusing to run against '{args.database}': the name must contain 'test'")
        return 2
    configure(args.database)

    from backend import config
    logging.disable(logging.CRITICAL)
    from backend.database.db_init import create_database_if_not_exists, migrate_schema
    create_database_if_not_exists(config.POSTGRES_HOST, config.POSTGRES_PORT, config.POSTGRES_USER,
                                  config.POSTGRES_PASSWORD, args.database, logging.getLogger("versions-test"))
    from backend.database import db as database
    from backend.main import app as backend_app
    from backend.api import messages as messages_api
    from backend.llm.tests.fake_openai_server import FakeOpenAIServer
    from backend.llm.tests.test_openai_loop import make_config
    app, db = backend_app, database
    migrate_schema(db.engine, logging.getLogger("versions-test"))
    db.init_tables()

    failures = 0
    with FakeOpenAIServer() as fake:
        server = fake
        fake._httpd.handle_error = lambda request, address: None  # A stopped answer closes the connection
        model = make_config(fake.base_url, supports_tools=False)
        messages_api._resolve_model = lambda user, conversation_id, model_id=None: model
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
