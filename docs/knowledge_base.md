# Knowledge base

Each signed-in user has one knowledge base: Markdown notes that the agent keeps across all of the user's conversations, like an Obsidian vault it writes itself. For now it is the agent's notebook, separate from the planned memory across conversations; it may be merged into that memory later.

It is adapted from the knowledge base of Superhuman Remote Worker (SRW): its `kb_*` tools, slugs and link parsing. SRW's notes live in a git repository per project, with Postgres as an index that is rebuilt from it. Here Postgres holds the only copy, which drops SRW's reindexing, sync bookkeeping and forge handling.

## Who gets it

- The tool group `knowledge_base` is **opt-in** (`OPT_IN_GROUPS` in `backend/llm/tools.py`). Only an agent whose tools list it explicitly gets the tools. An agent with "all tools" (`tools: null`) and a chat without an agent don't.
- **Guests never get it**, even with such an agent, because a guest's data is deleted when the session ends. Without a user the group gives no tools at all.
- The tools are built per answer for the user it is for (`functools.partial`), so the model can't choose another knowledge base.
- On the Agents page the group is labelled "Knowledge base" / "Wissensdatenbank". Under "All tools" it stays unchecked and has a hint.

## Tools (`backend/services/tools/kb_tools.py`)

| Tool | What it does |
|---|---|
| `kb_search(query?, exact?, tags?, max_results?)` | Notes that contain any query word, any exact text or any of the tags. Each hit shows how it matched and the passage around the match |
| `kb_list(tag?, max_results?)` | The active notes, most recently updated first. Without a tag it also lists the 20 most used tags |
| `kb_read(note)` | A note in full: content, tags, dates, the notes it links to (also ones that don't exist yet) and the notes that link to it |
| `kb_write(title, content, description?, tags?)` | Creates a note. The slug is made from the title. A title whose slug exists already is refused (also for an archived note), with a pointer to `kb_update` |
| `kb_update(note, content? \| append?, title?, description?, tags?)` | Replaces the content or appends to it (not both), and can change the title, description or the whole tag list. The slug stays the same. Updating an archived note restores it |
| `kb_archive(note, reason?)` | Hides a note from lists and searches; `kb_read` still shows it. Nothing is deleted for good |

A refused request raises `ToolInputError`. The step shows as failed, and the model gets a message saying what to do instead, so a tool result never claims a write that didn't happen. A `## Knowledge Base:` section of the system prompt (`KB_PROMPT` in `backend/llm/prompts.py`) says when to search, write, update and link. It is only there when the tools are.

## Notes (`backend/services/knowledge_base.py`)

- **Slug:** the note's stable id, unique per user. It is made from the first title: lowercase ASCII, umlauts transliterated ("Größe" becomes `groesse`), at most 80 characters, and `note-<hash>` for a title with no letters it can keep. A note can be referred to by its slug, by its exact title or as `[[slug]]`.
- **Fields:** title (up to 200 characters), optional one-sentence description (up to 300), lowercase tags (up to 20), Markdown content (up to 50,000 characters). A note over 15,000 characters gets a hint to split it. A first heading that repeats the title is dropped, because `kb_read` shows the title itself.
- **Links:** `[[slug]]`, `[[Title]]`, `[[slug|alias]]`, `[[slug#heading]]` and Markdown links without a scheme (`[text](other-note.md)`). Each target is turned into a slug and stored in `kb_links` on every write; the backlinks come from there. Archived notes don't count as backlinks.
- **History:** every write also stores the new version in `kb_note_revisions`, in the same transaction. A revision records the action (create, update, archive), the author (`agent`, later also `user`), the conversation and its agent, and for an archive the reason.
- **Parallel calls:** tool calls of one model turn run concurrently. An update locks the note's row, so parallel appends are all kept. Two notes with the same slug written at the same moment are stopped by the unique key, and the second one gets the usual "exists already" message.
- **Deleting a user** deletes their notes, revisions and links (`ON DELETE CASCADE`).

## Search

One query per search, over the user's active notes:

- **Words:** Postgres full-text search with the `simple` configuration, so German and English work the same (no stemming, no stop words). A note matches if it contains any of the words, and words of four letters or more also match as prefixes ("katze" finds "Katzen"). Words in the title weigh most, then the description and tags, then the content.
- **Exact:** a case-insensitive substring of slug, title, description, tags or content. LIKE wildcards in it are literal.
- **Tags:** notes with any of them.
- **Score:** the word rank, plus 1 for each exact text the note contains, plus 0.3 for each of the tags it has. Ties go to the more recently updated note.

There is no index for this: a user's vault is small (SRW's agent-written notes have a median of 3 KB), so the user's rows are scanned. A generated `tsvector` column with a GIN index is the next step if that gets slow; `array_to_string` isn't immutable, so the tags would need their own handling there.

## Postgres with pgvector

The compose files and the Helm chart run `pgvector/pgvector:pg16` (Debian) instead of `postgres:16-alpine`, so embeddings won't need an image change. Moving an existing data directory from Alpine (musl) to Debian (glibc) changes how text sorts, so its text indexes must be rebuilt.

`prepare_database()` in `backend/database/db.py` does this. It runs at backend start and in `app_init`. On a server that has pgvector, while the database doesn't have the extension yet, it runs `REINDEX DATABASE` if the database has no collation version (a database created under Alpine has none, while glibc reports one), then creates the extension. Postgres can't record a collation version for such a database later (`REFRESH COLLATION VERSION` refuses), so the extension is the marker that the rebuild has been done. If the rebuild fails, for example without owner rights, it is logged and tried again on the next start. A server without pgvector is only logged.

## Testing

- `python -m backend.llm.tests.run_all` (offline): the group is opt-in, guests and requests without a user get nothing, the prompt section, the tool status, and that writes record the conversation and its agent.
- `python backend/services/tests/knowledge_base_test.py`: the tools against a real Postgres, in a database `<POSTGRES_DB>_kb_test` that it creates itself. It covers:
  - slugs and link parsing;
  - read-after-write;
  - refused duplicate slugs;
  - links and backlinks;
  - update rules;
  - search (German prefixes, title first, literal wildcards, tags);
  - archive and restore;
  - two users who can't see each other's notes;
  - revisions;
  - parallel tool calls;
  - cascade on user delete.

## Not built yet

- **Embeddings (step 2):** a vector column next to the notes, filled from the homelab's Qwen3 embedding model, plus a semantic part in the search score. Keep the word and exact search as a fallback, because the router is flaky and SRW once lost its whole knowledge base to a missing embedding key. With a fixed dimension HNSW works up to 2000 dimensions (`halfvec` up to 4000). A per-user scan of an untyped `vector` column works without any index.
- **UI:** a page to browse, edit and restore notes and to see the revisions, plus a link from a `kb_write` step to its note. Revisions with `author: user` are already planned for edits made there.
- **Notes in the prompt:** the agent only sees notes it searches for or reads. A list of the user's notes in the system prompt, or SRW-style search hits for each message, would be next.
- **Import and export** as Markdown files (Obsidian), and a way for users to delete notes for good.
