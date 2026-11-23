#!/usr/bin/env python3
"""
Test of the answers that run on the server on their own (docs/background_answers.md), through the
real app, a real Postgres and the fake OpenAI server as the model.

An answer runs as a task of its own: a closed stream (a browser that is closed, a phone that
locks) only stops watching it, and the answer is written to its end and stored. A browser that
comes back follows it again (GET /api/message/stream/{conversationId}) and gets what was written
so far, merged into few events, then the rest; with the run's id and the number of the last event
it got, it gets only what it missed, also of an answer that ended meanwhile. Only Stop (POST
/api/message/stop) stops an answer, which keeps what was written.

Covers: a closed stream that doesn't stop the answer; following again (all, and after a number;
tokens and reasoning merged); an answer that ended (204 without its run, the rest with it); Stop
(only the run named, what was written kept, a follower gets done with stopped, a second Stop does
nothing); one answer per conversation (409); only the owner follows and stops; deleting the
conversation stops its answer; the server's shutdown waits for running answers, then stops them,
while their streams stay open; and the routes with their query names.

It creates the database <POSTGRES_DB>_background_test if needed (or --database, whose name must
contain "test") and deletes its own test users, so it never touches the real database:

    python backend/services/tests/background_answers_test.py

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
TEST_EMAILS = ("background-test-1@example.com", "background-test-2@example.com")
SECOND = 1794741599
QUESTION = SECOND * 1000 + 100


def configure(database: str) -> None:
    """The backend's settings for this test, set before it reads its configuration."""
    os.environ.update({
        "POSTGRES_DB": database,
        "DATABASE_URL": "",
        "AUTH_MODE": "mock",
        "CORS_ORIGINS": ORIGIN,
        "FRONTEND_URL": ORIGIN,
        "USE_DEV_CERTS": "False",
        "FILES_DIR": tempfile.mkdtemp(prefix="background-test-files-"),
        "FILESYSTEM_PATH": tempfile.mkdtemp(prefix="background-test-filesystem-"),
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
        from backend.security.auth import validate_session
        self.user = validate_session(self.client.cookies.get("session"))  # As the endpoints get it

    def headers(self) -> dict:
        headers = {"Origin": ORIGIN}
        token = self.client.cookies.get("csrf_token")
        if token:
            headers["X-CSRF-Token"] = token
        return headers

    def post(self, path: str, **kwargs):
        return self.client.post(path, headers=self.headers(), **kwargs)

    def conversation(self) -> str:
        """A new conversation with a question in it."""
        response = self.post("/api/conversation/create",
                             json={"name": "Background test", "participants": ["user", "Assistant"]})
        assert response.status_code == 201, response.text
        conversation_id = response.json()["id"]
        global QUESTION
        QUESTION += 1  # Message ids are unique across conversations
        db.create_message(QUESTION, conversation_id, "user", "Tell me a story", SECOND)
        return conversation_id


def sse_events(text: str) -> list[tuple[str, str, str]]:
    """The (id, event, data) of an SSE body."""
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        lines = block.strip().splitlines()
        event = next((line[6:].strip() for line in lines if line.startswith("event:")), None)
        number = next((line[3:].strip() for line in lines if line.startswith("id:")), None)
        data = "\n".join(line[5:].lstrip() for line in lines if line.startswith("data:"))
        if event:
            events.append((number, event, data))
    return events


class HeldAnswer:
    """A responder of the fake model: writes `before`, waits until released, then writes `after`."""

    def __init__(self, before=("Once upon",), after=(" a time",), reasoning=()):
        self.before, self.after, self.reasoning = before, after, reasoning
        self.release = threading.Event()

    def __call__(self, body):
        from backend.llm.tests.fake_openai_server import chunk, usage_chunk
        for text in self.reasoning:
            yield chunk(reasoning_content=text)
        for text in self.before:
            yield chunk(content=text)
        self.release.wait(10)
        for text in self.after:
            yield chunk(content=text)
        yield chunk(finish_reason="stop")
        yield usage_chunk(10, 3)


def held(**kwargs) -> HeldAnswer:
    answer = HeldAnswer(**kwargs)
    server.reset()
    server.script(answer)
    return answer


async def start(browser: Browser, conversation_id: str, **body):
    """stream-generate: its stream (the follower of the run) and the run's id from message_start."""
    from backend.api import messages as messages_api
    from backend.models.message import StreamGenerateRequest
    request = StreamGenerateRequest(conversationId=conversation_id, **body)
    response = await messages_api.stream_generate(request, current_user=browser.user, hide=False)
    stream = response.body_iterator
    first = await anext(stream)
    assert first["event"] == "message_start" and first["id"] == "1", first
    return stream, json.loads(first["data"])["runId"]


async def read_until(stream, kind: str) -> list[dict]:
    """The events of a stream up to the first one of this kind (within 10 s)."""
    async def read():
        events = []
        async for event in stream:
            events.append(event)
            if event["event"] == kind:
                return events
        raise AssertionError(f"the stream ended without {kind}: {events}")
    return await asyncio.wait_for(read(), 10)


async def follow(browser: Browser, conversation_id: str, run_id=None, after: int = 0):
    """GET /api/message/stream/{id}: the stream, or None for 204."""
    from backend.api import messages as messages_api
    response = await messages_api.follow_answer(conversation_id, run_id=run_id, after=after,
                                                current_user=browser.user)
    if response.status_code == 204:
        return None
    return response.body_iterator


async def stop(browser: Browser, conversation_id: str, run_id=None) -> bool:
    from backend.api import messages as messages_api
    from backend.models.message import StopAnswerRequest
    result = await messages_api.stop_answer(StopAnswerRequest(conversationId=conversation_id, runId=run_id),
                                            current_user=browser.user)
    return result.stopped


async def ended(conversation_id: str) -> None:
    """Wait until the conversation's answer has ended."""
    from backend.services import answer_runs
    run = answer_runs.current(conversation_id)
    assert run is not None
    await asyncio.wait_for(asyncio.shield(run.task), 10)


def answers(conversation_id: str) -> list[tuple[str, str]]:
    """The stored answers: [(content, status)]."""
    from sqlalchemy import select
    from backend.database.tables import messages
    with db.connection() as conn:
        rows = conn.execute(select(messages.c.content, messages.c.agent_status)
                            .where(messages.c.conversationId == conversation_id)
                            .where(messages.c.roleName != "user").order_by(messages.c.id))
        return [(r.content, r.agent_status) for r in rows]


def test_a_closed_stream_doesnt_stop_the_answer():
    """The browser goes away after the first words; the answer is written to its end and stored."""
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    answer = held()

    async def run():
        stream, _ = await start(browser, conversation_id)
        await read_until(stream, "token")
        await stream.aclose()  # The phone locks
        await asyncio.sleep(0.2)
        answer.release.set()
        await ended(conversation_id)

    try:
        asyncio.run(run())
    finally:
        answer.release.set()
    assert not server.errors, server.errors
    assert answers(conversation_id) == [("Once upon a time", "complete")], answers(conversation_id)


def test_following_again():
    """A browser that comes back gets what was written so far in few events, then the rest."""
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    answer = held(before=("Once", " upon", " a"), after=(" time", "."), reasoning=("Let me ", "think"))

    async def run():
        stream, run_id = await start(browser, conversation_id)
        first = await read_until(stream, "token")
        await asyncio.sleep(0.3)  # The other tokens arrive
        await stream.aclose()

        # Back without the run's id: everything so far, merged
        again = await follow(browser, conversation_id)
        events = []
        while True:
            event = await asyncio.wait_for(anext(again), 5)
            events.append(event)
            if event["event"] == "token":
                break
        kinds = [e["event"] for e in events]
        assert kinds[0] == "message_start" and kinds.count("token") == 1, kinds
        assert events[-1]["data"] == "Once upon a", events
        deltas = [json.loads(e["data"])["delta"] for e in events if e["event"] == "step_delta"]
        assert deltas == ["Let me think"], events
        numbers = [int(e["id"]) for e in events]
        assert numbers == sorted(numbers) and numbers[-1] > len(events), numbers  # Merged: fewer events
        last = numbers[-1]

        # Another browser with the run's id and the last number it got: only what it missed (the
        # first stream may have got some of the tokens merged already)
        after = await follow(browser, conversation_id, run_id=run_id, after=int(first[-1]["id"]))
        got = "".join(e["data"] for e in first if e["event"] == "token")
        assert "Once upon a".startswith(got) and got, first
        if got != "Once upon a":
            missed = await asyncio.wait_for(anext(after), 5)
            assert missed["event"] == "token" and missed["data"] == "Once upon a"[len(got):], (got, missed)

        answer.release.set()
        rest = await read_until(again, "done")
        text = "".join(e["data"] for e in rest if e["event"] == "token")
        assert text == " time.", rest
        assert all(int(e["id"]) > last for e in rest), rest
        assert rest[-1]["event"] == "done" and "stopped" not in json.loads(rest[-1]["data"])
        await read_until(after, "done")
        assert await anext(again, None) is None  # The stream ends with the answer

    try:
        asyncio.run(run())
    finally:
        answer.release.set()
    assert answers(conversation_id) == [("Once upon a time.", "complete")]


def test_an_answer_that_ended():
    """Without its run's id nothing is followed; with it, the rest of the answer, for a while."""
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    answer = held()

    async def run():
        stream, run_id = await start(browser, conversation_id)
        await read_until(stream, "token")
        await stream.aclose()
        answer.release.set()
        await ended(conversation_id)

        assert await follow(browser, conversation_id) is None  # 204: the next sync brings it
        assert await follow(browser, conversation_id, run_id="another") is None
        rest = await follow(browser, conversation_id, run_id=run_id, after=2)
        events = await read_until(rest, "done")
        assert "".join(e["data"] for e in events if e["event"] == "token") == " a time", events
        assert await anext(rest, None) is None

    try:
        asyncio.run(run())
    finally:
        answer.release.set()


def test_stop():
    """Stop stops only the run it names, keeps what was written and tells the followers."""
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    answer = held()

    async def run():
        stream, run_id = await start(browser, conversation_id)
        await read_until(stream, "token")
        watcher = await follow(browser, conversation_id)  # Another device
        await asyncio.sleep(0.2)  # Inside the model call, waiting for more

        assert not await stop(browser, conversation_id, run_id="an older one")
        assert await stop(browser, conversation_id, run_id=run_id)
        done = (await read_until(watcher, "done"))[-1]
        data = json.loads(done["data"])
        assert data["stopped"] is True and data["messageId"] > 0, data
        assert await anext(watcher, None) is None
        assert not await stop(browser, conversation_id, run_id=run_id)  # Twice does nothing
        assert not await stop(browser, conversation_id)
        await stream.aclose()

    try:
        asyncio.run(run())
    finally:
        answer.release.set()
    assert answers(conversation_id) == [("Once upon", "complete")], answers(conversation_id)


def test_one_answer_per_conversation():
    """A second answer while one is written is refused (409); once it ended, the next one runs."""
    from fastapi import HTTPException
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    other_conversation = browser.conversation()
    answer = held()

    async def run():
        stream, _ = await start(browser, conversation_id)
        await read_until(stream, "token")
        try:
            await start(browser, conversation_id)
            raise AssertionError("a second answer started")
        except HTTPException as e:
            assert e.status_code == 409, e
        # Another conversation answers meanwhile
        second = HeldAnswer(before=("Hi",), after=())
        second.release.set()
        server.script(second)
        other, _ = await start(browser, other_conversation)
        await read_until(other, "done")
        answer.release.set()
        await read_until(stream, "done")

        server.script(HeldAnswer(before=("Again",), after=()))
        server._responders[-1].release.set()
        again, _ = await start(browser, conversation_id)
        await read_until(again, "done")

    try:
        asyncio.run(run())
    finally:
        answer.release.set()
    assert [a[0] for a in answers(conversation_id)] == ["Once upon a time", "Again"]
    assert answers(other_conversation) == [("Hi", "complete")]


def test_only_the_owner():
    """Another user can neither follow nor stop someone's answer."""
    from fastapi import HTTPException
    owner, stranger = Browser(TEST_EMAILS[0]), Browser(TEST_EMAILS[1])
    conversation_id = owner.conversation()
    answer = held()

    async def run():
        stream, run_id = await start(owner, conversation_id)
        await read_until(stream, "token")
        for attempt in (follow(stranger, conversation_id), follow(stranger, conversation_id, run_id=run_id),
                        stop(stranger, conversation_id, run_id=run_id)):
            try:
                await attempt
                raise AssertionError("a stranger got in")
            except HTTPException as e:
                assert e.status_code == 403, e
        answer.release.set()
        await read_until(stream, "done")

    try:
        asyncio.run(run())
    finally:
        answer.release.set()
    assert answers(conversation_id) == [("Once upon a time", "complete")]


def test_deleting_the_conversation_stops_its_answer():
    from backend.api import conversations as conversations_api
    from backend.services import answer_runs
    browser = Browser(TEST_EMAILS[0])
    conversation_id = browser.conversation()
    answer = held()

    async def run():
        stream, _ = await start(browser, conversation_id)
        await read_until(stream, "token")
        await stream.aclose()
        await conversations_api.delete_conversation(conversation_id, current_user=browser.user)
        assert answer_runs.running(conversation_id) is None

    try:
        asyncio.run(run())
    finally:
        answer.release.set()
    assert answers(conversation_id) == []
    assert db.get_conversation_owner(conversation_id) is None


def test_shutdown_waits_then_stops():
    """
    At shutdown an answer that ends in time is stored whole, one that doesn't keeps what was
    written; their streams stay open meanwhile and end with the answers.
    """
    from backend.services import answer_runs
    browser = Browser(TEST_EMAILS[0])
    quick, slow = browser.conversation(), browser.conversation()
    server.reset()
    quick_answer, slow_answer = HeldAnswer(), HeldAnswer(before=("Slowly",), after=(" done",))
    server.script(quick_answer, slow_answer)
    closing = threading.Event()  # uvicorn's exit signal

    async def run():
        first, _ = await start(browser, quick)
        await read_until(first, "token")
        second, _ = await start(browser, slow)
        await read_until(second, "token")
        drain = asyncio.create_task(answer_runs.drain_on_shutdown(1.5, closing=closing.is_set))
        await asyncio.sleep(1.2)
        assert answer_runs.running(quick) and answer_runs.running(slow)  # Nothing happens before the signal
        closing.set()
        threading.Timer(0.3, quick_answer.release.set).start()
        # The streams stay open and get the answers to their end
        rest = await read_until(first, "done")
        assert "".join(e["data"] for e in rest if e["event"] == "token") == " a time", rest
        stopped = (await read_until(second, "done"))[-1]
        assert json.loads(stopped["data"]).get("stopped") is True, stopped
        await asyncio.wait_for(drain, 10)
        assert answer_runs.running(quick) is None and answer_runs.running(slow) is None

    try:
        asyncio.run(run())
    finally:
        quick_answer.release.set()
        slow_answer.release.set()
    assert answers(quick) == [("Once upon a time", "complete")], answers(quick)
    assert answers(slow) == [("Slowly", "complete")], answers(slow)


def test_merged():
    from backend.services.answer_runs import merged
    events = [{"id": "1", "event": "message_start", "data": "{}"},
              {"id": "2", "event": "step_delta", "data": json.dumps({"id": "r", "delta": "Let "})},
              {"id": "3", "event": "step_delta", "data": json.dumps({"id": "r", "delta": "me"})},
              {"id": "4", "event": "step_delta", "data": json.dumps({"id": "s", "delta": "x"})},
              {"id": "5", "event": "token", "data": "Hello"},
              {"id": "6", "event": "token", "data": " world\n"},
              {"id": "7", "event": "step", "data": "{}"},
              {"id": "8", "event": "token", "data": "!"}]
    result = merged(events)
    assert [(e["id"], e["event"]) for e in result] == [("1", "message_start"), ("3", "step_delta"),
                                                       ("4", "step_delta"), ("6", "token"), ("7", "step"),
                                                       ("8", "token")], result
    assert json.loads(result[1]["data"]) == {"id": "r", "delta": "Let me"}
    assert result[3]["data"] == "Hello world\n"


def test_routes():
    """The endpoints through HTTP: their paths, query names, the 204 and the SSE ids."""
    browser, stranger = Browser(TEST_EMAILS[0]), Browser(TEST_EMAILS[1])
    conversation_id = browser.conversation()
    answer = held()
    answer.release.set()
    response = browser.post("/api/message/stream-generate?ngsw-bypass=true", json={"conversationId": conversation_id})
    assert response.status_code == 200, response.text
    events = sse_events(response.text)
    numbers = [int(n) for n, _, _ in events]  # Tokens a slow reader missed come merged
    assert numbers[0] == 1 and numbers == sorted(set(numbers)), events
    run_id = json.loads(events[0][2])["runId"]

    assert browser.client.get(f"/api/message/stream/{conversation_id}").status_code == 204
    again = browser.client.get(f"/api/message/stream/{conversation_id}?runId={run_id}&after=1&ngsw-bypass=true")
    assert again.status_code == 200, again.text
    replay = sse_events(again.text)
    assert replay[0][1] != "message_start" and replay[-1][1] == "done", replay
    assert "".join(d for _, e, d in replay if e == "token") == "Once upon a time", replay
    assert stranger.client.get(f"/api/message/stream/{conversation_id}?runId={run_id}").status_code == 403

    stopped = browser.post("/api/message/stop", json={"conversationId": conversation_id, "runId": run_id})
    assert stopped.status_code == 200 and stopped.json() == {"stopped": False}, stopped.text
    assert stranger.post("/api/message/stop", json={"conversationId": conversation_id}).status_code == 403


TESTS = [
    test_a_closed_stream_doesnt_stop_the_answer,
    test_following_again,
    test_an_answer_that_ended,
    test_stop,
    test_one_answer_per_conversation,
    test_only_the_owner,
    test_deleting_the_conversation_stops_its_answer,
    test_shutdown_waits_then_stops,
    test_merged,
    test_routes,
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
    parser.add_argument("--database", default=f"{base}_background_test",
                        help="Test database, created if needed (default: <POSTGRES_DB>_background_test)")
    args = parser.parse_args()
    if "test" not in args.database:
        print(f"Refusing to run against '{args.database}': the name must contain 'test'")
        return 2
    configure(args.database)

    from backend import config
    logging.disable(logging.CRITICAL)
    from backend.database.db_init import create_database_if_not_exists, migrate_schema
    create_database_if_not_exists(config.POSTGRES_HOST, config.POSTGRES_PORT, config.POSTGRES_USER,
                                  config.POSTGRES_PASSWORD, args.database, logging.getLogger("background-test"))
    from backend.database import db as database
    from backend.main import app as backend_app
    from backend.api import messages as messages_api
    from backend.llm.tests.fake_openai_server import FakeOpenAIServer
    from backend.llm.tests.test_openai_loop import make_config
    app, db = backend_app, database
    migrate_schema(db.engine, logging.getLogger("background-test"))
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
