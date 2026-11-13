# Past chats

Feature doc, written on 2026-11-13 before building. The agent gets tools to search, list and read the user's earlier conversations. The memory and the knowledge base hold what the agent or a review chose to write down; the chats are the source. Once built, this doc becomes the reference, like `docs/knowledge_base.md`.

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
- **A tool group of its own:** `past_chats` ("Past chats" / "Frühere Chats"), opt-in like `knowledge_base` (in `OPT_IN_GROUPS`, not part of "all tools"), never for guests. It only works together with the knowledge base, since an agent without it has no memory and so no chats to search. A group of its own gives control per agent: an agent can keep notes without reading old chats.
- **The current conversation counts too,** all of it, including the part folded into the rolling summary, whose details the model no longer sees.
- **One search tool: grep with regular expressions.** No separate word search: a regular expression covers it (`mother|mama|mutter` finds any of the words, a substring also finds "Mutters"), and models write them well. The cost is that hits come newest first, not by relevance; the result says how many there are in all, so the agent narrows the pattern or the dates.
- **Grep from SRW.** `chat_search` is SRW's `kb_grep` (`grep_notes()` and its SQL helpers in `src/shared/runtime/services/knowledge_store.py` of Superhuman-Remote-Worker), adapted from asyncpg and SRW's `knowledge_index` to SQLAlchemy `text()` and the messages, with the lines also matched in Postgres (see [Search](#search-planned-backendservicespast_chatspy)).
- **No vectors.** The agent makes up for different wording with alternatives and both languages in its pattern. No test shows how much embeddings would add for chats like these; they are cheap to leave out at first and come later only if testing shows misses, then for the notes and the chats together (see [Later](#later)).
- **Fixed tools, no SQL from the model.** The tools bind the user and the memory like the knowledge base tools do (`functools.partial`), so the model can't reach other chats.

- **What the memory review read belongs to its memory.** A message stored without a memory (no agent, an agent without the knowledge base, an imported conversation) joins the memory the review saves it to. That is how imported chats get in (also the 2023/24 ones): give the conversation an agent with the knowledge base and press "Save to memory". The same works for the old chats of an agent that gets the knowledge base later.

## Which memory a message belongs to

- **`messages.memory_vault`:** NULL for no memory, 0 for the shared knowledge base, else the `personas.id` of the agent with own memory (the same numbers as `kb_notes.vault`).
- **Set when the message is stored,** from the conversation's agent at that moment: NULL without an agent, for an agent without the `knowledge_base` group, a disabled agent, or a guest's conversation; the agent's id with own memory; else 0. That is `persona_vault()` in `backend/catalog/resolver.py` plus "no knowledge base, no memory".
- **A trigger sets it** (`BEFORE INSERT ON messages`, in `schema.sql`), because messages are stored in four places in `backend/database/db.py` (sync, insert, import, insert between messages) and none may be missed. An update doesn't change it: an edited message stays where it was.
- **The memory review claims messages without one.** When the review (automatic or "Save to memory", `backend/services/memory_review.py`) has read a part of a conversation and moves its mark (`db.set_memory_review()`, not after a failure), the messages up to the mark that have no memory get the review's (`persona_vault()` of the conversation, as the review uses it). Messages that have a memory keep it.
- **Per message, not per conversation,** because a conversation's agent can change in the middle: the part with a therapist-like agent stays in its memory when a general agent takes over.
- **Existing messages** are filled once from their conversation's agent as it is now, the best there is. For an agent that is already deleted: its own knowledge base if it has notes there (`kb_notes.vault` is its id), else the shared one if a note was written to vault 0 from that conversation (`kb_note_revisions.conversation_id`), else none.

## Tools (planned: `backend/services/tools/chat_tools.py`)

| Tool | What it does |
|---|---|
| `chat_search(pattern, literal?, after?, before?, max_matches?)` | Every line of a message that matches the pattern, a regular expression, case-insensitive (`literal`: plain text, for "C++" or "what?"), newest first, with the line before and after. Grouped by conversation with its title, agent and dates; each line with its message id, role and time. Says how many messages in how many conversations matched in all |
| `chat_list(after?, before?, max_results?)` | The conversations, most recent activity first: title, agent, first and last message date, number of messages, and the start of the rolling summary if there is one, else the start of the first message |
| `chat_read(conversation, message?, messages_before?, messages_after?)` | Messages of one conversation: around `message`, or from the start without it. Says which messages come before and after, so the agent can read on |

The three don't overlap: `chat_search` needs a pattern and shows lines, `chat_list` answers "what did we talk about last week" without one, `chat_read` reads on from either.

- **Text only:** what the user and the agent wrote (user messages, voice transcripts, the agents' answers). System messages, tool results, thinking steps and tool records are left out of the search; `chat_read` shows system messages marked as such and names attachments, like the review's transcript (`message_text()` in `backend/services/memory_review.py`).
- **Dates:** `after` and `before` are dates or times (ISO) in `MEMORY_TIME_ZONE`, so they match the dates of the memory and the journal. They are compared with the message ids (the server's clock in milliseconds).
- **Limits:** `chat_search` 30 lines by default, at most 100, a long line (a paragraph can be thousands of characters) cut to about 300 characters around the match; `chat_list` 10, at most 30; `chat_read` at most 30 messages and about 15,000 characters per call, a long message cut at 3,000 characters with its length named. `chat_read` with `messages_before=0, messages_after=0` gives one message in full (up to the 15,000).
- **Errors** raise `ToolInputError`: a conversation that doesn't exist or is outside the memory gets the same "No such conversation", so the agent learns nothing about chats it may not see; a malformed regular expression gets Postgres's message and the hint to escape it or use `literal`.
- **Step titles** (`STEP_TITLES` in `backend/llm/tools.py`): "Searching Past Chats", "Listing Past Chats", "Reading Past Chat".
- **Link to the chat:** `chat_read` results carry `{"chat": conversationId, "chatMessage": id}` as a `ToolText`, so the step gets an "Open chat" button, like the book icon of a knowledge base step.

## Search (planned: `backend/services/past_chats.py`)

- **The message's text:** `messages.content` is either plain text or a JSON string `{"content", "attachments"}` (a message with attachments). An `IMMUTABLE` SQL function `message_search_text(content)` in `schema.sql` returns the text of either form and never fails: text that starts with `{` but isn't valid JSON (a pasted code snippet) is returned as it is. A failing function in an index would make storing that message fail.
- **Postgres does all the matching,** in two queries under `SET LOCAL statement_timeout` (5 seconds, from SRW):
  1. **Candidates:** the memory's messages whose text matches `~* ('(?n)' || pattern)`, newest first, at most `max_matches` of them (a message gives at least one line). `(?n)` makes `^`, `$` and `.` work per line. A second query counts all matching messages and conversations.
  2. **Lines:** the candidates' text split into lines in SQL (`regexp_split_to_table(...) WITH ORDINALITY`), with the line before and after (`lag`, `lead`), kept where the line matches; `regexp_instr()` gives the position for cutting a long line around the match.

  SRW matches the lines again in Python with `re`. Here one engine does both, so there is no difference between Postgres's and Python's dialects, and the timeout also covers the lines, which Python's backtracking `re` couldn't promise against a pathological pattern.
- **`\b`:** Postgres reads `\b` as a backspace; its word boundaries are `\y` (`\m` start, `\M` end). Models write `\b` (and `\B`), so the tool translates them outside brackets.
- **Literal:** the text is escaped into a regular expression and takes the same path.
- **From SRW:** at most 256 characters per pattern.
- **Index:** a trigram GIN index (`pg_trgm`, `gin_trgm_ops`) on `message_search_text(content)`, from the start, because unlike a user's notes the messages are many. It serves `~*`; a pattern without three literal characters in a row (`a.b`) can't use it and scans, which the timeout bounds. `pg_trgm` comes with Postgres (contrib, in the `pgvector/pgvector:pg16` image); `prepare_database()` creates it like the vector extension.
- **Scope:** messages join their conversation for the user (`conversations."userId"`) and `memory_vault = :vault`.
- **Size on the development database (2026-11-13):** 220 messages in 43 conversations, one with JSON content. The private deployment has more; count it before building the index there.

## Prompt

A section `## Past Chats:` (like `KB_PROMPT` in `backend/llm/prompts.py`), only there when the tools are:

- The memory and notes are summaries; the chats are the source. Search them when the user refers to an earlier conversation ("like we discussed", "last time", "you said"), asks what was talked about, or a detail isn't in the notes.
- The pattern is a regular expression: put alternatives and both languages into one search (`mother|mama|mutter`), use `\b` for whole words; with many hits, narrow the pattern or the dates. Read around a hit with `chat_read` before relying on it.
- Name the chat and its date when using what was found. Say so if nothing was found, rather than guessing.
- A past chat may be roleplay or fiction: what was said in character is not a fact about the user.
- A detail found in a chat that matters later goes into a note or the memory, as usual.

## Frontend

- The group in the tool picker of the Agents page (`persona-dialog.component.ts`, `catalog-admin.utils.ts`), enabled only while "Knowledge base" is checked, like "Own memory"; `ToolGroup` in `src/app/data/models/catalog.model.ts` and `backend/models/catalog.py`; the labels and hint in `en.json` and `de.json`.
- "Open chat" on a step with `metadata.chat` (`agent-steps.component.ts`): `chatState.loadConversation(id)`, as the Knowledge base page does (`openConversation()`). Jumping to the one message and highlighting it doesn't exist yet; that is a step of its own.

## Testing

- **Offline** (`python -m backend.llm.tests.run_all`): the group is opt-in, gives no tools without the knowledge base group, none to guests or without a user; the prompt section comes only with the tools; the user and memory are bound.
- **Against Postgres** (a new `backend/services/tests/past_chats_test.py`, its own `<POSTGRES_DB>_chats_test` database like the other scripts):
  - `memory_vault`: no agent, an agent without the knowledge base, shared, own, disabled, a guest; the agent changed in the middle of a conversation; the agent deleted later; the fill-in of existing messages; an imported conversation claimed by "Save to memory" (only up to the review's mark, not after a failed review, messages with a memory untouched);
  - the text: JSON content, invalid JSON starting with `{`;
  - grep: alternatives, `^` on a later line (needs `(?n)`), `\b` translated, a malformed pattern, `literal` with `.`, `+` and `\`, the 256-character cap, the count beyond the shown lines, a long line cut around the match, context at a message's first and last line, that the trigram index is used (`EXPLAIN`, as SRW's test does);
  - scope: another user, own and shared and no memory, the current conversation with its summarized part, `after`/`before`, a deleted conversation gone;
  - `chat_list`, and `chat_read` windows, paging and cuts.
- **With real models:** on the development database, ask "what did we talk about last week?" and about a detail of an old chat, with the homelab Gemma 4 and a stronger model, and see whether they search on their own and write usable patterns.

## Steps

1. Backend: `pg_trgm` in `prepare_database()`; in `schema.sql` the `memory_vault` column with its trigger and fill-in, `message_search_text()` and the trigram index; the review claiming messages without a memory in `db.set_memory_review()`; `backend/services/past_chats.py`; `chat_tools.py`; the group and schemas in `backend/llm/tools.py` (only with the knowledge base); the prompt section; `ToolGroup`.
2. The tests above.
3. Frontend: the group on the Agents page, "Open chat" on the steps.
4. Try it with real models, then update `docs/knowledge_base.md` and `CLAUDE.md`, and release.

## Later

- **Embeddings** for notes and messages together (pgvector is in place), if the tests show misses on different wording or across languages. Keep grep as the fallback; the router is flaky.
- **Ranking** if newest first proves weak, e.g. by how many of the alternatives a conversation matches.
- **Links to every chat** a search or list step names, not only `chat_read`'s.
- **Jump to a message** from a step: open the chat scrolled to the message and highlight it.
- **Search for the user:** the same search as an endpoint for the sidebar, over all of the user's chats.
- **Pointers from the memory to chats:** the review and the nightly consolidation know the conversation they read; the journal could name it, so `chat_read` can open the source of a line.
- **Recent chats at the start:** for an agent such as a therapist, the end of the last conversation could go into the first answer of a new one without a tool call (the journal and the review cover part of this).
