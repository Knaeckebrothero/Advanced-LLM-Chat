# Past chats

The agent can search, list and read the user's earlier conversations, those of its memory. The memory and the knowledge base hold what the agent or a review chose to write down; the chats are the source. Planned and built on 2026-11-13. See `docs/knowledge_base.md` for the memory itself.

## Why

The memory system keeps summaries: the memory lines, the notes, the memory review's notes of a conversation and the nightly journal. Summaries lose things. What they miss:

- **Exact wording:** a line from a roleplay scene, how an argument went in a philosophical thread, what the agent actually said.
- **Details the review left out** because it judged them unimportant at the time.
- **Chats the review never read:** it skips conversations quiet for more than `MEMORY_REVIEW_MAX_AGE_DAYS` (7), so older chats of an agent that got the knowledge base later never made it into the notes.

What others do and what is known (from the memory research of 2026-11-01):

- **claude.ai** has had chat search since August 2025, next to its memory. The model calls two tools (names unofficial): `conversation_search(query, max_results ≤ 10)` and `recent_chats(n ≤ 20, sort_order, before, after)`. They return short snippets that link to the source chat, and the calls are visible in the chat ([Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context); [Simon Willison](https://simonwillison.net/2025/Sep/12/claude-memory/)). Nobody has published a test of how well it works. Its known weakness is that it only helps when the model decides to search.
- **Raw history with search tools works.** A GPT-4o-mini agent given only the raw LoCoMo history as a file, with the tools `grep`, `search_files`, `open` and `close`, scored 74.0%, above Mem0's best reported 68.5%. It was Letta's own test, and the agent was made to start with `search_files` and keep searching, so it wasn't grep alone ([Letta blog](https://www.letta.com/blog/benchmarking-ai-agent-memory)). SRW's offline test found word-for-word history retrieved far better than extracted memories (recall at 5: 0.94 against 0.20; only 20 questions, so a hint, not proof).

## Decisions (2026-11-13)

- **The memory decides which chats an agent can search.** Every message belongs to the memory its conversation's agent used when the message was stored: the shared knowledge base, an agent's own one, or none. An agent searches only the chats of its memory: an agent with own memory only its own chats, an agent with the shared memory the chats of all agents with the shared memory, an agent without the knowledge base no chats at all. A chat keeps its memory when its agent is changed or deleted later: a deleted agent's shared chats stay shared, its own ones stay its own. See [Which memory a message belongs to](#which-memory-a-message-belongs-to).
- **What the memory review read belongs to its memory.** A message stored without a memory (no agent, an agent without the knowledge base, an imported conversation) joins the memory the review saves it to. That is how imported chats get in (also the 2023/24 ones): give the conversation an agent with the knowledge base and press "Save to memory". The same works for the old chats of an agent that gets the knowledge base later.
- **A tool group of its own:** `past_chats` ("Past chats" / "Frühere Chats"), opt-in like `knowledge_base` (in `OPT_IN_GROUPS`, not part of "all tools"), never for guests. It only works together with the knowledge base (`REQUIRED_GROUPS` in `backend/llm/tools.py`), since an agent without it has no memory and so no chats to search. A group of its own gives control per agent: an agent can keep notes without reading old chats.
- **The current conversation counts too,** all of it, including the part folded into the rolling summary, whose details the model no longer sees.
- **One search tool: grep with regular expressions.** No separate word search: a regular expression covers it (`mother|mama|mutter` finds any of the words, a substring also finds "Mutters"), and models write them well. The cost is that hits come newest first, not by relevance; the result says how many there are in all, so the agent narrows the pattern or the dates.
- **Grep from SRW.** `chat_search` is SRW's `kb_grep` (`grep_notes()` and its SQL helpers in `src/shared/runtime/services/knowledge_store.py` of Superhuman-Remote-Worker), adapted from asyncpg and SRW's `knowledge_index` to SQLAlchemy `text()` and the messages, with the lines also matched in Postgres (see [Search](#search-backendservicespast_chatspy)).
- **No vectors.** The agent makes up for different wording with alternatives and both languages in its pattern. No test shows how much embeddings would add for chats like these; they are cheap to leave out at first and come later only if testing shows misses, then for the notes and the chats together (see [Later](#later)).
- **Fixed tools, no SQL from the model.** The tools bind the user and the memory like the knowledge base tools do (`functools.partial`, a `Scope`), so the model can't reach other chats.

## Which memory a message belongs to

- **`messages.memory_vault`:** NULL for no memory, 0 for the shared knowledge base, else the `personas.id` of the agent with own memory (the same numbers as `kb_notes.vault`).
- **Set when the message is stored,** from the conversation's agent at that moment (`conversation_memory_vault()` in `schema.sql`): NULL without an agent, for an agent without the `knowledge_base` group (also "all tools"), a disabled agent, or a guest's conversation; the agent's id with own memory; else 0. That is `persona_tool_groups()` and `persona_vault()` in `backend/catalog/resolver.py`, plus "no knowledge base, no memory".
- **A trigger sets it** (`set_messages_memory_vault`, `BEFORE INSERT ON messages`), because messages are stored in four places in `backend/database/db.py` (`create_message`, `create_agent_message`, `insert_message_next_to`, `import_conversation`) and none may be missed. An update doesn't change it: an edited message stays where it was.
- **Per message, not per conversation,** because a conversation's agent can change in the middle: the part with a therapist-like agent stays in its memory when a general agent takes over.
- **The memory review claims messages without one.** When the review (automatic or "Save to memory", `backend/services/memory_review.py`) has read a part of a conversation and moves its mark, `db.set_memory_review(..., vault=...)` gives the messages up to the mark that have no memory the review's (`persona_vault()` of the conversation, as the review uses it); not after a failed review. Messages that have a memory keep theirs. Joining a memory isn't a change of the message: the messages trigger leaves `updated_at` alone.
- **Existing messages** were filled once, by `backfill_message_memory()` in the run that adds the column (`messages_lack_memory()`, checked before `app_init --prod` adds columns, like the files' backfill), from their conversation's agent as it is now. For an agent that is already deleted: its own knowledge base if the user has notes there (`kb_notes.vault` is its id), else the shared one if a note was written to vault 0 from that conversation (`kb_note_revisions.conversation_id`), else none. On the development database (2026-11-13) that gave the 9 messages of the Notebook agent's chats the shared memory; the 211 others have no agent with the knowledge base.

## Tools (`backend/services/tools/chat_tools.py`)

| Tool | What it does |
|---|---|
| `chat_search(pattern, literal?, after?, before?, max_matches?)` | Every line of a message that matches the pattern, a regular expression, case-insensitive (`literal`: plain text, for "C++" or "what?"), newest first. Grouped by conversation (id, title, agent, dates, messages), then by message (id, role, time), each matching line marked with `>` and with the nearest non-empty line before and after it, merged like `grep -C1` so every line shows once. Says how many messages in how many conversations match in all |
| `chat_list(after?, before?, max_results?)` | The conversations with messages in the period, most recent activity first: id, title, agent, first and last message, number of messages, and the start of the rolling summary (only if the memory has every message it covers) or else of the user's first message |
| `chat_read(conversation, message?, messages_before?, messages_after?)` | Messages of one conversation: around `message` (3 before, 8 after), or from the start without it (10 after). Says which messages come before and after, so the agent can read on |

The three don't overlap: `chat_search` needs a pattern and shows lines, `chat_list` answers "what did we talk about last week" without one, `chat_read` reads on from either.

- **Text only:** what the user and the agent wrote (user messages, voice transcripts, the agents' answers). System messages, tool results, thinking steps and tool records are left out of the search; `chat_read` shows system messages with the role `system` and names attachments.
- **Dates:** `after` and `before` are dates or times (ISO) in `MEMORY_TIME_ZONE`, so they match the dates of the memory and the journal: `after` from then on, `before` until before then. They are compared with the message ids (the server's clock in milliseconds); results show times in the same zone.
- **Limits:** `chat_search` 30 lines by default, at most 100, a long line (a paragraph can be thousands of characters) cut to about 300 characters around the match, the lines around it to 150; `chat_list` 10, at most 30; `chat_read` at most 30 messages (near the start, the rest go after the message) and about 15,000 characters per call, a message among others cut at 3,000 characters with its length named. `chat_read` with `messages_before=0, messages_after=0` gives one message alone, up to the 15,000.
- **Errors** raise `ToolInputError`: a conversation that doesn't exist, is another user's or has no message in the memory gets the same "No conversation … among your past chats", so the agent learns nothing about chats it may not see; a malformed regular expression gets Postgres's message and the hint to escape it or use `literal`; a search over the timeout gets advice to narrow it.
- **Step titles** (`TOOL_TITLES` in `backend/llm/tools.py`): "Searching Past Chats", "Listing Past Chats", "Reading Past Chat".
- **Link to the chat:** `chat_read` results carry `{"chat": conversationId, "chatMessage": id}` as a `ToolText`. The chat shows a history icon on the result step and an "Open chat" button inside it (`chatOf()` and `openChat()` in `agent-steps.component.ts`), which opens the conversation with `chatState.loadConversation()`.

## Search (`backend/services/past_chats.py`)

- **The message's text:** `messages.content` is either plain text or a JSON string `{"content", "attachments"}` (a message with attachments). The `IMMUTABLE` function `message_search_text(content)` in `schema.sql` returns the text of either form and never fails: text that starts with `{` but isn't valid JSON (a pasted code snippet) is returned as it is. A failing function in an index would make storing that message fail. `message_parts()` reads it the same way in Python, with the attachments' names.
- **Postgres does all the matching,** in one transaction under `SET LOCAL statement_timeout` (5 seconds, from SRW):
  1. **Candidates:** the memory's messages (not system messages) whose text matches `~* ('(?n)' || pattern)`, newest first, at most `max_matches` of them (a message gives at least one line). `(?n)` makes `^`, `$` and `.` work per line.
  2. **Lines:** the candidates' text split into lines in SQL (`regexp_split_to_table(...) WITH ORDINALITY`), blank lines left out, with the line before and after (`lag`, `lead`) and the line's number (`row_number`), kept where the line matches; `regexp_instr()` gives the position for cutting a long line around the match.
  3. **Count:** all matching messages and conversations.

  SRW matches the lines again in Python with `re`. Here one engine does both, so there is no difference between Postgres's and Python's dialects, and the timeout also covers the lines, which Python's backtracking `re` couldn't promise against a pathological pattern.
- **Patterns as models write them** (`postgres_regex()`): Postgres reads `\b` as a backspace; its word boundaries are `\y` (`\m` start, `\M` end). `\b` and `\B` become `\y` and `\Y` outside brackets (an escaped backslash and brackets, also `[]…]` and `[[:alpha:]]`, stay as they are), and inline flags at the start such as `(?i)` are dropped, since Postgres takes options only at the very start, where the search puts its own.
- **Literal:** `literal_regex()` puts a backslash before every character a Postgres regular expression gives a meaning, and the text takes the same path.
- **From SRW:** at most 256 characters per pattern.
- **Index:** a trigram GIN index (`idx_messages_search_trgm`: `pg_trgm`, `gin_trgm_ops`) on `message_search_text(content)`. It serves `~*`, also with the `(?n)` prefix (the test checks with `EXPLAIN`); a pattern without three literal characters in a row (`a.b`) can't use it and scans, which the timeout bounds. `pg_trgm` comes with Postgres (contrib, in the `pgvector/pgvector:pg16` image); `prepare_database()` creates it like the vector extension, and the index is only created where it exists (a `DO` block), since a failed statement would break the rest of the schema's transaction.
- **Case:** umlauts match in any case under the database's locale (`en_US.utf8` in the bundled Postgres): "SCHÖN" finds "schön".
- **Scope:** messages join their conversation for the user (`conversations."userId"`) and `memory_vault = :vault`.

## Prompt

`CHAT_PROMPT` (`## Past Chats:` in `backend/llm/prompts.py`), after the knowledge base's section, only there when the tools are:

- The memory and notes are summaries; the chats are the source. Search them when the user refers to an earlier conversation ("like we discussed", "last time", "you said"), asks what was talked about, or a detail isn't in the notes.
- The pattern is a regular expression: put alternatives and both languages into one search (`\bmother\b|\bmom\b|mutter|mama`), a part of a word also finds longer words; with many hits, narrow the pattern or the dates, with none, try other words. Read around a hit with `chat_read` before relying on it.
- Name the chat and its date when using what was found. Say so if nothing was found, rather than guessing.
- A past chat may be roleplay or fiction, or with another agent: what was said in character is not a fact about the user.
- What matters beyond the conversation goes into the memory or a note, as usual.

## Frontend

- **Agents page:** the group in the tool picker (`persona-dialog.component.ts`), with the icon `history` (`catalog-admin.utils.ts`) and its hint (`catalog.admin.personas.toolOptInPastChats`). It can only be picked while "Knowledge base" is (`requires` in `GET /api/admin/tools`, `REQUIRED_TOOL_GROUPS` in `catalog.model.ts` when the list can't be loaded); removing the knowledge base removes it too. One picked already without the knowledge base can still be removed.
- **Chat:** "Open chat" on a step with `metadata.chat` (`knowledgeBase.openChat`). Jumping to the one message and highlighting it doesn't exist yet.

## Testing

- **Offline** (`python -m backend.llm.tests.run_all`, `test_past_chats_need_the_knowledge_base`): the group is opt-in and gives no tools without the knowledge base group, none to guests or without a user; the user and memory are bound, not schema arguments; the prompt section comes only with the tools, after the knowledge base's; the regular expressions translated for Postgres. The tool status has `requires`.
- **Against Postgres** (`python backend/services/tests/past_chats_test.py`, its own `<POSTGRES_DB>_chats_test` database):
  - `memory_vault`: no agent, an agent without the knowledge base, "all tools", disabled, a guest, shared, own; the agent changed in the middle of a conversation; the agent deleted later; an edit; db.py's insert paths and an import;
  - the fill-in of existing messages (an agent that still exists, deleted ones with notes in their own vault, with a note in the shared one, without notes; messages that have a memory);
  - the review's claim: only up to its mark, not after a failure, messages with a memory untouched, `updated_at` unchanged; an imported conversation that gets an agent and is reviewed (`review_conversation()` against the fake OpenAI server), then found;
  - the text: JSON content, `null`, another JSON object, invalid JSON starting with `{`, in SQL and in Python;
  - the search: alternatives, parts of words, case (also umlauts), `\b`, `^` and `$` on a later line, literal text, system messages and attachment names left out, the lines around a hit without blank lines, a long line cut around the match, the count beyond the shown lines, refused patterns and dates, the timeout's message, that the trigram index is used;
  - scope: the own memory and the shared one, another user, messages without memory, the period, a deleted conversation;
  - `chat_list` (order, period, limit, the summary only when the memory has every message it covers), `chat_read` (from the start, around a message, 30 at most, cuts, one message alone, the budget, unknown or foreign conversations and messages, a conversation of two memories);
  - the tools' texts through the registry, the merged lines of one message, the step's link, a deleted agent's name.
- **With a real model** (2026-11-13, development database, DeepSeek V4.1 Flash, the Notebook agent with past chats, the user `kb-demo@example.com`): asked in German what exactly they had said about the mast and when, the model searched on its own (`mast|seldén|selden|rigg`), read the conversation and listed the chats, then quoted the one sentence with its chat and date and told it apart from what it had answered itself. "Open chat" opened that conversation. Weaker models (the homelab's Gemma 4) are still to be tried.

## Later

- **Embeddings** for notes and messages together (pgvector is in place), if the tests show misses on different wording or across languages. Keep grep as the fallback; the router is flaky.
- **Ranking** if newest first proves weak, e.g. by how many of the alternatives a conversation matches.
- **Links to every chat** a search or list step names, not only `chat_read`'s.
- **Jump to a message** from a step: open the chat scrolled to the message and highlight it.
- **Search for the user:** the same search as an endpoint for the sidebar, over all of the user's chats.
- **Pointers from the memory to chats:** the review and the nightly consolidation know the conversation they read; the journal could name it, so `chat_read` can open the source of a line.
- **Recent chats at the start:** for an agent such as a therapist, the end of the last conversation could go into the first answer of a new one without a tool call (the journal and the review cover part of this).
- **The conversation's title** shows in results even when its first messages belong to another memory (a conversation whose agent changed); the summary is hidden in that case, the title isn't.
