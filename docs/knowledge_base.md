# Knowledge base

Each signed-in user has a knowledge base: Markdown notes that the agent keeps across all of the user's conversations, like an Obsidian vault it writes itself. Its note `memory` is the agent's **memory**: short lines that are part of every answer and point to the notes with the details, like Claude Code's `MEMORY.md` index (see [Memory](#memory)). An agent with **own memory** gets a knowledge base of its own per user instead of the shared one ([Knowledge bases per agent](#knowledge-bases-per-agent)). Once a conversation has been quiet for a while, a **memory review** reads it and saves what the agent didn't ([Memory review](#memory-review)). Once a night, a **consolidation** puts the day together in a journal per week, tidies the memory up and keeps the patterns it sees ([Nightly consolidation](#nightly-consolidation)). Nothing is off limits: the user wants everything kept, personal and sensitive topics included, so the prompts ask to save rather than to hold back ("when in doubt, save it") and have no safety rules or restrictions on web content (decided on 2026-11-04). A note can keep files, above all images, so the agent shows a picture again in any later conversation ([Files](#files)). On the Knowledge base page the user reads, searches, corrects, archives and deletes the notes and the memory, sees who wrote each version, and exports them as an Obsidian vault. An agent that also has the tool group **Past chats** searches and reads the user's earlier conversations of its memory, word for word (`docs/past_chats.md`); what the memory review reads joins its memory.

The design follows the memory research of 2026-11-01 (Claude, ChatGPT, Claude Code, OpenClaw, Letta and the benchmarks): a small curated layer in every prompt, details looked up on demand, and a background job that doesn't depend on the chat model remembering to save.

It is adapted from the knowledge base of Superhuman Remote Worker (SRW): its `kb_*` tools, slugs and link parsing. SRW's notes live in a git repository per project, with Postgres as an index that is rebuilt from it. Here Postgres holds the only copy, which drops SRW's reindexing, sync bookkeeping and forge handling.

## Who gets it

- The tool group `knowledge_base` is **opt-in** (`OPT_IN_GROUPS` in `backend/llm/tools.py`). Only an agent whose tools list it explicitly gets the tools. An agent with "all tools" (`tools: null`) and a chat without an agent don't.
- **Guests never get it**, even with such an agent, because a guest's data is deleted when the session ends. Without a user the group gives no tools at all.
- The tools are built per answer for the user and knowledge base it is for (`functools.partial`), so the model can't choose another knowledge base.
- On the Agents page the group is labelled "Knowledge base" / "Wissensdatenbank". Under "All tools" it stays unchecked and has a hint. With the group picked, the switch **Own memory** (`own_memory`, `ownMemory`) gives the agent its own knowledge base.

## Tools (`backend/services/tools/kb_tools.py`)

| Tool | What it does |
|---|---|
| `kb_search(query?, exact?, tags?, max_results?)` | Notes that contain any query word, any exact text or any of the tags. Each hit shows how it matched, the passage around the match and the files the note keeps |
| `kb_list(tag?, max_results?)` | The active notes, most recently updated first, with the files they keep. Without a tag it also lists the 20 most used tags |
| `kb_read(note)` | A note in full: content, tags, dates, the notes it links to (also ones that don't exist yet), the notes that link to it, and the files it keeps with where each comes from |
| `kb_write(title, content, description?, tags?, files?)` | Creates a note. The slug is made from the title. A title whose slug exists already is refused (also for an archived note), with a pointer to `kb_update`. `files`: files of the conversation that the note keeps ([Files](#files)) |
| `kb_update(note, content? \| append?, title?, description?, tags?, files?)` | Replaces the content or appends to it (not both), and can change the title, description or the whole tag list. The slug stays the same. Updating an archived note restores it. `files`: further files the note keeps |
| `kb_archive(note, reason?)` | Hides a note from lists and searches; `kb_read` still shows it. Nothing is deleted for good |
| `memory_add(text, section?)` | Adds a line to the memory with today's date, under the heading `section` (made if missing) or before the first heading. A line it has already is not added twice |
| `memory_replace(line, text)` | Replaces the one line that contains `line` (a few words of it, case-insensitive) with `text`, dated today |
| `memory_remove(line)` | Removes the one line that contains `line`; a heading left without lines goes too |

A refused request raises `ToolInputError`. The step shows as failed, and the model gets a message saying what to do instead, so a tool result never claims a write that didn't happen. The `## Knowledge Base and Memory:` section of the system prompt (`KB_PROMPT` in `backend/llm/prompts.py`) explains the two layers, when to save (the user tells something about themselves, a correction or preference, a decision or goal, "remember this", worked-out results), how (a fact on one line in the memory, details in a note plus a pointer line), when to look things up, and to write down only what the user said or what the agent found out. It comes with the tools, separate from the agent's own prompt, and is only there when the tools are. `kb_write` answers with a nudge to give an important note a pointer line in the memory.

The results of `kb_read`, `kb_write`, `kb_update`, `kb_archive` and the memory tools are a `ToolText` (`backend/llm/tools.py`): a string for the model that also carries `{"kbNote": slug}` (and `{"kbVault": id}` for an agent's own knowledge base). The agent loop puts that into the result step's `metadata`, and the chat shows a book icon on the step (and an "Open note" button inside it) that opens the note on the Knowledge base page. A result that names kept files (also of `kb_search` and `kb_list`) carries them as `{"kbFiles": [...]}`, which is how the chat finds a file the answer places.

## Memory

The note with the slug `memory` of a knowledge base (`MEMORY_SLUG` in `backend/services/knowledge_base.py`), titled "Memory":

- **In every answer:** `_answer_context()` in `backend/api/messages.py` reads it for every answer of an agent with the memory tools and adds it with `with_memory()` after the tool sections and before the conversation's own instructions: `## Your memory:`, today's date (so the model dates what it saves and sees how old a line is), then the lines in `<memory>` tags, framed as notes to follow as preferences but not as instructions that override the system prompt. Like system messages, it is outside the history, so it is never cut off or summarized.
- **A snapshot per conversation** (`backend/services/memory_snapshot.py`, table `conversation_memory_snapshots`, decided on 2026-11-13): the prompt shows the memory as it was when the snapshot was taken, with that day, not the memory as it is now. A provider's prompt cache only reads the part of a request that starts like an earlier one, and the memory sits ahead of the whole history: when the prompt took the memory fresh for every answer, every change (a line the agent saved, the review, the consolidation, a new day) made the next answer pay the full price for the whole history once more. The Claude apps do the same: their memory stays as it was when the conversation or session began, and Claude Code tells the model about changes in a note in the conversation.
  - **Taken** at the conversation's first answer, and again once nothing was answered for `MEMORY_SNAPSHOT_REFRESH_MINUTES` (30; the cache is gone by then anyway) or when the conversation's knowledge base or family mode changed.
  - **Meanwhile** what changed since (the lines added and removed, a new day) goes to the model as a `<memory-update>` note at the start of the newest user message (`change_note()`, `with_note()`). It is never stored and moves on with every new message, so a change only costs the last exchange. The agent's own saves in the conversation are also in its history, as its tool calls and results.
- **Format:** Markdown lines, `- <fact> (<date>)`, under headings such as "About the user", "Preferences", "Ongoing" and "Where things are"; pointers to notes as `[[slug]]`. Lines the user writes on the page may look different; the tools keep them.
- **Size:** at most `MEMORY_MAX_LINES` (200) lines of text and `MEMORY_MAX_CHARS` (20,000) characters, about 5,000 tokens of every prompt; one line at most `MEMORY_LINE_CHARS` (500). From 90 % on, every change reminds the model to merge lines and move details into notes; a change that would go over is refused with that advice. Code enforces this, not the prompt.
- **Only line by line:** `kb_write` refuses the title "Memory", `kb_update` and `kb_archive` refuse the note; lists, searches and the counts leave it out (it is in the prompt anyway). `kb_read` shows it. Its `[[links]]` count, so a note shows "Linked from: Memory".
- **History:** every change is a revision like a note's (author `agent`, `review` or `user`). The user edits it on the page like a note (with the version check), can't archive it, and deletes it to empty it.
- **Parallel calls:** a change locks the memory row; the first change of a parallel pair creates the note, the other one then changes it.

## Nightly consolidation

`backend/services/memory_dream.py`, like sleep after a day: once a night a model goes over every knowledge base that had conversations since its last run (author `dream` in the history). The memory review saves the details of single conversations; this is where they are put together, so "what mattered last week" has an answer and the memory doesn't just grow.

- **Journal:** one note per ISO week, "Journal 2026-W45" (`journal-2026-w45`, tag `journal`), with a section per day ("## Tuesday, 2026-11-03"): what the user did and talked about, what mattered, decisions, progress, moods and open threads, linked to the notes. A later run adds to the week's note without changing earlier days.
- **Memory:** a line under "Where things are" points to the current week's journal; lines on the same topic are merged, changed facts updated (a plan that became a fact), done or wrong ones removed.
- **Patterns:** it reads the last few journal notes and keeps what recurs (themes, habits, moods, what helps, how the user works) under "Patterns" in the memory.
- **Notes:** outdated notes are updated, two notes on the same topic merged (the other one archived).
- **Input:** the period with its days and their week notes (new or existing), the earlier journal notes, the knowledge base's changes in the period (`changes_since()`: by the agent, the review or the user), and the conversations as one transcript with the time of each message (text only, cut to half the model's window: messages shortened, then the oldest left out). For an agent's own knowledge base also the agent's prompt as context; for the shared one the names of the agents that use it.
- **Model:** the user's memory model, else the model of their latest conversation in the period (`resolve_memory_model()`).
- **Period:** `memory_dreams` keeps, per user and knowledge base, how far the last run got (`dreamed_until`, milliseconds like message ids). A first run looks back 24 hours (`--hours`), no run more than 7 days. A failed run sets `failed_at` and the next one covers the same period and what came since.
- **Time zone:** `MEMORY_TIME_ZONE` (default UTC) gives the journal's days and the memory's dates ("today" in the prompt, the date of a new line). The Helm value `backend.memoryDream.timeZone` sets it and the CronJob's schedule zone together.
- **Where it runs:** a Kubernetes CronJob of the Helm chart (`backend.memoryDream`: `enabled`, default on; `schedule`, default `30 3 * * *`; `timeZone`; `activeDeadlineSeconds`), with the backend's image, settings and secrets, and an empty `data` volume (the backend's is ReadWriteOnce). One run at a time; a missed run waits for the next night. Docker compose doesn't schedule it; run it by hand with `docker compose exec -u app backend python -m backend.services.memory_dream` if wanted.
- **By hand:** `python -m backend.services.memory_dream [--user ID [--vault N]] [--hours 24]`. It prints one line per knowledge base; exit code 1 if a run failed (a user without a usable model is only reported).

The first run on the development database (2026-11-04, DeepSeek V4.1 Flash, two days of a test user) wrote the week's journal with both days and their open threads, added the journal pointer and a first pattern to the memory, and updated one note.

## Knowledge bases per agent

`kb_notes.vault`: 0 is the user's shared knowledge base, which every agent with the knowledge base uses; an agent with `own_memory` uses the vault with its `personas.id` (`persona_vault()` in `backend/catalog/resolver.py`). Slugs are unique per user and vault (`UNIQUE (user_id, vault, slug)`), and every read, search, link, backlink, list, count and export stays within one vault. So a therapist-like agent keeps its notes and memory apart from the others, and the others can't find them.

- The tools get the vault bound like the user. A disabled persona, or one the user may no longer use, counts as no persona: vault 0.
- Deleting or changing the agent keeps its notes; the page lists such a vault as "no longer in use" while it has notes.
- `schema.sql` adds the column to older databases and moves the unique key from `(user_id, slug)` to `(user_id, vault, slug)` (block `kb_notes_unique_per_vault`), also without `app_init --prod`.

## Memory review

`backend/services/memory_review.py`: once a conversation of a signed-in user with an agent that has the knowledge base has had no new message for `MEMORY_REVIEW_IDLE_MINUTES` (15), a model reads what was said since the last review and saves what matters with the same tools (author `review` in the history). So the memory doesn't depend on the chat model remembering to save while it answers, or being able to: models without tools, weaker tool callers.

- **Model:** the user's **memory model** (settings, `user_settings.memory_model_id`, `memoryModelId`; only models with tools), else the conversation's model (`resolve_memory_model()`). Without a usable model with tools the review is skipped and tried again an hour later.
- **Prompt:** `REVIEW_PROMPT` with the same rules on what and how to save as the agent (`KB_SAVE_RULES`, `KB_HOW_RULES`), the agent's name, description and prompt as context (not to follow), and the memory as it is now. The new messages come as a `<conversation>` transcript with their dates; up to 4 messages before them, already reviewed, as `<earlier>` context. Text only: tool results and system messages are left out, attachments are named. The conversation is data, not instructions (so the model doesn't answer or continue it); only the user's requests to remember or forget count. It keeps everything that could matter later and leaves out only small talk and explained general knowledge; if nothing is new, it saves nothing.
- **Once per message:** `conversations.memory_reviewed_until` is the newest message id the review has read; a long stretch of new messages is read in parts of at most half the model's window, and the mark moves after each part. A failed review sets `memory_review_failed_at` and is tried again after 60 minutes. The conversations trigger doesn't count these columns as a change of the conversation (`updatedAt` stays).
- **When:** `review_loop()` runs in the backend (started in `main.py`) and checks every 5 minutes (`db.get_conversations_for_memory_review()`), quietest first, one review at a time. Conversations quiet for more than `MEMORY_REVIEW_MAX_AGE_DAYS` (7) are left alone, so an agent that just got the knowledge base doesn't review months of old chats. `MEMORY_REVIEW_ENABLED=false` switches the loop off. One backend replica: the loop has no lock across processes.
- **On request:** "Save to memory" in a conversation's menu (only with an agent that has the knowledge base) calls `POST /api/kb/review`, which runs the review now and answers what it changed.
- **Cost:** one model run per quiet conversation, which reads the new messages once (about as much input as one more answer in that chat) plus a few searches; logged with the token counts.

## Notes (`backend/services/knowledge_base.py`)

- **Slug:** the note's stable id, unique per user. It is made from the first title: lowercase ASCII, umlauts transliterated ("Größe" becomes `groesse`), at most 80 characters, and `note-<hash>` for a title with no letters it can keep. A note can be referred to by its slug, by its exact title or as `[[slug]]`.
- **Fields:** title (up to 200 characters), optional one-sentence description (up to 300), lowercase tags (up to 20), Markdown content (up to 50,000 characters). A note over 15,000 characters gets a hint to split it. A first heading that repeats the title is dropped, because `kb_read` shows the title itself.
- **Links:** `[[slug]]`, `[[Title]]`, `[[slug|alias]]`, `[[slug#heading]]` and Markdown links without a scheme (`[text](other-note.md)`). Each target is turned into a slug and stored in `kb_links` on every write; the backlinks come from there. Archived notes don't count as backlinks. Links inside code (fenced blocks, also unclosed ones, and inline code) are text, not links (`CODE_RE`).
- **History:** every write also stores the new version in `kb_note_revisions`, in the same transaction. A revision records the action (`create`, `update`, `archive`, `restore`), the author (`agent`, `review` for the memory review, `dream` for the nightly consolidation, or `user` for the page), the conversation and its agent, and a reason (why it was archived, or which version was restored).
- **Version:** the id of a note's newest revision. An edit from the page sends the version it started from (`base_version`); if the note changed since, it is refused with `KBConflict`, so the user's save never silently overwrites what an agent wrote meanwhile (and vice versa).
- **Parallel calls:** tool calls of one model turn run concurrently. An update locks the note's row, so parallel appends are all kept. Two notes with the same slug written at the same moment are stopped by the unique key, and the second one gets the usual "exists already" message.
- **Deleting a user** deletes their notes, revisions and links (`ON DELETE CASCADE`).

## Files

A note can keep files of a conversation, so that they outlast it: an image the user sent, or one a tool of the agent made. That is how an agent keeps pictures, finds them later by words and shows them again in any conversation. It works for any stored file (a PDF, an audio file); images are what it is for.

**One note per image** is the pattern the prompt asks for (`KB_FILES_RULES` in `backend/llm/prompts.py`). The note's text says what the image shows, in enough detail to find it by words: who and what is in it, the setting, style and colors, text in it, why it is kept, and for a generated image the prompt and settings. The search is the notes' text search: nothing searches images by their looks. The agent is told to describe what it sees, not what was asked for, and to look at the image first. A note can also keep several files (a trip with its photos), up to `MAX_NOTE_FILES` (20).

- **Keeping:** `kb_write(..., files=["civitai-3.png"])` or `kb_update(note, files=[...])`, with names or file IDs of files of the conversation the agent answers in. Files of other conversations and other users are refused, and a refused call writes nothing. The memory review has no `files` parameter (it reads a conversation as text), and the memory keeps no files.
- **Its name:** a kept file is named after its note, `<slug>.<ending>`: `red-fox-in-the-snow.png`, further files of the note `red-fox-in-the-snow-2.jpg`. Names are unique in the knowledge base whatever their ending and case (`kb_files`, one write at a time picks them). The name is what the agent and the user go by; the conversation's name (`civitai-3.png`) means nothing later.
- **In the note's text:** `![[red-fox-in-the-snow.png]]` (Obsidian's embed) or `![a fox](red-fox-in-the-snow.png)`. Where the text the agent writes already places the file by its name or file ID in the conversation, that becomes the new name. Else the file goes to the top of a new note, or to the end of an updated one (`_place_files()`).
- **Not twice:** a file a note keeps already is not kept again. Another note that is given it shows it by its name, and the result says which note keeps it.
- **Stored once:** `kb_files` points to the stored file (`uploaded_files`, `docs/files.md`), so keeping costs no second copy. The file stays in its conversation as before, and stays kept when the conversation or its message is deleted.
- **Finding:** `kb_search`, `kb_list` and `kb_read` name the files of the notes they show (`Keeps: red-fox-in-the-snow.png (image/png, 1024×1536 px)`), and `kb_read` says where each comes from and, for a file a tool made, the arguments it was made with. Search results are text: the image itself goes to the model only when it asks.
- **Looking:** `read_file` of the file tools reads a kept file by its name, in any conversation, for an agent that has both tool groups (the image itself for a vision model, `region` to look closer; `docs/files.md`). A file of the conversation with the same name comes first.
- **Showing:** the agent places a kept file in its answer like a file of the conversation, `![what it shows](red-fox-in-the-snow.png)`, which costs no tokens for the image. The chat looks for the name among the files the answer's knowledge base tools named (`metadata.kbFiles`), then the conversation's files, then the kept files of the knowledge bases the conversation's messages were written with (`GET /api/kb/files?conversationId=`, asked only for a name the conversation has no file for).
- **Other notes** place a kept file by its name too. `![[red-fox.png]]` is no link to a note: a target that ends like a file is left out of the links (`names_file()`).
- **Per knowledge base:** an agent with its own memory keeps its files apart, like its notes.
- **Family mode:** the file of a hidden note is hidden with it, and so is one that a note's text places only in hidden lines (what a hidden conversation adds to a note that isn't hidden is tagged, the line with its file too). On a device in family mode such a file is not found by the tools, the chat, the page or the export.
- **Gone with its note:** deleting a note for good (the page) deletes the files it keeps, unless a conversation or another note still has them. On the page a single file can be taken away from its note the same way. The agent can't delete files: it archives notes, and the files of an archived note stay readable by their names.

`backend/services/knowledge_base.py` ("Files") has the store; the files themselves are served by the files API, by their file ID, to their owner.

## Search

One query per search, over the user's active notes (the page can also search the archived ones):

- **Words:** Postgres full-text search with the `simple` configuration, so German and English work the same (no stemming, no stop words). A note matches if it contains any of the words, and words of four letters or more also match as prefixes ("katze" finds "Katzen"). Words in the title weigh most, then the description and tags, then the content.
- **Exact:** a case-insensitive substring of slug, title, description, tags or content. LIKE wildcards in it are literal.
- **Tags:** notes with any of them.
- **Score:** the word rank, plus 1 for each exact text the note contains, plus 0.3 for each of the tags it has. Ties go to the more recently updated note.

There is no index for this: a user's vault is small (SRW's agent-written notes have a median of 3 KB), so the user's rows are scanned. A generated `tsvector` column with a GIN index is the next step if that gets slow; `array_to_string` isn't immutable, so the tags would need their own handling there.

## The Knowledge base page

`/knowledge-base` and `/knowledge-base/<slug>` (`src/app/knowledge-base/`, loaded on demand; one route through `knowledgeBaseMatcher`, so the list stays when another note opens). The sidebar shows "Knowledge base" to signed-in users; `memberGuard` sends guests to the login. The page needs the server: the notes are only stored there, not in the browser.

- **Knowledge base:** with more than one, a picker above the search switches between the shared one and the agents' own ones (query parameter `vault`, kept by every navigation on the page).
- **Memory:** pinned above the notes, with how many of the 200 lines it uses; it opens like a note, with a banner explaining it and no archive action.
- **List:** search (the agent's search: any word, longer ones as prefixes, plus the text as a literal part of a note from three characters on), a switch between the notes and the archive with their counts, and the tags in use as filters. Search results show the passage around the match as plain text.
- **Note:** the Markdown rendered with ngx-markdown. `[[links]]` become links to the page (`noteMarkdown()` in `kb-markdown.ts`, outside of code); a link to a note that doesn't exist yet is dashed, and clicking it starts writing that note. Task boxes show as ☐ and ☑, because the sanitizer removes checkboxes. Below: "Links to" and "Linked from". At the top: the tags (they filter the list), and who changed the note last, when and in which chat (a link to the chat).
- **Files:** the files a note's text places are shown at their place, an image as the picture (never cropped), as in a chat answer (`NoteContentComponent` uses the chat's `answerParts()`); a click opens the preview, which steps through the note's images. The editor's preview and the history show them too. Under the note, **Files** lists what it keeps, with the name the agent goes by, pixels and size, and a button that takes a file away from the note (asked first: it deletes the file unless a chat still has it). In the list, a note that keeps an image shows a small preview of the first one; a click on it opens the image.
- **Edit:** title, description, tags (chips) and the Markdown with a preview; Ctrl+S saves. A new note's slug is shown while typing the title. If an agent changed the note meanwhile, the editor says so and offers "Save anyway" (the agent's version stays in the history) or "Discard my changes". Leaving the editor with unsaved changes asks first.
- **History:** every version with its action, author (you, or the agent's name) and time; one of them in full; "Restore this version" makes it the current one as a new version.
- **Archive, restore, delete:** archiving offers "Undo"; deleting for good asks first and removes all versions and the files the note keeps. The agent can only archive.
- **Export for Obsidian:** downloads the zip (below).

The frontend's `slugify()` matches the backend's (checked against it for umlauts, accents and other scripts).

## API (`backend/api/knowledge_base.py`)

All under `/api/kb`, for signed-in users only (guests get 403 with code `guest`), always the user's own notes. Every note endpoint takes the query parameter `vault` (0, the default: the shared knowledge base; else an agent's id), 404 `not_found` for a vault the user doesn't have:

| Endpoint | What it does |
|---|---|
| `GET /notes?status=&tag=` | Notes with the status (`active` or `archived`), newest first, with the tags in use and the counts per status |
| `GET /search?q=&status=` | Search hits with the passage around the match |
| `GET /notes/{slug}` | A note with its version, links, backlinks and versions (without content), the files it keeps (`files`: `[{fileId, name, mimeType, size, width, height, note, origin}]`) and the files of other notes that its text places (`placedFiles`) |
| `POST /notes` | A new note (author `user`); 409 `exists` with the existing note's slug |
| `PUT /notes/{slug}` | Replaces title, description, tags and content (the slug stays); `baseVersion`, else 409 `conflict` with the version now |
| `POST /notes/{slug}/archive`, `/restore` | Archive, or restore unchanged |
| `DELETE /notes/{slug}` | Delete for good, with the files it keeps |
| `DELETE /notes/{slug}/files/{name}` | Take a file away from its note; returns the note as it is then |
| `GET /files?conversationId=` | The files the notes of the knowledge base keep. With `conversationId`: the kept files the answers of that conversation can place, of the knowledge base its agent uses and of the ones its earlier messages were written with (none for somebody else's conversation) |
| `GET /notes/{slug}/revisions/{id}` | One version with its content |
| `POST /notes/{slug}/revisions/{id}/restore` | Makes that version the current one, as a new version (`baseVersion` as for an edit) |
| `GET /export?tz=` | The Obsidian zip with the notes' files (with the memory as `memory.md`; `knowledge-base-<agent>-<date>.zip` for an agent's own) |
| `GET /vaults` | The user's knowledge bases: the shared one, the own ones of the agents the user may use, and those of other agents that still have notes; with counts and memory lines |
| `GET /memory` | The memory of a knowledge base with its lines, characters and limits; `note` is null while it is empty |
| `POST /review` | `{conversationId}`: the memory review of that conversation now; `{status, detail, modelName, changes, reviewedUntil}` |

The notes in the lists and search hits carry their `files` too. Errors carry `{"code", "message"}` as detail: `not_found` (404), `exists` and `conflict` (409), `invalid` (400). Times are UTC with a `Z` (`UtcDatetime`).

## Obsidian export (`backend/services/knowledge_base_export.py`)

A zip with the folder `knowledge-base/`, which Obsidian opens as a vault:

- one `<slug>.md` per note, so the `[[slug]]` links resolve as they are (link view, graph, backlinks); archived notes in `knowledge-base/archive/` (Obsidian finds a link's file by name in any folder);
- the files notes keep in `knowledge-base/files/`, under their names in the knowledge base, so `![[red-fox.png]]` shows the image in Obsidian as it is. The zip is written to a temporary file and sent from there, since images add up (a kept file that is missing on disk is left out);
- YAML properties: `title`, `aliases` (the title, for Obsidian's link suggestions and search), `description`, `tags`, `created`, `updated`; then the title as a heading and the content;
- links not written as a slug are rewritten to one, keeping their text (`[[Project Apollo]]` becomes `[[project-apollo|Project Apollo]]`, `[x](Project%20Apollo.md)` becomes `[x](project-apollo.md)`); code stays as it is;
- tags as Obsidian accepts them: other characters than letters, digits, `_`, `-` and `/` become dashes, and a tag of only digits gets the prefix `tag-` (`2026` becomes `tag-2026`);
- times in the browser's time zone (the page sends it as `tz`; Obsidian reads times without a zone as local time), also the files' dates in the zip; UTC for an unknown zone.

Earlier versions aren't exported. Importing a vault is a later step: name clashes and folders need decisions first, and the export format should prove itself before.

## Postgres with pgvector

The compose files and the Helm chart run `pgvector/pgvector:pg16` (Debian) instead of `postgres:16-alpine`, so embeddings won't need an image change. Moving an existing data directory from Alpine (musl) to Debian (glibc) changes how text sorts, so its text indexes must be rebuilt.

`prepare_database()` in `backend/database/db.py` does this. It runs at backend start and in `app_init`. On a server that has pgvector, while the database doesn't have the extension yet, it runs `REINDEX DATABASE` if the database has no collation version (a database created under Alpine has none, while glibc reports one), then creates the extension. Postgres can't record a collation version for such a database later (`REFRESH COLLATION VERSION` refuses), so the extension is the marker that the rebuild has been done. If the rebuild fails, for example without owner rights, it is logged and tried again on the next start. A server without pgvector is only logged.

## Testing

- `python -m backend.llm.tests.run_all` (offline), `test_memory_snapshot`: the snapshot of the memory taken at the first answer, kept while the conversation goes on (the note with the lines added and removed and a new day), taken anew after a pause or with another knowledge base or family mode, and the note at the start of the newest user message.
- `python -m backend.llm.tests.run_all` (offline), the other scripts: the group is opt-in (with the memory tools), guests and requests without a user get nothing, the prompt section, the memory after it with today's date (only with the memory tools), the tool status, that writes record the conversation and its agent, and that an agent with own memory gets its own vault.
- `python backend/services/tests/knowledge_base_test.py`: the tools, the store and the API (FastAPI's test client on the knowledge base router) against a real Postgres, in a database `<POSTGRES_DB>_kb_test` that it creates itself. It covers:
  - slugs and link parsing (also links in code);
  - read-after-write;
  - refused duplicate slugs;
  - links and backlinks;
  - update rules;
  - search (German prefixes, title first, literal wildcards, tags);
  - archive and restore;
  - two users who can't see each other's notes;
  - revisions;
  - parallel tool calls;
  - cascade on user delete;
  - tool results that link their step to the note;
  - page edits with the version check, restoring a version or an archived note, deleting for good;
  - the Obsidian export (files, folders, properties, link rewriting, tags, time zones);
  - the API, also for another user and for guests;
  - the memory: dates, sections, duplicates, replace and remove by a part of the line (ambiguous and missing parts), the size limits, the other tools leaving it alone, lists and searches leaving it out, its links, page edits;
  - vaults: the same slug in two, searches and memories that stay in theirs, `list_vaults`, the export, the API's `vault`, `/vaults` and `/memory`;
  - the memory review against the fake OpenAI server of `backend/llm/tests`: what it sends, what it saves (author `review`), reading every message once, a failure and the retry, which conversations are due;
  - the nightly consolidation the same way: the period, the days and their week notes, the transcript and the changes it is given, the journal it writes (author `dream`), `memory_dreams`, nothing to do, a failure.
  - the memory snapshot on the real tables: storing and replacing it, the time of the newest answer, a line the agent saves going into the note, the cascade when the conversation is deleted.
  - the files notes keep (`test_notes_keep_files`, `test_hidden_files`, `test_files_api_and_export`), with real stored files in a temporary folder: a file's name and place in the text, a file kept already, names another note has, refusals that write nothing, search, list and read naming the files, `read_file` from another conversation and only with that knowledge base, a deleted conversation, a file taken away, a deleted note, the limit, two writes at once, hidden notes and hidden lines, the API and the export.

  The script runs `migrate_schema()` first, as `app_init --prod` does, because an old test database lacks columns that `schema.sql`'s triggers use.

## Not built yet

- **Embeddings (step 2):** a vector column next to the notes, filled from the homelab's Qwen3 embedding model, plus a semantic part in the search score. Keep the word and exact search as a fallback, because the router is flaky and SRW once lost its whole knowledge base to a missing embedding key. With a fixed dimension HNSW works up to 2000 dimensions (`halfvec` up to 4000). A per-user scan of an untyped `vector` column works without any index.
- **Search hits in the prompt:** besides the memory, the agent only sees notes it searches for or reads. SRW-style search hits for each message would help models that rarely search.
- **Import** of an Obsidian vault (see the export).
- **Adding a file on the page.** A note gets its files from an agent, in a chat: send the picture there and ask to keep it. The page shows them and takes them away, but has no upload.
- **Search by an image's looks.** Kept images are found by their notes' text. Image embeddings (SigLIP 2, Qwen3-VL-Embedding) could add "looks like" searches later.
- **A description written without the agent.** The note's text is what the agent writes. Nothing describes a kept image on its own, so a careless agent leaves an image that is hard to find.
- **A gallery of all kept images.** The list shows a note's first image, and the tag `image` filters to the image notes if the agent tagged them.
- **`[[links]]` in chat answers:** the agent mentions notes as `[[slug]]`, which the chat shows as plain text; they could link to the page.
- **A diff** between two versions in the history.
- **Memory:** the nightly consolidation in docker compose (Kubernetes only, by decision). The search over past conversations is built: `docs/past_chats.md`.
