# Versions of an answer

**Regenerate** keeps the answer it replaces. The answer gets versions, and `‹ 2/3 ›` under it switches between them. The version shown is the one the conversation goes on with: the next answers get it in their history. Built on 2026-11-21.

## What other apps do (research of 2026-11-21)

- **Versions of the newest answer only:** SillyTavern ("swipes": arrows and a swipe gesture on the last message, `swipes[]` and `swipe_id` on the message in the chat file), Gemini (arrows under the newest answer) and Character.AI. Once the chat goes on, the version chosen is final.
- **A tree of branches:** Claude, Open WebUI (`parentId`, `childrenIds`, `currentId`), LibreChat (`parentMessageId`) and ChatGPT until 2026. Every version keeps the messages that followed it, and editing your own message makes a branch too.
- **ChatGPT in 2026** replaced its inline arrows with a "See versions" button, and you continue from an old version only in a new chat. Its forum threads are full of users who want the arrows back: they had compared versions and gone on from an old one in place.
- **Common to all:** the counter sits in the row of actions under the answer. Copy and rating apply to each version, and each version shows its model.

## Decisions (2026-11-21, with the owner)

- **Arrows on every answer that has versions,** not only the newest. Switching an older answer swaps it in place: the messages after it stay as they are, as after a manual edit of its text. New versions come only from **Regenerate**, which the newest answer offers, as before.
- **No branches.** A version doesn't keep the messages that followed it, and editing your own message doesn't make versions of it. A tree would have to reach every reader of the messages: the history, the sync, the summary, the search over past chats, the memory review and the export.
- **The server stores stopped answers,** all of them, not only stopped versions. Before, a stopped answer lived only in the browser that stopped it, so the next answers didn't see what it said and other devices didn't have it.
- **Delete deletes the version shown,** and the next version is shown in its place. An answer with one version is deleted whole.

## How it is stored

- **The version shown is the message.** It is the `messages` row, with the answer's id, so with its place in the conversation. History, sync, past chats, memory review, export and summaries read `messages` as before and see only that version.
- **The other versions** are in `message_alternatives`, one row per version, under the key `(message_id, position)`. Each row holds the columns the version had as the answer (`type, content, time, rating, agent_status, agent_steps, agent_error, model_id, model_name, usage`) and its tool record (`tool_record`, the row of `message_tool_records` it had).
- **Positions:** `messages.alternative_position` is the place of the version shown, from 1 for the oldest; NULL means the answer has no other version. The positions have no gaps.
- **Deleting:** deleting the message, the messages after an edited one, or the conversation deletes the versions too (`ON DELETE CASCADE`).
- **Names:** the code calls them *alternatives*, since `messages.version` already is the counter of a message's edits.

**Regenerate** (`db.store_answer_version()`):
- The version shown moves to `message_alternatives`, and the new one becomes the message at the last position.
- A version that failed without any text is dropped instead of kept: a later version takes its place.
- The new version is unrated, its `time` is when it began, and the version counter goes up, so an edit of the old text from a stale copy is refused (409).
- A summary that covers the answer is dropped.
- A memory review that has read the answer reads it again: its mark goes back to just before the answer.
- `lastMessageAt` moves forward.

**Switching** (`db.switch_answer_alternative()`) swaps the message's columns and tool record with the version's. The version counter goes up, and a summary that covers the answer is dropped.

**Deleting the version shown** (`db.delete_answer_alternative()`) shows the next version, or the previous one if it was the last, and closes the gap. The files its tools made stay in the conversation, since they are linked to the message id (`docs/files.md`).

**Speech:** cached speech is per message id (`tts_handler`), so a switch, a new version, an edit and a deletion delete it (`delete_message_tts_cache()`).

## API

- **`POST /api/message/stream-generate` with `regenerateId`** writes a new version of that answer.
  - It keeps the answer's id: `message_start` has it as `messageId`.
  - It gets the history before the answer (`build_entries(before_message=...)`) and only the system messages before it.
  - It doesn't use a summary that covers the answer.
  - 400 for a user or system message.
  - An id the server doesn't have (an answer that only a browser has) gets a new answer with a new id. The browser then drops its copy.
- **Answer events:** `done`, and an `error` whose failed answer the server stored, carry the answer's `version`, `alternativePosition` and `alternativeCount`. The error also carries `messageId`.
- **`POST /api/message/alternatives/switch`** takes `{conversationId, messageId, position}`. **`POST /api/message/alternatives/delete`** takes `{conversationId, messageId}`.
  - Both answer with the message as the sync sends it.
  - 404 for an answer without such a version, or without another one; 403 without access.
  - They store no new data, so guests have no counter for them, as for a rating.
- **Messages** (`MessageResponse`, the sync) carry `alternativePosition` and `alternativeCount`; both are null for an answer with one version.

## Stopped answers

Stop sends `POST /api/message/stop` (`docs/background_answers.md`). Closing the stream stops nothing, since the answer runs as a task of its own. Stop cancels that task, which raises an `asyncio.CancelledError` in stream-generate's generator where it awaits.

- **What is kept:** once the model has begun (a step or text), stream-generate stores what it has with status `complete`, as a new message or a new version, and raises again. Streams that still follow the answer get `done` with `"stopped": true`. A server that shuts down does the same for the answers it no longer waits for.
- **No `await` in that handler:** anyio raises the cancellation again at every `await` in a cancelled scope. The database calls are synchronous.
- **Stopped before the model began:** nothing is stored. A regeneration then leaves the answer as it was.
- **No tool record:** `run_agent()` gives the record at its end, so later answers get only the text of a stopped answer.

**In the browser:**
- `cancelStreaming()` keeps the text it has, as before.
- After a stopped regeneration it asks the server for that message half a second after Stop has returned (the server has stored it then), and again two seconds later, until the stored version is newer than the regenerated one. Only then does it have the server's counter and versions.
- The sync replaces its copy when the server stored more text than the browser had shown.

## Frontend

- **Model:** `IMessageMetadata.alternatives` (`{position, count}`, or null) comes from the server's two fields (`Message.readAlternatives()`). It is kept in IndexedDB and compared by the sync (`serverView()`), so a version switched or regenerated on another device arrives with the next sync, as edits do (the newest 20 messages).
- **Regenerate** (`ChatStateService.regenerateMessage()`):
  - It no longer deletes the answer. The streaming message gets the answer's id at once, so the chat hides the stored copy while the new version is written (`ChatUiComponent.messages$`).
  - Stopped before the model began, the stored copy shows again.
  - An answer with a negative id (it failed before the server stored it) is deleted and answered anew, as before.
  - A stream that fails on the way (network, HTTP error) shows its error as a message of its own with a local id, so it doesn't replace the stored answer.
- **Navigator** (`ChatUiMessageComponent`, `.answer-versions`):
  - It sits first in the row of actions and is shown without hovering. The other actions wait for hover on a desktop and are always shown on a phone.
  - With a background image it sits on a small frosted backing of its own.
  - The arrows stop at both ends and are disabled while an answer is written. A failed switch says why under the message.
  - The answer's header shows the model of the version shown.
- **Where the view stands:** while the stored copy of a regenerated answer is hidden, the thread can still show it in the first check after the click. `placeTurn()` therefore waits until the thread shows exactly the messages of the list. Otherwise it took the regeneration for an answer that goes on, and put the new version at the top of the view instead of the question.

## Export and import

An answer in a conversation file can carry `alternatives` (the other versions with the fields of an answer, in order) and `alternativePosition` (`docs/conversation_file.md`). Import recreates them without tool records.

## Tests

`python backend/services/tests/answer_versions_test.py` runs against a real Postgres (`<POSTGRES_DB>_versions_test`), with the fake OpenAI server as the model. It covers:
- regeneration: the history before the answer, without a system message after it
- switching, with the counter, the summary and the speech
- a third version, and failed ones
- deleting versions
- export and import
- unknown and invalid `regenerateId`
- stopped answers, with Stop: a new answer and a regeneration inside the model call, and before the model began
- only the owner

Frontend specs: `src/app/data/objects/message.spec.ts` and `conversation.repository.sync.spec.ts`.

## Later

- **Branches,** if switching older answers in place turns out to confuse: each version with its own continuation, as in Claude and Open WebUI.
- **Arrow keys and swipe gestures** for the newest answer (SillyTavern), and regenerating an older answer, which needs the streaming message drawn in its place instead of at the end of the thread.
- **The tool record of a stopped answer:** `run_agent()` would have to give it before its end.
