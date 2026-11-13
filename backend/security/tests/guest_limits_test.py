#!/usr/bin/env python3
"""
Test of what guests may use (backend/security/guest_limits.py, docs/authentication.md) and of the
other protections of a public server, through the real app (FastAPI's test client, with its
middleware) and a real Postgres.

Covers: the address a guest is counted under (IPv4, IPv6 as its /64 network); the counter in the
database (the limit holds for requests that arrive together, it starts again after its window, a
refused request doesn't move it, used-up counters are deleted); the limits of the endpoints:
answers (generate, send-and-generate, regenerate, stream-generate), titles, speech (only new
speech counts), uploads (per file, at most 10 at once, a file's size, all guests' files together),
stored conversations and messages (their number and size, renames included), guest logins; that
signed-in users are not limited; that one address's use doesn't count for another; that a guest's
session is not renewed for ever; what a failed answer or tool tells a guest and a signed-in user; that logins and logout only work from the app's own pages; that the session
is not in a login's response; and the largest request body.

It creates the database <POSTGRES_DB>_guest_test if needed (or --database, whose name must contain
"test"), so it never touches the real database:

    python backend/security/tests/guest_limits_test.py

Exit code 0 if every check passed.
"""
import argparse
import io
import json
import logging
import os
import sys
import tempfile
import threading
import traceback
from datetime import datetime, timedelta, UTC
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import dotenv_values, find_dotenv  # noqa: E402

ORIGIN = "https://chat.test"
SECRET = "http://model-server.internal:8090 answered: bad key sk-test-1234"


def configure(database: str) -> None:
    """The backend's settings for this test, set before it reads its configuration."""
    os.environ.update({
        "POSTGRES_DB": database,
        "DATABASE_URL": "",
        "AUTH_MODE": "mock",              # Signed-in users through the mock login
        "CORS_ORIGINS": ORIGIN,
        "FRONTEND_URL": ORIGIN,
        "USE_DEV_CERTS": "False",
        "FILES_DIR": tempfile.mkdtemp(prefix="guest-test-files-"),
        "FILESYSTEM_PATH": tempfile.mkdtemp(prefix="guest-test-filesystem-"),
        "MODEL_CATALOG_FILE": "",
        "MEMORY_REVIEW_ENABLED": "false",
        "GUEST_LIMIT_HOURS": "3",
        "GUEST_MAX_ANSWERS": "5",
        "GUEST_MAX_LOGINS": "8",
        "GUEST_MAX_TITLES": "3",
        "GUEST_MAX_SPEECH": "2",
        "GUEST_MAX_UPLOADS": "4",
        "GUEST_MAX_WRITES": "12",
        "GUEST_MAX_REQUEST_KB": "8",
        "GUEST_FILES_MAX_MB": "1",
        "MAX_REQUEST_MB": "1",
    })


# Set by main(), once the backend is imported
app = None
db = None
messages_api = None
guest_limits = None
_addresses = iter(range(1, 250))


class Visitor:
    """A browser: a test client with its own address, cookies and CSRF header."""

    def __init__(self, address: str = None):
        from fastapi.testclient import TestClient
        self.address = address or f"198.51.100.{next(_addresses)}"
        # https, or the client would not send the Secure cookies back
        self.client = TestClient(app, base_url="https://testserver", client=(self.address, 50000))
        self.user = None

    def headers(self, extra: dict = None) -> dict:
        headers = {"Origin": ORIGIN}
        token = self.client.cookies.get("csrf_token")
        if token:
            headers["X-CSRF-Token"] = token
        headers.update(extra or {})
        return headers

    def post(self, path: str, **kwargs):
        return self.client.post(path, headers=self.headers(kwargs.pop("headers", None)), **kwargs)

    def patch(self, path: str, **kwargs):
        return self.client.patch(path, headers=self.headers(kwargs.pop("headers", None)), **kwargs)

    def get(self, path: str, **kwargs):
        return self.client.get(path, **kwargs)

    def guest(self) -> "Visitor":
        response = self.post("/api/auth/guest-login")
        assert response.status_code == 200, response.text
        self.user = response.json()["user"]
        return self

    def login(self, email: str) -> "Visitor":
        response = self.post("/api/auth/mock-login", json={"email": email})
        assert response.status_code == 200, response.text
        self.user = response.json()["user"]
        return self

    def conversation(self) -> str:
        response = self.post("/api/conversation/create", json={"name": "Test", "participants": ["user", "Assistant"]})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def send(self, conversation_id: str, text: str = "Hello"):
        return self.post("/api/message/send", json={"conversationId": conversation_id, "roleName": "user",
                                                    "type": "text", "content": text})


def utcnow() -> datetime:
    """Now, as the database stores times: UTC without a time zone."""
    return datetime.now(UTC).replace(tzinfo=None)


def counter(name: str, address: str) -> int:
    row = db.get_guest_usage(f"{name}:{guest_limits.address_key(address)}")
    return row["request_count"] if row else 0


def reset() -> None:
    """Forget every counter, so each test starts with unused limits."""
    db.delete_stale_guest_usage(utcnow() + timedelta(days=1))


def fake_model(fail: bool = False):
    """Let the answering endpoints run without a model: a fixed reply, or the error of a provider."""
    from backend.llm.types import ModelConfig, Usage

    config = ModelConfig(id=None, display_name="Test model", model_id="test", provider_id=None,
                         provider_name="Test", kind="openai", base_url=None)

    async def generate_reply(*args, **kwargs):
        if fail:
            raise RuntimeError(SECRET)
        return "A reply", Usage(input_tokens=1, output_tokens=1)

    async def answer_context(*args, **kwargs):
        raise RuntimeError(SECRET)

    messages_api._resolve_model = lambda *args, **kwargs: config
    messages_api._resolve_model_or_503 = lambda *args, **kwargs: config
    messages_api.generate_reply = generate_reply
    messages_api._answer_context = answer_context  # stream-generate: fails before it calls a model


# =========================================================================
# Tests
# =========================================================================

def test_address_key():
    key = guest_limits.address_key
    assert key("203.0.113.7") == "203.0.113.7"
    assert key("2001:db8:1:2:aaaa:bbbb:cccc:dddd") == "2001:db8:1:2::/64"
    assert key("2001:db8:1:2::1") == key("2001:db8:1:2:ffff::9"), "one /64 is one guest"
    assert key("2001:db8:1:3::1") != key("2001:db8:1:2::1")
    assert key("::ffff:203.0.113.7") == "203.0.113.7", "an IPv4 address written as IPv6"
    assert key(None) == "unknown" and key("") == "unknown"
    assert key("testclient") == "testclient" and len(key("x" * 5000)) == 64


def test_counter():
    window = timedelta(hours=3)
    key = "answers:counter-test"
    for _ in range(5):
        assert db.count_guest_usage(key, 1, 5, window) is None
    starts_again = db.count_guest_usage(key, 1, 5, window)
    last = db.get_guest_usage(key)["last_request_at"]
    assert starts_again == last + window, "the time the counter starts again"
    assert db.count_guest_usage(key, 1, 5, window) == starts_again, "a refused request doesn't move it"
    assert db.get_guest_usage(key)["request_count"] == 5

    # Several at once: all or nothing
    assert db.count_guest_usage("uploads:counter-test", 3, 4, window) is None
    assert db.count_guest_usage("uploads:counter-test", 2, 4, window) is not None
    assert db.count_guest_usage("uploads:counter-test", 1, 4, window) is None
    assert db.count_guest_usage("uploads:counter-test-2", 5, 4, window) is not None, "more than the limit at once"
    assert db.get_guest_usage("uploads:counter-test-2") is None

    # After the window the counter starts again
    from sqlalchemy import update
    from backend.database.tables import guest_usage
    with db.connection() as conn:
        conn.execute(update(guest_usage).where(guest_usage.c.ip_address == key)
                     .values(last_request_at=utcnow() - window - timedelta(seconds=5)))
    assert db.count_guest_usage(key, 1, 5, window) is None
    assert db.get_guest_usage(key)["request_count"] == 1

    # Requests that arrive together can't all slip under the limit
    results = []
    barrier = threading.Barrier(40)

    def take():
        barrier.wait()
        results.append(db.count_guest_usage("answers:burst-test", 1, 5, window))
    threads = [threading.Thread(target=take) for _ in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(1 for result in results if result is None) == 5, results
    assert db.get_guest_usage("answers:burst-test")["request_count"] == 5

    # Counters that have started again are deleted, the others kept
    with db.connection() as conn:
        conn.execute(update(guest_usage).where(guest_usage.c.ip_address == "answers:burst-test")
                     .values(last_request_at=utcnow() - window - timedelta(seconds=5)))
    assert db.delete_stale_guest_usage(utcnow() - window) == 1
    assert db.get_guest_usage("answers:burst-test") is None and db.get_guest_usage(key) is not None


def test_answers():
    fake_model()
    guest = Visitor().guest()
    conversation_id = guest.conversation()
    assert guest.send(conversation_id).status_code == 201

    generate = {"conversationId": conversation_id, "roleName": "Assistant", "time": 0}
    send_and_generate = {"conversationId": conversation_id, "roleName": "user", "type": "text", "content": "Hi",
                         "generateResponse": True, "aiParticipant": "Assistant"}

    # The limit is one for all the answering endpoints
    response = guest.post("/api/message/generate", json=generate)
    assert response.status_code == 201, response.text
    answer_id = response.json()["id"]
    response = guest.post("/api/message/send-and-generate", json=send_and_generate)
    assert response.status_code == 201 and response.json()["aiMessage"]["content"] == "A reply", response.text
    response = guest.post("/api/message/regenerate", json={"id": answer_id, "conversationId": conversation_id})
    assert response.status_code == 200, response.text
    assert counter("answers", guest.address) == 3

    # A message stored without an answer is no answer
    response = guest.post("/api/message/send-and-generate", json={**send_and_generate, "generateResponse": False})
    assert response.status_code == 201 and response.json()["aiMessage"] is None, response.text
    assert counter("answers", guest.address) == 3

    for _ in range(2):
        assert guest.post("/api/message/generate", json=generate).status_code == 201
    before = db.get_message_count(conversation_id)
    for path, body in (("/api/message/generate", generate), ("/api/message/send-and-generate", send_and_generate),
                       ("/api/message/regenerate", {"id": answer_id, "conversationId": conversation_id}),
                       ("/api/message/stream-generate", {"conversationId": conversation_id}),
                       ("/api/message/summarize", {"conversationId": conversation_id})):
        response = guest.post(path, json=body)
        assert response.status_code == 429, (path, response.status_code, response.text)
        assert 0 < int(response.headers["Retry-After"]) <= 3 * 3600
        # The chat reads the time after "after"
        after = response.json()["detail"].split("after ")[1]
        assert timedelta(hours=2, minutes=59) < datetime.fromisoformat(after) - datetime.now().astimezone() \
            <= timedelta(hours=3), after
    assert db.get_message_count(conversation_id) == before, "a refused send-and-generate stores nothing"
    assert counter("answers", guest.address) == 5

    # Another session from the same address shares the limit; another address doesn't
    again = Visitor(guest.address).guest()
    assert again.post("/api/message/generate", json={"conversationId": again.conversation(),
                                                    "roleName": "Assistant", "time": 0}).status_code == 429
    other = Visitor().guest()
    other_conversation = other.conversation()
    other.send(other_conversation)
    assert other.post("/api/message/generate", json={"conversationId": other_conversation,
                                                    "roleName": "Assistant", "time": 0}).status_code == 201

    # Signed-in users are not limited, also from the guest's address
    user = Visitor(guest.address).login("guest-limits-user@example.com")
    conversation_id = user.conversation()
    user.send(conversation_id)
    for _ in range(7):
        assert user.post("/api/message/generate", json={"conversationId": conversation_id,
                                                       "roleName": "Assistant", "time": 0}).status_code == 201
    assert counter("answers", guest.address) == 5


def test_titles():
    guest = Visitor().guest()
    conversation_id = guest.conversation()
    path = f"/api/conversation/{conversation_id}/generate-title"
    for _ in range(3):
        assert guest.post(path, json={"firstMessage": "Hello there"}).status_code == 200
    assert guest.post(path, json={"firstMessage": "Hello there"}).status_code == 429
    assert counter("titles", guest.address) == 3 and counter("answers", guest.address) == 0


def test_speech():
    calls = []

    async def generate_speech(text, language, path):
        calls.append(text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"mp3")
        return b"mp3"

    async def preprocess_for_tts(text, config=None):
        return None
    messages_api.generate_speech = generate_speech
    messages_api.preprocess_for_tts = preprocess_for_tts
    messages_api.resolve_auxiliary_model = lambda *args, **kwargs: None

    guest = Visitor().guest()
    conversation_id = guest.conversation()
    ids = [guest.send(conversation_id, f"Message {n}").json()["id"] for n in range(3)]
    path = f"/api/message/tts/{conversation_id}/"
    for message_id in ids[:2]:
        response = guest.post(f"{path}{message_id}")
        assert response.status_code == 200 and response.headers["X-TTS-Cached"] == "false", response.text
    # Speech that is cached costs nothing and isn't counted
    for _ in range(3):
        response = guest.post(f"{path}{ids[0]}")
        assert response.status_code == 200 and response.headers["X-TTS-Cached"] == "true"
    assert counter("speech", guest.address) == 2 and len(calls) == 2
    assert guest.post(f"{path}{ids[2]}").status_code == 429
    assert len(calls) == 2, "no speech is made past the limit"


def png(size: int = 200) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + os.urandom(size)


def test_uploads():
    from backend.services import file_store

    guest = Visitor().guest()

    def upload(visitor, *contents, name="a.png", mime="image/png"):
        return visitor.post("/api/files/upload", files=[("files", (name, io.BytesIO(content), mime))
                                                        for content in contents])

    response = upload(guest, png(), png())
    assert response.status_code == 201 and len(response.json()) == 2, response.text
    assert counter("uploads", guest.address) == 2
    # Every file counts, and an upload over the limit stores nothing
    files_before = len(db.get_guest_file_ids())
    assert upload(guest, png(), png(), png()).status_code == 429
    assert len(db.get_guest_file_ids()) == files_before and counter("uploads", guest.address) == 2
    assert upload(guest, png(), png()).status_code == 201
    assert upload(guest, png()).status_code == 429

    # A file's size: refused by what the upload declares, before it is read
    reset()
    original = file_store.MAX_FILE_SIZE
    file_store.MAX_FILE_SIZE = 500_000  # Under MAX_REQUEST_MB of this test, so the request itself passes
    try:
        response = upload(guest, b"x" * 500_001)
        assert response.status_code == 413 and "maximum size" in response.json()["detail"], response.text
        assert upload(guest, b"x" * 400_000, name="a.bin", mime="application/octet-stream").status_code == 201
    finally:
        file_store.MAX_FILE_SIZE = original

    # Too many files at once, for everyone
    user = Visitor().login("guest-limits-user@example.com")
    assert upload(user, *[png() for _ in range(11)]).status_code == 400
    assert upload(user, *[png() for _ in range(10)]).status_code == 201, "signed-in users aren't counted"

    # All guests' files together: GUEST_FILES_MAX_MB (1 MB here), with what is made from them
    reset()
    other = Visitor().guest()
    assert upload(other, os.urandom(300_000), name="a.bin", mime="application/octet-stream").status_code == 201
    file_id = db.get_guest_file_ids()[-1]
    derived = Path(os.environ["FILES_DIR"]) / f"{file_id}_page_1.png"
    derived.write_bytes(b"x" * 400_000)  # e.g. a PDF's page
    from backend.services.file_utils import stored_bytes
    assert stored_bytes(db.get_guest_file_ids()) >= 300_000 + 400_000 + 400_000
    response = upload(other, png())
    assert response.status_code == 507, response.text
    assert counter("uploads", other.address) == 1, "a refused upload isn't counted"
    assert upload(user, png()).status_code == 201, "signed-in users can still upload"
    derived.unlink()


def test_writes():
    guest = Visitor().guest()
    conversation_id = guest.conversation()                       # 1
    for _ in range(9):                                           # 10
        assert guest.send(conversation_id).status_code == 201

    # A guest's message can only be so large (GUEST_MAX_REQUEST_KB, 8 KB here); a refused one isn't counted
    response = guest.send(conversation_id, "x" * 9000)
    assert response.status_code == 413 and "8 KB" in response.json()["detail"], response.text
    assert counter("writes", guest.address) == 10

    # Renaming a conversation is a stored change as well, with the same size
    rename = f"/api/conversation/{conversation_id}"
    assert guest.patch(rename, json={"name": "x" * 9000}).status_code == 413
    assert counter("writes", guest.address) == 10, "a request that is too large isn't counted"
    response = guest.patch(rename, json={"name": "Renamed"})
    assert response.status_code == 200 and response.json()["name"] == "Renamed", response.text  # 11

    message_id = guest.send(conversation_id).json()["id"]        # 12
    for response in (guest.send(conversation_id),
                     guest.patch(rename, json={"name": "Again"}),
                     guest.post("/api/conversation/create", json={"name": "x", "participants": []}),
                     guest.post("/api/message/insert", json={"conversationId": conversation_id,
                                                             "messageId": message_id, "roleName": "user",
                                                             "content": "More"}),
                     guest.patch("/api/message/patch", json={"id": message_id, "conversationId": conversation_id,
                                                             "content": "Changed", "version": 1})):
        assert response.status_code == 429, (response.status_code, response.text)
    assert counter("writes", guest.address) == 12

    # Signed-in users: any number, and larger than a guest's
    user = Visitor(guest.address).login("guest-limits-user@example.com")
    conversation_id = user.conversation()
    for _ in range(14):
        assert user.send(conversation_id, "x" * 9000).status_code == 201
        assert user.patch(f"/api/conversation/{conversation_id}", json={"name": "Renamed"}).status_code == 200

    # A conversation's name has a length, for everyone
    assert user.patch(f"/api/conversation/{conversation_id}", json={"name": "x" * 501}).status_code == 422
    assert user.post("/api/conversation/create", json={"name": "x" * 501, "participants": []}).status_code == 422
    assert user.patch(f"/api/conversation/{conversation_id}", json={"name": "x" * 500}).status_code == 200


def test_logins():
    visitor = Visitor()
    for _ in range(8):
        response = visitor.post("/api/auth/guest-login")
        assert response.status_code == 200, response.text
    response = visitor.post("/api/auth/guest-login")
    assert response.status_code == 429 and "after " in response.json()["detail"], response.text

    # Used-up answers don't keep a guest from starting a session: the chat tells them
    reset()
    fake_model()
    guest = Visitor().guest()
    conversation_id = guest.conversation()
    guest.send(conversation_id)
    for _ in range(5):
        guest.post("/api/message/generate", json={"conversationId": conversation_id, "roleName": "Assistant", "time": 0})
    assert Visitor(guest.address).post("/api/auth/guest-login").status_code == 200

    # The session is in the HttpOnly cookie only, not in the response for scripts to read
    visitor = Visitor()
    response = visitor.post("/api/auth/guest-login")
    session = visitor.client.cookies.get("session")
    assert session and session not in response.text and "token" not in response.json(), response.text
    assert "httponly" in response.headers["set-cookie"].lower()


def test_guest_sessions_end():
    """A guest's session is renewed only while the guest is young: a guest's data is not kept for ever."""
    from sqlalchemy import update
    from backend.database.tables import sessions, users

    def about_to_expire(visitor):
        with db.connection() as conn:
            conn.execute(update(sessions).where(sessions.c.user_id == visitor.user["id"])
                         .values(expires_at=utcnow() + timedelta(minutes=30)))

    guest = Visitor().guest()
    session = guest.client.cookies.get("session")
    assert guest.post("/api/auth/refresh-session").json()["message"] == "Session does not need refresh yet"
    about_to_expire(guest)
    response = guest.post("/api/auth/refresh-session")
    assert response.json()["message"] == "Session refreshed successfully", response.text
    renewed = guest.client.cookies.get("session")
    assert renewed != session

    # Older than GUEST_MAX_HOURS (24): the session runs out, and the cleanup deletes the guest
    about_to_expire(guest)
    with db.connection() as conn:
        conn.execute(update(users).where(users.c.id == guest.user["id"])
                     .values(created_at=utcnow() - timedelta(hours=25)))
    response = guest.post("/api/auth/refresh-session")
    assert response.status_code == 200 and "not renewed" in response.json()["message"], response.text
    assert response.json()["expires_in"] <= 1800 and guest.client.cookies.get("session") == renewed

    # A signed-in user's session is renewed whatever the user's age
    user = Visitor().login("guest-limits-user@example.com")
    about_to_expire(user)
    with db.connection() as conn:
        conn.execute(update(users).where(users.c.id == user.user["id"])
                     .values(created_at=utcnow() - timedelta(days=400)))
    assert user.post("/api/auth/refresh-session").json()["message"] == "Session refreshed successfully"


def test_own_pages_only():
    # Another site's page can't log a visitor out or swap their session for a guest's
    user = Visitor().login("guest-limits-user@example.com")
    session = user.client.cookies.get("session")
    for path in ("/api/auth/logout", "/api/auth/guest-login", "/api/auth/mock-login", "/api/auth/refresh-session"):
        for origin in ("https://evil.example", "null", "https://chat.test.evil.example"):
            response = user.client.post(path, headers={"Origin": origin}, json={"email": "x@example.com"})
            assert response.status_code == 403, (path, origin, response.status_code)
    assert user.client.cookies.get("session") == session
    assert user.get("/api/auth/me").json()["user"]["email"] == "guest-limits-user@example.com"

    # The app's own page can, and so can a script (no Origin: it has nobody's cookies to abuse)
    assert Visitor().client.post("/api/auth/guest-login").status_code == 200
    assert Visitor().client.post("/api/auth/guest-login", headers={"Origin": ORIGIN + "/"}).status_code == 200
    response = user.client.post("/api/auth/logout", headers={"Origin": ORIGIN})
    assert response.status_code == 200, response.text
    assert user.get("/api/auth/me").status_code == 401

    # Everything else still needs the CSRF token
    guest = Visitor().guest()
    response = guest.client.post("/api/conversation/create", headers={"Origin": ORIGIN},
                                 json={"name": "x", "participants": []})
    assert response.status_code == 403, response.text


def test_error_texts():
    fake_model(fail=True)

    def answers(visitor):
        conversation_id = visitor.conversation()
        visitor.send(conversation_id)
        generate = visitor.post("/api/message/generate", json={"conversationId": conversation_id,
                                                               "roleName": "Assistant", "time": 0})
        both = visitor.post("/api/message/send-and-generate", json={
            "conversationId": conversation_id, "roleName": "user", "type": "text", "content": "Hi",
            "generateResponse": True, "aiParticipant": "Assistant"})
        stream = visitor.post("/api/message/stream-generate", json={"conversationId": conversation_id})
        assert generate.status_code == 500 and both.status_code == 500 and stream.status_code == 200
        error = next(line for line in stream.text.split("\r\n\r\n") if line.startswith("event: error"))
        stored = [m for m in db.get_messages_by_conversation(conversation_id, limit=100)
                  if m.get("agent_status") == "error"]
        assert len(stored) == 1, stored
        return generate.json()["detail"], both.json()["detail"], json.loads(error.split("data: ")[1])["error"], \
            stored[0]["agent_error"]

    # A guest learns that it failed, not what the provider said
    for text in answers(Visitor().guest()):
        assert "internal" not in text and "sk-test" not in text, text
        assert text.startswith("The model could not answer"), text
    # A signed-in user gets the provider's message, which says what to fix
    for text in answers(Visitor().login("guest-limits-user@example.com")):
        assert text == SECRET, text

    # A tool that fails unexpectedly: a guest's steps say that it failed, not with which text
    import asyncio
    from backend.llm.agent_loop import _run_tool
    from backend.llm.common import ToolCall
    from backend.llm.tools import Tool, ToolError, ToolRegistry

    async def broken():
        raise ConnectionError(SECRET)

    async def refuses():
        raise ToolError("No file 'a.txt' in this conversation")
    tools = ToolRegistry([Tool("broken", "x", {"type": "object", "properties": {}}, broken),
                          Tool("refuses", "x", {"type": "object", "properties": {}}, refuses)])
    call = ToolCall(id="c1", name="broken", arguments="{}")
    output, is_error, _ = asyncio.run(_run_tool(tools, call, {}, None))
    assert is_error and SECRET in output, output
    tools.hide_errors = True  # What _answer_context sets for a guest
    output, is_error, _ = asyncio.run(_run_tool(tools, call, {}, None))
    assert is_error and output == "Error: the tool failed (ConnectionError)", output
    # What a tool reports itself is meant for the model and stays
    output, _, _ = asyncio.run(_run_tool(tools, ToolCall(id="c2", name="refuses", arguments="{}"), {}, None))
    assert output == "Error: No file 'a.txt' in this conversation", output

    # A provider's status is passed on to guests, its message isn't
    from backend.security.errors import answer_error

    class ProviderError(Exception):
        status_code = 503
    assert answer_error(ProviderError(SECRET), {"is_guest": True}) == \
        "The model could not answer (its provider returned an error 503). Please try again later."
    assert answer_error(ProviderError(SECRET), None).startswith("The model could not answer")
    assert answer_error(ProviderError(SECRET), {"is_guest": False}) == SECRET


def test_request_size():
    guest = Visitor().guest()
    user = Visitor().login("guest-limits-user@example.com")
    conversation_id = user.conversation()

    # MAX_REQUEST_MB is 1 here. A body that declares its size is refused before it is read ...
    response = user.send(conversation_id, "x" * 1_100_000)
    assert response.status_code == 413 and response.json() == {"detail": "Request too large"}, response.text
    assert response.headers.get("access-control-allow-origin") == ORIGIN, "refused inside the CORS middleware"
    assert user.send(conversation_id, "x" * 900_000).status_code == 201

    # ... and one sent in chunks, without a declared size, as soon as it has grown too large
    def chunks(total: int):
        body = json.dumps({"conversationId": conversation_id, "roleName": "user", "type": "text",
                           "content": "x" * total}).encode()
        for start in range(0, len(body), 64 * 1024):
            yield body[start:start + 64 * 1024]
    response = user.post("/api/message/send", content=chunks(1_100_000),
                         headers={"Content-Type": "application/json"})
    assert "content-length" not in response.request.headers
    assert response.status_code == 413, (response.status_code, response.text[:200])
    response = user.post("/api/message/send", content=chunks(100_000), headers={"Content-Type": "application/json"})
    assert response.status_code == 201, response.text

    # Uploads have their own, larger limit (10 files of 10 MB): 2 MB pass the 1 MB of other requests
    response = user.post("/api/files/upload", files=[("files", ("a.bin", io.BytesIO(b"x" * 2_000_000),
                                                                "application/octet-stream"))])
    assert response.status_code == 201, response.text
    # A guest's chunked message is measured too
    response = guest.post("/api/message/send", content=chunks(20_000), headers={"Content-Type": "application/json"})
    assert response.status_code in (403, 413), response.text  # Not the guest's conversation, or too large: not stored


TESTS = [
    test_address_key,
    test_counter,
    test_answers,
    test_titles,
    test_speech,
    test_uploads,
    test_writes,
    test_logins,
    test_guest_sessions_end,
    test_own_pages_only,
    test_error_texts,
    test_request_size,
]


def main() -> int:
    global app, db, messages_api, guest_limits
    env_file = dotenv_values(find_dotenv())
    base = os.environ.get("POSTGRES_DB") or env_file.get("POSTGRES_DB") or "llm_chat"
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--database", default=f"{base}_guest_test",
                        help="Test database, created if needed (default: <POSTGRES_DB>_guest_test)")
    args = parser.parse_args()
    if "test" not in args.database:
        print(f"Refusing to run against '{args.database}': the name must contain 'test'")
        return 2
    configure(args.database)

    from backend import config
    logging.disable(logging.CRITICAL)
    from backend.database.db_init import create_database_if_not_exists, migrate_schema
    create_database_if_not_exists(config.POSTGRES_HOST, config.POSTGRES_PORT, config.POSTGRES_USER,
                                  config.POSTGRES_PASSWORD, args.database, logging.getLogger("guest-test"))
    from backend.database import db as database
    from backend.main import app as backend_app
    from backend.api import messages
    from backend.security import guest_limits as limits
    app, db, messages_api, guest_limits = backend_app, database, messages, limits
    migrate_schema(db.engine, logging.getLogger("guest-test"))
    db.init_tables()

    failures = 0
    for test in TESTS:
        reset()
        try:
            test()
            print(f"PASS  {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL  {test.__name__}")
            traceback.print_exc()
    # Leave nothing behind: the test users with their conversations and files, and the counters
    reset()
    from sqlalchemy import delete
    from backend.database.tables import conversations, sessions, uploaded_files, users
    with db.connection() as conn:
        ids = [row[0] for row in conn.execute(users.select().with_only_columns(users.c.id))]
        conn.execute(delete(uploaded_files).where(uploaded_files.c.user_id.in_(ids)))
        conn.execute(delete(conversations).where(conversations.c.userId.in_(ids)))
        conn.execute(delete(sessions).where(sessions.c.user_id.in_(ids)))
    db.close_all()
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
