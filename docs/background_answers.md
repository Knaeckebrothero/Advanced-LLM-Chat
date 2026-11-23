# Answers that run on without the browser

An answer runs on the server on its own. Closing the app, locking the phone or losing the network doesn't stop it: the answer is written to its end and stored. Opening the conversation again shows it, with everything written so far, and follows the rest live. Only the **Stop** button stops an answer.

This was the user's wish on 2026-11-23. Answers can take two minutes, and on a phone the installed app had to stay open the whole time, or the answer stopped. The user wanted the same for guests, and no notification when an answer is done.

## How it works

The code is in `backend/services/answer_runs.py`. The endpoints are in `backend/api/messages.py`.

- **A run per answer:** stream-generate starts the answer as an asyncio task of its own (`answer_runs.start()`), not as part of its HTTP request. The task puts the answer's events into the run's list. The response only follows that list (`AnswerRun.follow()`), so a closed stream stops nothing.
- **Numbered events:** every event has a number, the SSE `id:`, starting at 1. `message_start` carries the run's id (`runId`).
- **Following again:** `GET /api/message/stream/{conversationId}` gives the same stream as stream-generate. It sends what was written so far at once, then the rest as it comes.
  - **Without `runId`:** only an answer that is still running is followed. The browser uses this when a conversation opens or the app comes back.
  - **With `runId` and `after`:** `after` is the number of the last event the browser got, and only the events after it come. A finished answer is still kept `KEEP_SECONDS` (120) for this. The browser uses it when its stream broke.
  - **204:** there is nothing to follow, and the next sync brings the stored answer.
- **Merged events:** neighbouring tokens become one token event, and neighbouring `step_delta`s of the same step become one (`merged()`). A merged event has the number of the last event it holds. A browser that comes back gets a long answer in a few events, not thousands, and so does a reader that falls behind.
- **Stop:** `POST /api/message/stop` with `{conversationId, runId}` cancels the run's task. It returns once what was written is stored (`{"stopped": true}`).
  - The answer is stored as with every stop: as a message or as a new version (`docs/answer_versions.md`, "Stopped answers").
  - Streams that still follow the answer, on other devices, get `done` with `"stopped": true`.
  - With `runId`, a late Stop can't stop a newer answer. Stopping an answer that has ended does nothing (`{"stopped": false}`).
- **One answer per conversation:** stream-generate answers 409 while an answer is being written in the conversation, for example when another device started one. Other conversations can answer at the same time.
- **Only the owner** can follow or stop an answer: the conversation's ownership is checked, and so is the run's user. Open WebUI had a security advisory in 2026 for stop endpoints that didn't check this (PYSEC-2026-2714).
- **Deleting a conversation** stops its answer first, so it isn't stored after the delete.
- **Questions of MCP servers** (elicitation, `docs/mcp.md`) wait their `MCP_ELICITATION_TIMEOUT` (300 s) also without a browser. A chat that comes back shows the open question and can answer it.
- **In memory:** runs live in the backend process. That is enough for the one replica the chart runs, which the questions of MCP servers already need. Several replicas would need the runs in Postgres (`LISTEN/NOTIFY`) or Redis, as LibreChat does.

### Stopping the server

A server that stops waits `ANSWER_SHUTDOWN_WAIT` seconds (default 100) for running answers, then stops the rest, which keep what was written (`answer_runs.drain_on_shutdown()`, started in the lifespan of `backend/main.py`).
- **The streams stay open meanwhile:** the browsers watching get the answers to their end. uvicorn waits for open connections before it shuts the app down. sse-starlette would end its streams at a shutdown, but its hook into uvicorn's signal handler comes too late: uvicorn takes the signals before it imports the app.
- **The watcher:** at the app's start, `watch_exit_signals()` puts a handler of its own in front of uvicorn's for SIGTERM and SIGINT, which notes the signal and passes it on. `drain_on_shutdown()` then starts the wait at once. Found live on 2026-11-23: without it, the server waited for the open stream until the answer ended, with no limit, and an answer longer than the grace period would have been killed before it was stored.
- **uvicorn's own limit:** `start_backend.py` sets `timeout_graceful_shutdown` to `ANSWER_SHUTDOWN_WAIT` + 10 s. A connection still open after that is closed, so the app's shutdown stores the stopped answers before the process is killed.
- **The dev server:** with its own TLS, it takes up to 30 s more after the last answer before it exits (closing the TLS connections). Behind the chart's ingress the backend serves plain HTTP.

- **The chart:** `backend.terminationGracePeriodSeconds: 120`. The backend uses the `Recreate` strategy (its volume is ReadWriteOnce), so the new pod starts only after the old one is gone. An update can therefore wait up to two minutes while an answer is written.
- **docker compose:** `stop_grace_period: 2m`.
- **A server that dies** (killed, out of memory) loses the answer it was writing. Nothing is stored then. LibreChat says the same: "The response survives your connection, not the server."

## In the browser

`ChatStateService` follows at most one answer: the open conversation's (`following`).

- **Following:** `followAnswer()` asks whether an answer is being written in the open conversation. It does so when a conversation opens, when the app comes back to the foreground, and with the sync every minute, which also finds an answer another device started.
  - Nothing is shown until the answer's first event arrives, so a conversation without one doesn't flicker.
  - The answer then stands as one that was just asked for: its turn goes to the top of the view, and the Stop button shows.
  - For a new version of a stored answer (Regenerate), the stored copy is hidden as usual, since the ids match. `message_start` finds that copy, so Stop and errors treat it as a regeneration.
- **A broken stream:** the network drops, the phone locks, or the server restarts. A stream that ends without `done` or `error` is followed again with the run's id and the number of its last event (`onStreamEnd()`, `followAgain()`).
  - The attempts come after 0, 2, 5 and 10 seconds. A hidden page waits until it is visible first, since a locked phone can't hold a connection.
  - Every event that arrives starts the count again.
  - After the last failed attempt, the browser lets go of the answer. The sync and opening the conversation again bring it, or follow it again while it is written.
- **A stalled stream:** the server pings an open stream every 15 seconds. A stream that got nothing for 45 seconds is closed and followed again (`StreamingService`'s watchdog). A connection that died while the phone was locked doesn't always end on its own.
- **Another conversation or a new chat:** the browser lets go of the answer (`leaveAnswer()`), and it goes on on the server. Before, it was shown in whatever conversation was open.
- **Stop:** `cancelStreaming()` sends Stop with the run's id. It keeps the text it has, as before. After a stopped regeneration, it asks for the stored version once Stop has returned.
- **409:** the browser says that an answer is still being written in this chat (`message.answerStillRunning`) and follows that answer.
- **The service worker:** the answer requests carry `ngsw-bypass`, so Angular's service worker doesn't pass them on itself. There are reports that iOS cuts a response a service worker passes on after about 70 seconds. A query parameter is used rather than the header, which would need a CORS preflight.

## Researched (2026-11-23)

The design is the one others use:
- **The answer decoupled from the connection:** LibreChat's "resumable streams" keep running answers in memory on one instance and in Redis Streams on several. The Vercel AI SDK keeps an `activeStreamId` on the chat and resumes with a GET that answers 204 when nothing runs.
- **Numbered events:** OpenAI's background mode numbers events (`sequence_number`) and resumes with `starting_after`.
- **Stop:** the AI SDK's troubleshooting page "abort breaks resumable streams" explains why Stop needs an endpoint of its own. Its rules:
  - Only an explicit click stops, never unload or navigation.
  - Stop names its run, and stopping twice does no harm.
  - After a Stop, the app doesn't follow the answer again on its own.
- **Not needed here:** Redis or durable-stream services (one replica), saving partial answers regularly (LibreChat doesn't either), and push notifications (not wanted; Web Push could add them later).

## Tests

`python backend/services/tests/background_answers_test.py` runs against a real Postgres (`<POSTGRES_DB>_background_test`), with the fake OpenAI server as the model. It covers:
- a closed stream that doesn't stop the answer
- following again: all events, and those after a number, with tokens and reasoning merged
- an answer that ended: 204 without its run, the rest with it
- Stop: only the run it names, what was written kept, `done` with `stopped` for a follower, a second Stop does nothing
- one answer per conversation (409)
- only the owner
- deleting the conversation stops its answer
- the shutdown waits for answers, then stops them, while their streams stay open
- the routes with their query names

`answer_versions_test.py` stops answers with Stop.

Tested live on 2026-11-23 in the dev app at Android phone width with DeepSeek V4.1 Flash (the mock user `background-demo@example.com`):
- closing the page mid-answer and coming back
- a stream broken mid-answer, after which the text in the browser equals the stored one, character for character
- leaving for a new chat and back
- Stop after coming back
- Regenerate across leaving and coming back
- stopping the dev backend (SIGTERM) mid-answer: the wait started at once, the browser got the answer to its end (17,428 characters, stored), then the server stopped
