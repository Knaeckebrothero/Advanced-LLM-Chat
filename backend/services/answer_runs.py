"""
Answers that run on the server on their own (docs/background_answers.md).

An answer (stream-generate) runs as a task of its own, not as part of the HTTP request that
asked for it: a browser that is closed, a phone that locks or a network that drops only stops
watching, and the answer is written to its end and stored as before. Only Stop
(POST /api/message/stop) stops it; it keeps what was written so far.

The task puts the answer's events (message_start, step, step_delta, token, summary, done,
error) into the run's list, numbered from 1 (the SSE id of each event). Any number of streams
follow a run: the one of the request that started it, and those of browsers that come back
(GET /api/message/stream/{conversationId}), which get what was written so far at once, merged
into few events, then the rest as it comes. With the number of the last event it got, a
browser whose stream broke gets only what it missed.

One answer runs per conversation at a time. A finished run is kept for KEEP_SECONDS, so a
browser whose stream broke near the end still gets the end. Runs live in this process's memory:
the chart runs one backend replica, as the questions of MCP servers already need.

A server that shuts down waits ANSWER_SHUTDOWN_WAIT seconds for running answers, then stops
them, which keeps what was written (drain_on_shutdown()). Their streams stay open meanwhile, so
the browsers watching get the answers to their end: uvicorn waits for open connections before it
shuts the app down. sse-starlette would end its streams at a shutdown, but its hook into uvicorn
comes too late (uvicorn takes the signals before it imports the app), so watch_exit_signals()
notes the signal itself.
"""
import asyncio
import json
import logging
import signal
import threading
import time
import uuid
from typing import AsyncIterator, Callable, Optional

log = logging.getLogger(__name__)

# How long a finished run is kept for a browser that comes back for its end
KEEP_SECONDS = 120
# How long Stop waits for the stopped answer to be stored
STOP_WAIT_SECONDS = 10


class AnswerRunning(Exception):
    """The conversation has an answer that is still being written."""


class AnswerRun:
    """One answer, running or finished: its events and the task that writes them."""

    def __init__(self, conversation_id: str, user_id: int):
        self.id = uuid.uuid4().hex
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.events: list[dict] = []  # {"id", "event", "data"}, the id is the place in the list + 1
        self.task: Optional[asyncio.Task] = None
        self.finished_at: Optional[float] = None  # time.monotonic() when the task ended
        self._changed = asyncio.Event()

    @property
    def running(self) -> bool:
        return self.finished_at is None

    def emit(self, event: dict) -> None:
        """
        Add an event ({"event", "data"}) for the streams that follow. Never awaits, so it also
        works while a stopped answer is stored (its cancellation would come again at an await).
        """
        self.events.append({"id": str(len(self.events) + 1), **event})
        self._wake()

    def _wake(self) -> None:
        self._changed.set()
        self._changed = asyncio.Event()

    async def follow(self, after: int = 0) -> AsyncIterator[dict]:
        """
        The events after the one numbered `after` (0: all), merged where they can be, then the
        new ones as they come, until the run has ended. A closed stream only stops following.
        """
        position = max(0, after)
        while True:
            if position < len(self.events):
                batch = self.events[position:]
                position = len(self.events)
                for event in merged(batch):
                    yield event
                continue
            if not self.running:
                return
            changed = self._changed  # Taken after the check, so no event can come in between
            await changed.wait()


def merged(events: list[dict]) -> list[dict]:
    """
    The events with neighbouring tokens merged into one token event, and neighbouring step_delta
    events of the same step into one; a merged event has the number of the last one it holds.
    A browser that comes back gets the text written so far in a few events, not one per token.
    """
    result: list[dict] = []
    for event in events:
        last = result[-1] if result else None
        if last is not None and last["event"] == event["event"] == "token":
            result[-1] = {**event, "data": last["data"] + event["data"]}
            continue
        if last is not None and last["event"] == event["event"] == "step_delta":
            earlier, delta = json.loads(last["data"]), json.loads(event["data"])
            if earlier.get("id") == delta.get("id"):
                earlier["delta"] = earlier.get("delta", "") + delta.get("delta", "")
                result[-1] = {**event, "data": json.dumps(earlier)}
                continue
        result.append(event)
    return result


# The newest run of each conversation, running or kept for KEEP_SECONDS after its end
_runs: dict[str, AnswerRun] = {}


def current(conversation_id: str) -> Optional[AnswerRun]:
    """The conversation's running answer, or its last one if it ended less than KEEP_SECONDS ago."""
    run = _runs.get(conversation_id)
    if run is not None and not run.running and time.monotonic() - run.finished_at > KEEP_SECONDS:
        _forget(run)
        return None
    return run


def running(conversation_id: str) -> Optional[AnswerRun]:
    """The conversation's answer that is being written now, if any."""
    run = current(conversation_id)
    return run if run is not None and run.running else None


def start(conversation_id: str, user_id: int,
          produce: Callable[[AnswerRun], AsyncIterator[dict]]) -> AnswerRun:
    """
    Run an answer as a task of its own: produce(run) gives its events.

    Raises:
        AnswerRunning: The conversation has an answer that is still being written.
    """
    if running(conversation_id) is not None:
        raise AnswerRunning(conversation_id)
    run = AnswerRun(conversation_id, user_id)
    _runs[conversation_id] = run
    # The registry holds the task: the event loop keeps only a weak reference to it
    run.task = asyncio.create_task(_drive(run, produce(run)), name=f"answer-{conversation_id}")
    return run


async def _drive(run: AnswerRun, events: AsyncIterator[dict]) -> None:
    """Put the answer's events into the run until it ends, is stopped or fails."""
    try:
        async for event in events:
            run.emit(event)
    except asyncio.CancelledError:
        pass  # Stopped: the answer kept what was written (stream-generate stores it)
    except Exception as e:  # stream-generate turns its errors into error events; this is a bug
        log.error(f"Answer in {run.conversation_id} failed: {e}", exc_info=True)
    finally:
        run.finished_at = time.monotonic()
        run._wake()
        asyncio.get_running_loop().call_later(KEEP_SECONDS + 1, _forget, run)


def _forget(run: AnswerRun) -> None:
    if _runs.get(run.conversation_id) is run:
        del _runs[run.conversation_id]


async def stop(run: AnswerRun) -> bool:
    """
    Stop a running answer and wait (up to STOP_WAIT_SECONDS) until what was written is stored.

    :return: False if it had already ended.
    """
    if not run.running or run.task is None:
        return False
    run.task.cancel()
    try:
        # Shielded: a Stop request that goes away doesn't cancel the waiting run a second time
        await asyncio.wait_for(asyncio.shield(run.task), STOP_WAIT_SECONDS)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass
    return True


async def stop_conversation(conversation_id: str) -> None:
    """Stop the conversation's running answer, if any (before the conversation is deleted)."""
    run = running(conversation_id)
    if run is not None:
        await stop(run)


# Set by the exit signal (SIGTERM, SIGINT) the server got
_exit_signal = False


def watch_exit_signals() -> None:
    """
    Note the server's exit signal before uvicorn's own handler gets it, so drain_on_shutdown()
    starts at once. Called at the app's start, after uvicorn took the signals; only in the main
    thread, where signal handlers live. A signal without a handler of its own is left alone.
    """
    if threading.current_thread() is not threading.main_thread():
        return
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous = signal.getsignal(signum)
        if not callable(previous):
            continue

        def handler(sig, frame, previous=previous):
            global _exit_signal
            _exit_signal = True
            previous(sig, frame)

        signal.signal(signum, handler)


def server_closing() -> bool:
    """Whether the server got its exit signal (watch_exit_signals())."""
    return _exit_signal


async def drain_on_shutdown(wait: float, closing: Callable[[], bool] = server_closing) -> None:
    """
    Started with the app: once the server shuts down, let the running answers end (up to `wait`
    seconds), then stop the others. Their streams end with them, so uvicorn, which waits for open
    connections first, can go on and shut the app down before the platform kills the process.
    """
    while not closing():
        await asyncio.sleep(1)
    await shutdown(wait)


async def shutdown(wait: float) -> None:
    """
    At the server's shutdown: wait up to `wait` seconds for the running answers to end, then
    stop the others (they keep what was written).
    """
    tasks = [run.task for run in _runs.values() if run.running and run.task is not None]
    if not tasks:
        return
    log.info(f"Shutdown: waiting up to {wait:.0f} s for {len(tasks)} running answer(s)")
    _, pending = await asyncio.wait(tasks, timeout=wait)
    if pending:
        log.info(f"Shutdown: stopping {len(pending)} answer(s) that are still running")
        for task in pending:
            task.cancel()
        await asyncio.wait(pending, timeout=STOP_WAIT_SECONDS)
