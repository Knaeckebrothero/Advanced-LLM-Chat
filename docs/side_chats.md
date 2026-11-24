# Side chats

A side chat is a conversation on the side of another one: you fork it from a message to have something explained, an image made or a script written, without it entering the main conversation. It knows the main conversation up to that message, runs with the same agent, is kept, and can become a real conversation. Designed with the owner on 2026-11-24 (mockups first), built the same day.

## What other apps do (research of 2026-11-24)

- **A question on the side that leaves the main chat alone:** Claude Code's `/btw` (one question with the whole session as context, no tools, an overlay, nothing goes into the history; it reuses the main chat's prompt cache). The Claude Code desktop app has a side chat (Ctrl+;) that knows the main context without redirecting a running task.
- **A temporary fork and a permanent one:** Codex CLI's `/side` forks the conversation, the main agent keeps working, Esc goes back, nothing is merged; `/fork` copies the conversation into a new thread. A blog reports that `/side` became kept by default in v0.146, with `--ephemeral` for throwaway ones (third-party blogs only, which disagree between versions). Its rule of thumb: a side chat past 3 or 4 exchanges should have been a fork.
- **A child conversation that stays attached:** Cursor's side chat gets the parent's history as hidden context, opens from a text selection ("Ask in Side Chat"), is kept until archived, and comes back into the main thread only when you @-mention it. No nesting.
- **A copy into a new chat:** ChatGPT's "Branch in new chat" copies everything up to a message into a new chat, with a divider at the branch point and no merge back (the addition its users ask for most). LibreChat and TypingMind fork the same way, LibreChat with options for which branches to copy.
- **Exploring a term:** Msty's Delve mode opens a split chat on a clicked term. Its release notes admit that the branches get out of hand.
- **Wishes in the OpenAI forum:** select text, ask in a side panel, then discard it, keep it as a branch or "summarize back to main", and the main chat's memory untouched unless you merge explicitly.

## Decisions (2026-11-24, with the owner)

- **Context:** the whole main conversation up to the message it was forked from, then the side chat's own messages.
- **Agent:** the main conversation's agent and model. Its composer, the chat's, can pick others (the owner's wish later the same day: the same composer as the main chat, with attachments, voice messages and the picker).
- **Nothing goes back into the main conversation.** Side chats are for explaining something or making an image or script that you copy and take elsewhere. No merge, no summary back, no "use in chat".
- **Kept.** Side chats stay until you delete them. Finding them again matters most (see "Finding them again").
- **Linked to the message they were forked from,** not to a passage of its text: no marks in the text.
- **Becoming a real conversation copies** the main conversation's messages up to that message into it.
- **They don't go with their message:** deleting the message they were forked from keeps them.
- **Deleting a conversation that has side chats asks:** keep them as conversations, or delete it with all its side chats.
- **A search in the sidebar** is a feature of its own, built after this one.

## How it is stored

A side chat is a `conversations` row of its own. Its columns:

- `parent_id TEXT`: the conversation it was forked from (`ON DELETE SET NULL`). It stays after the side chat becomes a conversation, for the "Forked from" divider.
- `fork_message_id BIGINT`: the message it was forked from. A position, not a foreign key: its context is the parent's messages with an id up to this one, whether that message still exists or not. Once it is a conversation of its own, the copy of that message.
- `side_chat BOOLEAN NOT NULL DEFAULT FALSE`: true while it is a side chat. False once it is a conversation of its own. A side chat whose parent is gone (`parent_id` NULL) counts as a conversation everywhere (`db.get_fork()`, `sideChat` in the API).

It copies the parent's `persona_id`, `persona_values`, `model_id`, `system_prompt`, `hidden` and `hidden_by` when it is created (`_create_side_chat()` in `backend/api/conversations.py`). A model or agent the create request names (`modelId`, `personaId` sent: picked in the side chat's composer before its first message) takes the place of the parent's; the parent's own system prompt goes only with the parent's agent. Later, a side chat's model and agent change like any conversation's (`PATCH /api/conversation/{id}`).

Being its own conversation gives it most things as they are: its own answer run (one per conversation, `answer_runs.py`), so it answers while the main conversation is still writing and keeps running without the browser; the stream, Stop, the message sync, versions of its answers, its files, a generated title.

No side chats of a side chat (400). A side chat that became a conversation can have side chats of its own.

## The history of a side chat

`ConversationHistoryBuilder.build_entries()` builds a side chat's entries as:

1. The parent's summary, if it covers only messages up to `fork_message_id` (`history_summary()`; stream-generate and context-size use it in place of the conversation's own).
2. The parent's messages after that summary up to `fork_message_id`, chosen by id (`db.get_newest_messages()`: a regenerated answer keeps its id and place, but its time is when it was written again), with their tool records. Its latest user message doesn't get its attachments in full: that is the side chat's.
3. The side chat's own messages.

Cut to the model's context window from the oldest end, as for any conversation (`fit()`), so the parent's part goes first. A side chat writes no summary of its own: stream-generate doesn't fold its messages, context-size never says it would, and Summarize on request answers 409.

The system prompt is the parent's: its agent and own system prompt (copied when the side chat was created), its system messages up to `fork_message_id` before the side chat's own (`system_instructions()`), and **the parent's memory snapshot** (`_memory_prompt()` passes the parent's id to `memory_snapshot.prompt_memory()`), so a side chat's requests begin with the same text as the parent's, and the provider's prompt cache covers that part. A fork from the newest message shares the whole prefix; a fork from an older one shares the prefix up to it. A side chat with another agent than its parent's (another memory, maybe) keeps a snapshot of its own, so it never changes the parent's.

Until the side chat becomes a conversation, the parent is read live: an edit or a deletion of an earlier message of the parent changes the side chat's context too.

**Files:** `db.get_conversation_files()` gives a side chat its own files and the parent's files of messages up to `fork_message_id`, so `list_files`, `read_file`, the files' names a tool picks, `web_fetch` and the files API all see them ("explain this image" works). What its tools make, such as images of an MCP server, are files of the side chat.

## Becoming a conversation

`POST /api/conversation/{id}/promote` (`backend/services/side_chats.py`, `db.promote_side_chat()`):

- The parent's files of the messages up to the fork are copied under new file ids, with what was made from them (a PDF's pages and text, previews: all files named `<file id>_…`), as hard links where the file system allows (`file_store.copy_stored_file()`).
- The parent's messages up to `fork_message_id` are copied into the side chat with their tool records and the other versions of answers, the ids of copied files replaced by their copies' in every copied column (file ids are unique words). The copies get ids as `db.import_conversation()` picks them: the original's, a taken id moves up by one, the order is kept, so they stay before the side chat's own messages.
- A summary isn't copied: the next answer writes one when the history needs it.
- `side_chat` becomes false and `fork_message_id` names the copy of the fork message: the chat shows "Forked from <conversation>" after it while the parent exists.
- From then on it is independent: editing or deleting the parent changes nothing in it.
- A conversation that isn't a side chat is returned as it is.

## Deleting

- **A side chat:** the delete button in its panel's header (it asks first), `DELETE /api/conversation/{id}`.
- **The message it was forked from:** keeps the side chat; the side chat's context loses that message.
- **A conversation with side chats:** the dialog says how many it has and offers **Keep side chats as conversations** and **Delete with side chats** (and Cancel) (`DeleteConversationDialogComponent`; a conversation without side chats keeps the browser's confirm). `DELETE /api/conversation/{id}?sideChats=keep|delete`; without the parameter (an older version of the app) they are kept. Keeping makes each one a conversation first (above), then deletes the parent. Running answers of deleted side chats are stopped first.

## Other readers

- **Memory review:** reviews a side chat as a conversation of its own and reads only its own messages; the parent's are reviewed with the parent.
- **Past chats:** a side chat's messages have the memory of its agent like any other (`messages.memory_vault`), so the search finds them. `chat_list`, `chat_search` and `chat_read` name a side chat as "a side chat of conversation <id>: "<title>" (it goes on from there)" (`side_chat_of`).
- **Export:** a side chat exports as a conversation file with its context copied in (the parent's messages up to the fork and their versions). A conversation's export doesn't include its side chats.
- **Hidden:** a side chat is hidden when its parent is (`hidden_content.CONVERSATION_SQL`, `conversation_hidden()`), also when the parent is hidden after it was created.
- **Guests:** their side chats are created and answered like their conversations (guests' writes and answers counters); the browser keeps them.
- **Sync:** `GET /api/conversations` and `GET /api/conversation/{id}` return `parentId`, `forkMessageId` and `sideChat`; the browser takes them over (`Conversation.mergeFork()`), so a side chat made a conversation on another device moves to the sidebar. Their messages sync per conversation, like any other.

## The browser

- **Answers in two places at once:** what follows an answer (start, follow again after the stream broke, Stop, save what the server stored) is `AnswerFollower` (`src/app/services/answer-follower.ts`), moved out of `ChatStateService` unchanged. The main chat has one, and `SideChatService` another, so the side chat answers while the main chat does.
- **`SideChatService`:** the panel's state (closed, the list, or one side chat; a new one is created with its first message), the side chats of the open conversation and their counts per message, sending (creates the side chat with `parentId` and `forkMessageId`, then a title from the model), Stop, regenerate, delete, promote. It syncs the open side chat when it opens, every minute and when the app comes back, and follows its running answer. Opening another conversation closes the panel; opening a side chat by link (`ChatStateService.loadConversation()`) opens its conversation with the panel on it (`sideChatRequests$`).
- **`MessageHost`** (`src/app/chat-ui/message-host.ts`): what a message asks of the chat that shows it. `ChatUiComponent` and `SideChatPanelComponent` both provide it, so the panel shows its messages with the chat's message component. In the panel messages can't be edited, inserted or sent again, and no side chats are forked from them.
- **`SideChatPanelComponent`:** 440 px (380 px below 1100 px) to the right of the chat, which gets narrower; at 768 px and below a full-screen sheet. Its left edge changes its width (the owner's wish, 2026-11-24): drag it, or focus it and use the arrow keys (Home and End for the limits); a double-click goes back to the default. At least 300 px, and the chat keeps 360 px (also when the window gets narrower later). The width is kept in this browser (`localStorage` `sideChatPanelWidth`), not synced: it depends on the screen. Its header: back to the list, the title, **Make it a conversation** (an icon with a tooltip), delete, close. Then "Forked from the answer · 14:02" with the start of that message (it shows the message in the chat, marked for a moment; on a phone the sheet closes first), the messages, and the chat's composer (`ChatUiInputfieldComponent`, "Ask on the side…"): attachments, photos, voice messages (sent once their transcript is there), Files of this chat, Stop, and the model and agent picker (`ModelPickerComponent` with `[source]="sideChats"`: `SideChatService` gives the side chat's selection, a new one's is its conversation's until picked otherwise). Two composers on one page: a recording shows only in the composer that started it, and files dropped on the panel (`[data-drop-area]`) go to its composer, elsewhere to the chat's (`ownDrops`).
- **The message it was forked from** is marked in the chat while its side chat is open (`side-chat-fork`).
- **Sidebar:** side chats aren't listed (`ChatStateService.visibleConversations$`); a conversation shows how many it has, its menu has **Side chats (N)**, and the newest message of a side chat moves its conversation up (`Conversation.sideActivity`, not stored).

## Finding them again

1. **At the message:** a message with side chats shows a badge with their number ("2 side chats") in its row of actions, always, also when the other actions wait for hover. It opens the side chat, or the list with that message's side chats marked.
2. **The conversation's list:** **Side chats N** at the top right of the chat while the panel is closed, and **Side chats (N)** in the conversation's menu in the sidebar, open the list: title, the start of the message it was forked from, last activity, newest first.
3. **The sidebar:** the count next to a conversation's name, and side chats' activity moves it up.
4. **Agents:** the search over past chats finds side chats and names their conversation.

## Not built

- **"Ask on the side" on selected text,** which would put the selected text into the composer as a quote: open, the owner hasn't decided.
- **Editing a side chat's messages** (and inserting, sending again).
- **"Side chat in <conversation>" in All files:** a side chat's files are listed under its own title.
- **A conversation's export with its side chats.**
- **The search in the sidebar** (decided: a feature of its own, next).

## Tests

`python backend/services/tests/side_chats_test.py` (11 tests) against a real Postgres (`<POSTGRES_DB>_side_test`) and the fake OpenAI server: creating one (what it takes from the parent, no side chat of a side chat, of another user's conversation or at a message that isn't the parent's), the conversation list's fields; the history (the parent's messages up to the fork with tool records, nothing later, the parent's system messages up to the fork, the request beginning as the parent's does); answering while the parent's answer runs; the summary (the parent's only when it covers no later message, no summary of its own, 409 on request); the files it sees; deleting the fork message and editing an earlier one; making it a conversation (copies with tool records, versions and files, ids before its own messages, `fork_message_id` on the copy, independent from then on, also of the parent's deletion); deleting a conversation with its side chats kept, kept without the parameter, and deleted; the export; past chats naming the parent; hidden with the parent; and that only the owner can do any of it.

Checked live on 2026-11-24 in the dev app at desktop and phone width with DeepSeek V4.1 Flash: a side chat from an answer and from your own message, its answer while the main chat answered, the badge, the list, the button on the chat, the sidebar count and menu, making one a conversation (copies, divider), deleting one, and deleting a conversation with a side chat kept.
