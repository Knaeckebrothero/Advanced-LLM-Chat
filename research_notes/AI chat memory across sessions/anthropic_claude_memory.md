# How Anthropic's products handle long-term memory across sessions (as of 2026-11-01)

Scope: claude.ai memory and past-chat search, Claude Projects, Claude Code (CLAUDE.md and auto memory), the Anthropic API (memory tool, context editing, compaction, Managed Agents memory stores and "dreams"), Anthropic's engineering guidance, and known limitations. Every mechanism is described technically (what is stored, who writes it, when, how it gets back into the context). Help-center pages show only "Updated yesterday" with no calendar date, so they were taken as current on 2026-10-31/11-01. Reverse-engineered details are marked **UNOFFICIAL**.

Timeline (from the official release notes unless noted):
- 2025-08-11: past-chat search for Max, Team and Enterprise ([Release notes](https://support.claude.com/en/articles/12138966-release-notes))
- 2025-09-11: memory for Team; incognito chats for Free, Pro, Max and Team ([Release notes](https://support.claude.com/en/articles/12138966-release-notes); [Claude blog](https://claude.com/blog/memory))
- 2025-09-18: memory for Enterprise ([Release notes](https://support.claude.com/en/articles/12138966-release-notes))
- 2025-09-29: memory tool and context editing launched in public beta on the Developer Platform with Sonnet 4.5; "Effective context engineering" post published ([Claude blog](https://claude.com/blog/context-management); [Anthropic Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents))
- 2025-10-23: memory for Max, then Pro over the next two weeks ([Release notes](https://support.claude.com/en/articles/12138966-release-notes))
- 2025-11-26: "Effective harnesses for long-running agents" ([Anthropic Engineering](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents))
- 2026-03-02: memory from chat history for all users, Free included, plus memory import ([Release notes](https://support.claude.com/en/articles/12138966-release-notes))
- 2026-07-09: monthly recap ("A new way to reflect with Claude"), beta, needs memory on ([Release notes](https://support.claude.com/en/articles/12138966-release-notes))
- 2026-07-10: memory becomes "a set of individual, categorized entries", replacing the daily summary ([Release notes](https://support.claude.com/en/articles/12138966-release-notes))
- 2026-08-25: memory shared between chat and Cowork, editable "Topics", a sensitive-topics setting ([Release notes](https://support.claude.com/en/articles/12138966-release-notes); [TechCrunch](https://techcrunch.com/2026/08/25/claude-cowork-finally-remembers-what-you-told-the-app-in-chat/))

---

## 1. claude.ai memory ("memory from chats"): how it works today, plans, project memory, incognito, import/export, editing, prompt injection

### Takeaway
Since July/August 2026, claude.ai memory is a set of individual, categorized "Topics". Claude writes them **during** the chat (on its own or when asked to "remember this"), and the user can view, edit and delete each one. This replaced the 2025 design, a single memory summary regenerated about every 24 hours (still used by some legacy Team/Enterprise orgs). Memory is per project with inheritance from account memory. Sensitive categories (health, religion, politics, ...) stay out unless the user opts in, and a notice appears each time one is saved. Some categories are never saved. Anthropic does not document how the current Topics reach the prompt. For the 2025 design, an unofficial reverse-engineering found a `<userMemories>` block placed after the system prompt.

### Cited Findings

**Current storage and update model (2026)**
- "Memory on Claude now works as a set of individual, categorized entries" (2026-07-10), replacing the daily memory summary — [Release notes](https://support.claude.com/en/articles/12138966-release-notes)
- 2026-08-25: "Everything Claude remembers is listed under Topics in Settings > Memory." Items can be edited or deleted — [Release notes](https://support.claude.com/en/articles/12138966-release-notes)
- Memory is saved "as individual topics during chats", not as summaries written after conversations end. Claude "updates memory as you chat", either on its own or when you ask it to "remember this" — [Help center: chat search and memory](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- TechCrunch: Claude now adds topics to memory as you chat, instead of summarizing a conversation when it ends. Memories update faster and sync between chat and Cowork even while a chat is still going. Before, ideas from chat did not carry into Cowork — [TechCrunch, 2026-08-25](https://techcrunch.com/2026/08/25/claude-cowork-finally-remembers-what-you-told-the-app-in-chat/)
- What Claude remembers, per the help center: role, projects and professional context; people and places in your work and life; communication preferences and working style; technical preferences and coding style; project details and ongoing work — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- The import article says Claude "focuses memory on work-related topics", so imported personal details unrelated to work may not be kept — [Help center: import/export](https://support.claude.com/en/articles/12123587-importing-and-exporting-your-memory-from-claude)

**Legacy (superseded) model, 2025 to July 2026**
- The legacy experience generated a memory summary updated every 24 hours, plus a separate project summary for each project. Some Team/Enterprise orgs still use it — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- Imports in the legacy experience show up "within 24 hours". In the new experience they show up "shortly" — [Help center: import/export](https://support.claude.com/en/articles/12123587-importing-and-exporting-your-memory-from-claude)
- Legacy users manage "memory edits" instead of memory entries — [Help center: import/export](https://support.claude.com/en/articles/12123587-importing-and-exporting-your-memory-from-claude)
- The September 2025 launch post: memory was "designed for work use" and "avoids sensitive conversations and topics". At setup, Claude could generate memory from past chats. Users could view and edit the summary in settings and update it by chatting ("tell Claude what to focus on or ignore") — [Claude blog: memory](https://claude.com/blog/memory)
- **UNOFFICIAL** (reverse-engineered by prompting Claude, Dec 2025; the author warns of hallucination and run-to-run variance): prompt order was system prompt → `<userMemories>` block → conversation history → current message. `<userMemories>` held a bulleted list of distilled facts (name, location, role, preferences, projects, expertise). Implicit updates ran periodically in the background, not immediately. Explicit edits ("remember this", "delete this from memory") went through a tool named `memory_user_edits` — [Manthan Gupta, 2025-12-14](https://manthanguptaa.in/posts/claude_memory). The official mention of legacy "memory edits" ([Help center: import/export](https://support.claude.com/en/articles/12123587-importing-and-exporting-your-memory-from-claude)) is consistent with this.

**Plans**
- Memory is on by default for Free, Pro, Max and Ultra on web, desktop and mobile (mobile needs the latest app). On Team and Enterprise, owners decide whether memory is available, and it stays off for each member until the member turns it on — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- Free users got memory on 2026-03-02 ("Memory from chat history is now available for all Claude users, including free users") — [Release notes](https://support.claude.com/en/articles/12138966-release-notes). The press linked the launch to users leaving ChatGPT — [MacRumors (search snippet only)](https://www.macrumors.com/2026/03/02/anthropic-memory-import-tool/)
- The new memory experience is not available to HIPAA or public-sector organizations — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- Editor's note on the blog: mentions of "Max" before 2026-10-30 include today's Max and Ultra plans — [Claude blog: memory](https://claude.com/blog/memory)

**Project memory**
- Each project has its own memory. Inside a project, Claude uses that project's memory plus your non-project account memory, but never another project's memory. New memories go to the project. Turning off "Use account memory" on the project page separates the project completely — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- Project memory is deleted with the project — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- Memory is shared between chat and Cowork in the cloud. Local Cowork sessions don't use memory. Claude Duet (a research preview) uses memory and adds to it — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)

**Controls**
- Per chat: in a new chat, click "+" and turn off "Memory" before the first message. The switch can't change after the chat starts (mobile shows it locked). The chat stays in history and remains searchable, unlike an incognito chat — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- Per account: Settings > Your Claude > "Memory from chats". **Pause** keeps existing memories but stops both using them and making new ones; conversations during the pause are not added later. **Reset** permanently deletes all memories, project memories included, and "cannot be undone" — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- Viewing and editing: Settings > Your Claude > "Manage" next to "Your memory". Memories are listed under Topics; each can be opened, edited or deleted. Users can also tell Claude in chat to remember, change or forget something. Changes apply to future conversations — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context). There is also a "Tell Claude what to change or remove" box — [Help center: import/export](https://support.claude.com/en/articles/12123587-importing-and-exporting-your-memory-from-claude)

**Sensitive topics (directly relevant to a therapist persona)**
- Off by default. Covers health, race, ethnicity, religious beliefs, politics, gender identity and similar areas. Opt-in toggle: "Include sensitive topics in memory". Once it is on, Claude shows a notice above the message box **each time** it saves a sensitive memory. Earlier conversations are not saved retroactively. Declining the notice, or turning the setting off, removes sensitive items already saved — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- Never saved, even on request: government ID numbers, criminal history, financial account numbers, immigration status — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context). TechCrunch's list differs slightly: government IDs, Social Security numbers, criminal history, immigration status, "anything violating its acceptable use policy" — [TechCrunch](https://techcrunch.com/2026/08/25/claude-cowork-finally-remembers-what-you-told-the-app-in-chat/)
- On Team/Enterprise, each user must opt in to sensitive topics; owners can't view or edit individual memories — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- Before the October 2025 Pro/Max rollout, Anthropic ran safety tests on sensitive wellbeing topics and edge cases. They checked whether memory could reinforce harmful patterns, cause over-accommodation, or help bypass safeguards, and made "targeted adjustments" as a result — [Claude blog: memory](https://claude.com/blog/memory)

**Incognito**
- Incognito chats are not saved to memory or chat history, and existing memory stays unchanged — [Claude blog: memory](https://claude.com/blog/memory)
- Incognito chats are kept at least 30 days for safety. On Enterprise/Team they appear in data exports and follow the retention policies — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)

**Import/export**
- Labelled experimental. Available on Free, Pro, Max, Ultra, Team and Enterprise, on web and desktop. Steps: copy Anthropic's prompt into the other assistant; the prompt asks it to list every stored memory in one code block, dated where possible. Paste the result under Settings > Your Claude > "Start import" > "Add to memory". Claude extracts the key details and stores them as individual entries. "See what Claude learned about you" opens a check-up chat. Claude "may not always incorporate imported memories" — [Help center: import/export](https://support.claude.com/en/articles/12123587-importing-and-exporting-your-memory-from-claude)
- Export: open the memory under "Manage" and copy it, or ask Claude in chat to write out its memories verbatim. Plain text only; no export file format is documented — [Help center: import/export](https://support.claude.com/en/articles/12123587-importing-and-exporting-your-memory-from-claude). All memory data is included in the account data exports — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)

**Retention**
- Deleting a conversation does **not** delete the memory entries generated from it. Custom retention periods apply to memory (except project memory): entries not updated within the period are deleted, and parts of entries can be removed. Turning memory off for an org permanently deletes all of its memory data. Audit logs record owner toggles but not individual members' edits — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- Monthly recap (beta, Free/Pro/Max, 2026-07-09) requires memory to be on — [Release notes](https://support.claude.com/en/articles/12138966-release-notes). Pausing or resetting memory also hides the recap (legacy experience) — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)

### Inferences
- The shift from "summary written after the conversation / every 24 h" to "topics written during the chat" mirrors Claude Code's auto memory (one fact per file, written by the model while it works). The claude.ai Topics are most likely written through a model-invoked tool and injected as a compact list or index each turn. This is an inference; Anthropic has not documented it.
- Pattern for the therapist persona: (a) per-persona memory, like project memory, with an option to also inherit account memory; (b) health counts as a "sensitive topic", which Anthropic keeps out by default and gates behind explicit opt-in plus a visible notice per save. A therapist persona needs that consent flow, since nearly everything it should remember is sensitive; (c) a never-store list; (d) per-chat "memory off" fixed at chat start; (e) pause vs reset semantics; (f) deleting a chat does not cascade to memory unless the app chooses to (Anthropic chose not to).
- Anthropic's own wellbeing testing (reinforcing harmful patterns, over-accommodation) is the risk most relevant to a therapy persona: injected memory can anchor the model on old framings.

### Gaps
- No official description of how current (2026) Topics are injected into the prompt (always-on list vs index vs retrieval), how many are injected, or the name of the write tool. The only injection detail is the unofficial Dec 2025 `<userMemories>` finding, which predates the July 2026 rebuild.
- Penligent's write-up of a leaked "Claude Fable 5.1" system prompt (Sept 2026, published by Pliny on GitHub, ~270k characters) says it contains memory rules, but the write-up names no tags or tools. The raw file was not retrieved — [Penligent](https://www.penligent.ai/hackinglabs/claude-fable-5-1-system-prompt-leak/)
- Whether the July 10 (categorized entries) and August 25 (Topics, Cowork) changes were one rollout or two: the release notes list them separately; third-party blogs disagree.
- The help center contradicts itself on Team org-level controls (legacy section: none; current section: owners decide).

---

## 2. claude.ai past-chat search (conversation_search, recent_chats): how it works, when Claude calls it, difference from injected memory

### Takeaway
Chat search is a separate, model-invoked RAG tool, not always-injected context. It appears as a visible tool call, is scoped to the current project (or to non-project chats), cites and links the source chats, is limited to paid plans, and has its own toggle ("Search and reference chats"). Unofficially, there are two tools: `conversation_search(query, max_results)` for topic search and `recent_chats(n, sort_order, before, after)` for time-based retrieval. Both return snippets wrapped in `<chat url updated_at>`. Recall depends on the model choosing to call them, so it is non-deterministic.

### Cited Findings
- Chat search uses RAG. Searches "will appear as tool calls during your conversations". It is on by default once rolled out; users ask naturally ("What did we discuss about [topic]?"). Results cite and link the source chats — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- Scope: all non-project chats, or the chats inside one project. Searches never cross project boundaries — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- Plans: paid only (Pro, Max, Ultra, Team, Enterprise). Toggle: Settings > Your Claude > "Search and reference chats", which also controls Claude Duet's access — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- Launched 2025-08-11 for Max, Team and Enterprise — [Release notes](https://support.claude.com/en/articles/12138966-release-notes)
- Enterprise customer-managed encryption keys disable chat search because the content is encrypted — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- **UNOFFICIAL** tool schemas, from Claude's self-report:
  - `conversation_search`: `query` (string, required), `max_results` (int 1–10, default 5)
  - `recent_chats`: `n` (int 1–20, default 3), `sort_order` ('asc' or 'desc', default 'desc'), optional ISO datetime `before`/`after`
  - Both return `<chat url="claude.ai/chat/{uri}" updated_at="...">` elements holding the title and short snippets of the human and assistant messages
  - Neither runs on every request; Claude calls them only when it judges past context relevant, so it can miss history
  - [Manthan Gupta, 2025-12-14](https://manthanguptaa.in/posts/claude_memory)
- **UNOFFICIAL**: tool descriptions quoted by Simon Willison: conversation_search: "Search through past user conversations to find relevant context and information". recent_chats: "Retrieve recent chat conversations with customizable sort order (chronological or reverse chronological)", with optional `before`/`after` pagination and project filtering — [Simon Willison, 2025-09-12](https://simonwillison.net/2025/Sep/12/claude-memory/)
- Design contrast in August/September 2025 (before memory reached individual plans): Claude started every chat from a blank slate, and memory activated only when invoked, by searching raw past chats with no generated profile. ChatGPT, by contrast, automatically injected details of previous conversations into every chat. Willison valued that Claude's recall was visible as tool calls — [Simon Willison](https://simonwillison.net/2025/Sep/12/claude-memory/). This "no summaries, just search" description is **superseded**: the September 2025 memory summary and the 2026 Topics add always-available memory alongside search.

### Inferences
- Two complementary layers worth copying: (1) small, curated memory that is always present (or indexed); (2) on-demand search over the full transcript archive, exposed as a tool with project/persona scoping and links back to the source chats. The app already stores conversations in PostgreSQL. A `conversation_search` tool (full-text or embeddings, filtered by user and persona) plus `recent_chats(n, before, after)` would be straightforward and works with any tool-calling model, OpenAI-compatible ones included.
- For a therapist persona, `recent_chats(n=1..3)` ("what did we talk about last session") is probably more valuable than topic search, and could even run deterministically at session start instead of relying on the model to call it.

### Gaps
- No official tool names, schemas, ranking method (embedding vs keyword) or snippet length. Pro's chat-search start date is not in the release notes.

---

## 3. Claude Projects: project knowledge, instructions, RAG beyond the context window, project-scoped memory

### Takeaway
A project bundles uploaded knowledge, instructions, its own chats, its own memory and its own chat-search scope. Project knowledge is placed in the context while it fits. Once it nears the window limit, Claude switches automatically to a "project knowledge search" RAG tool, which raises capacity about 10x. Project memory is isolated from other projects but can inherit account memory.

### Cited Findings
- RAG activates automatically when project knowledge nears or exceeds the context-window limit. A visual indicator marks RAG-enabled projects, and a project switches back to in-context processing if its knowledge shrinks. Capacity is "up to 10x" what the context window used to allow. Claude retrieves through a "project knowledge search tool". Users cannot force RAG on or off. Paid plans only (Pro, Max, Ultra, Team, Enterprise). Best practice: descriptive filenames, and naming documents in questions — [Help center: RAG for projects](https://support.claude.com/en/articles/11473015-retrieval-augmented-generation-rag-for-projects)
- Project memory: separate per project, plus account memory unless "Use account memory" is off; it is deleted with the project; the legacy experience kept a per-project summary — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- The September 2025 blog presented project-scoped memory as a way to keep "unrelated and confidential work apart" — [Claude blog: memory](https://claude.com/blog/memory)
- Chat search inside a project covers only that project's chats — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)

### Inferences
- The Advanced LLM Chat "persona" corresponds to a Claude Project: persona prompt = project instructions, persona knowledge = project knowledge, and per-persona memory with optional inheritance of user-level memory = project memory. Using in-context loading while it fits and switching to retrieval beyond a threshold is a simple, transparent policy to copy.

### Gaps
- Project instructions were not re-verified on a current page this session (how they combine with the system prompt). No launch date for project RAG or a token threshold was found. The tool's formal identifier is unconfirmed (`project_knowledge_search` is commonly cited but not on the official page).

---

## 4. Claude Code: CLAUDE.md hierarchy, rules, auto memory (MEMORY.md + one-fact files), /memory, compaction interaction

### Takeaway
Claude Code has two layers. **CLAUDE.md** files are written by humans and loaded in full at launch along a fixed hierarchy (managed policy → user → project → local, then subdirectories on demand, plus `@imports` and `.claude/rules/` with optional path globs). **Auto memory** is written by Claude: a per-repository directory with a `MEMORY.md` index (one line per memory; the first 200 lines / 25 KB are injected every session) and one topic file per memory with typed YAML frontmatter (`user`, `feedback`, `project`, `reference`) and a `modified` timestamp. Topic files are read on demand. After compaction both are re-injected from disk.

### Cited Findings

**CLAUDE.md hierarchy**
- Load order, broadest to most specific (later = read last):
  - managed policy: macOS `/Library/Application Support/ClaudeCode/CLAUDE.md`, Linux/WSL `/etc/claude-code/CLAUDE.md`, Windows `C:\Program Files\ClaudeCode\CLAUDE.md`
  - user `~/.claude/CLAUDE.md`
  - project `./CLAUDE.md` or `./.claude/CLAUDE.md` (AGENTS.md can load instead or alongside)
  - local `./CLAUDE.local.md` (gitignored)
  - [Claude Code docs: memory](https://code.claude.com/docs/en/memory)
- Files in the working directory and every ancestor load at launch and are **concatenated**, not overridden, root first. Within a directory, CLAUDE.local.md comes after CLAUDE.md. Subdirectory CLAUDE.md files load once Claude reads, writes or edits a file in that subdirectory. Block-level HTML comments are stripped before injection. Files over 4 MiB are skipped entirely — [Claude Code docs: memory](https://code.claude.com/docs/en/memory)
- `@path/to/file` imports: relative to the importing file, recursive up to four hops, skipped inside code spans and fences. Imports help organization but don't save context — [Claude Code docs: memory](https://code.claude.com/docs/en/memory)
- `.claude/rules/*.md`, discovered recursively: rules without frontmatter load at launch with the same priority as `.claude/CLAUDE.md`. Rules with `paths:` glob frontmatter (the only frontmatter field read) load only when Claude works with matching files. User-level rules live in `~/.claude/rules/` and load before project rules; neither set overrides the other — [Claude Code docs: memory](https://code.claude.com/docs/en/memory)
- On-demand files over a per-file limit (40,000 characters for a 200K window; 150,000–200,000 for 1M windows, by model) are truncated, with a note telling Claude to read the rest — [Claude Code docs: memory](https://code.claude.com/docs/en/memory)

**Auto memory**
- Claude writes four kinds of notes, with a `type` frontmatter field:
  - `user`: role, expertise, working preferences
  - `feedback`: corrections the user gives and approaches the user confirms
  - `project`: ongoing work, deadlines and decisions that can't be derived from the code or git
  - `reference`: where to find outside information
  - It skips anything derivable from the codebase or already stated in CLAUDE.md, and doesn't save something every session; it saves only what would be useful in a future conversation. "Remember X" saves to auto memory; "add this to CLAUDE.md" edits CLAUDE.md instead — [Claude Code docs: memory](https://code.claude.com/docs/en/memory)
- Storage: `~/.claude/projects/<project>/memory/` (derived from the git repository, so it is shared across worktrees and subdirectories). It holds `MEMORY.md` ("Index, one line per memory, loaded into every session") plus one topic file per memory. Machine-local, not synced. Excluded from the transcript-cleanup sweep. `autoMemoryDirectory` relocates it — [Claude Code docs: memory](https://code.claude.com/docs/en/memory)
- Loading: the first 200 lines or 25 KB of MEMORY.md, whichever comes first, are injected at the start of every conversation; topic files are **not** loaded at startup but read on demand with the normal file tools. After each write to MEMORY.md, Claude Code measures it against the limits: near a limit, it reminds Claude to keep one line per entry, move detail into topic files, and merge or drop stale entries; over a limit, the write succeeds but Claude Code returns an error telling Claude to rewrite the index — [Claude Code docs: memory](https://code.claude.com/docs/en/memory)
- When Claude writes a memory file that starts with YAML frontmatter, Claude Code records a `modified` ISO 8601 timestamp, "so the timestamp shows how current the fact is" to both the user and Claude — [Claude Code docs: memory](https://code.claude.com/docs/en/memory)
- Local observation (this machine, Claude Code session of 2026-11-01), showing the actual format:
  - MEMORY.md lines look like `- [Title](file.md) — one-line hook`
  - each topic file has frontmatter `name`, `description`, `metadata: {node_type: memory, type: feedback, originSessionId, modified}`, then a short body stating the fact and why
  - local file: `~/.claude/projects/<project>/memory/check-ui-live-in-browser.md` (this project's Claude Code memory)
- The UI shows "Saved 2 memories" / "Recalled 2 memories" when Claude writes or reads memory — [Claude Code docs: memory](https://code.claude.com/docs/en/memory)
- On by default in local sessions; off by default in self-hosted environments. Toggle in `/memory` (saved as `autoMemoryEnabled`), per project via settings, or with `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`. Subagents don't get the main auto memory (forks do) but can have their own via the subagent `memory` field — [Claude Code docs: memory](https://code.claude.com/docs/en/memory)
- `/memory` lists CLAUDE.md/CLAUDE.local.md files across scopes, toggles auto memory and opens the memory folder; `/context` shows what loaded — [Claude Code docs: memory](https://code.claude.com/docs/en/memory)
- Launch timing: secondary sources say auto memory arrived around February–March 2026; no official version or date was found — [Engineer's Codex](https://www.engineerscodex.com/claude-code-auto-memory); [To Data & Beyond](https://todatabeyond.substack.com/p/claude-code-memorymd-everything-you) (search snippets only)

**Compaction interaction**
- After `/compact` or auto-compaction:
  - re-injected from disk: system prompt, project-root CLAUDE.md, unscoped rules, **auto memory**, and the plan-mode plan
  - reloaded on demand: path-scoped rules and nested CLAUDE.md files
  - re-read: up to five recently modified files (a file over 5,000 tokens comes back only as a path reference)
  - re-injected with caps: invoked skill bodies (5,000 tokens each, 25,000 total)
  - SessionStart hooks matching `compact` run again
  - summarized away: anything given only in conversation
  - [Claude Code docs: context window](https://code.claude.com/docs/en/context-window)
- `/compact <focus instructions>` steers the summary. `/autocompact <tokens>` sets the threshold. The summarization request inherits the session's extended-thinking setting (v2.1.198+) — [Claude Code docs: context window](https://code.claude.com/docs/en/context-window)
- In Claude Code's compaction, the model keeps architectural decisions, unresolved bugs and implementation details, drops redundant tool output, and continues with the summary plus the five most recently accessed files — [Anthropic Engineering: context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

### Inferences
- The most directly copyable design for the app: per (user, persona), keep a `MEMORY.md`-style index (bounded by lines/bytes, one line per fact with a hook) that is **always injected into the system prompt**, plus one-fact records with `type` and `modified`, read on demand through a tool. Enforce the size budget in code, and nudge the model to consolidate when it nears the cap. Keep memory **outside the history**, as the app already does for system messages (`with_instructions()`), so the rolling summary and the context cut never drop it. This is exactly how Claude Code re-injects auto memory after compaction.
- The four Claude Code types translate to a therapy persona roughly as user (biography, preferences), feedback (what helped or didn't, the client's corrections), project (ongoing goals, homework, agreed next steps), and reference (external resources or referrals).

### Gaps
- The exact system-prompt wording Claude Code uses to tell the model when and how to write auto memory is not published on the docs page (the docs describe the behaviour only).

---

## 5. Anthropic API: memory tool, context editing, compaction, Managed Agents memory stores and dreams, and how they combine

### Takeaway
The **memory tool** (`{"type": "memory_20250818", "name": "memory"}`) is a client-side, file-shaped tool with six commands (view, create, str_replace, insert, delete, rename) under a virtual `/memories` root. The app stores the data. When the tool is present, the API automatically adds a "view your memory directory first" protocol to the system prompt. It is stable (no beta header now), and eligible for ZDR and HIPAA. **Context editing** (beta) clears old tool results and thinking server-side and warns Claude to save to memory before clearing. **Compaction** (beta; threshold `compact_20260112` or on-demand `compact-2026-09-04`) summarizes the conversation server-side. Anthropic recommends compaction plus memory for long-running agents. **Managed Agents** add hosted memory stores (mounted as directories, versioned, auditable) and "dreams", an offline consolidation job.

### Cited Findings

**Memory tool**
- Tool entry: `{"type": "memory_20250818", "name": "memory"}`. The name must be `memory`, and no input schema is defined. The tool runs client-side, and the app maps `/memories` onto its own storage (e.g. a per-user directory or database keys). It is "available on all Claude 4 and later models". Status: stable; "the memory tool itself doesn't require a beta header". Eligible for ZDR (except Covered Models) and HIPAA — [Docs: memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- Launched 2025-09-29 in public beta, together with context editing. Internal agentic-search eval: memory + context editing +39% over baseline, context editing alone +29%. In a 100-turn web-search eval, context editing cut token use by 84% — [Claude blog: context management](https://claude.com/blog/context-management)
- Commands and reference return strings ([Docs: memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)):
  - `view {path, view_range?}`. A directory returns "Here're the files and directories up to 2 levels deep in {path}, excluding hidden items and node_modules:" followed by `{size}\t{path}` lines. A file returns "Here's the content of {path} with line numbers:" with 6-wide right-aligned 1-indexed numbers and a tab. Claude's tool description says view truncates files longer than 16,000 characters and can show .jpg/.png images
  - `create {path, file_text}`. Returns "File created successfully at: {path}". The reference errors if the file exists, but Claude's description says it "creates or overwrites", so overwriting is acceptable
  - `str_replace {path, old_str, new_str?}`. Errors if old_str is missing or not unique
  - `insert {path, insert_line, insert_text}`. Inserts after line N; 0 means the beginning
  - `delete {path}`. Recursive for directories; the `/memories` root itself must be rejected
  - `rename {old_path, new_path}`. Never overwrites; rejects renaming the root
  - Errors come back as a `tool_result` with `is_error: true`
- Auto-injected system prompt text (verbatim):
  ```
  IMPORTANT: ALWAYS VIEW YOUR MEMORY DIRECTORY BEFORE DOING ANYTHING ELSE.
  MEMORY PROTOCOL:
  1. Use the `view` command of your `memory` tool to check for earlier progress.
  2. ... (work on the task) ...
     - As you make progress, record status / progress / thoughts etc in your memory.
  ASSUME INTERRUPTION: Your context window might be reset at any moment, so you risk losing any progress that is not recorded in your memory directory.
  ```
  Optional reinforcement against clutter: "Note: when editing your memory folder, always try to keep its content up-to-date, coherent and organized. You can rename or delete files that are no longer relevant. Do not create new files unless necessary." Scoping example: "Only write down information relevant to <topic> in your memory system." — [Docs: memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- SDK helpers: `BetaAbstractMemoryTool` (Python, C#), `betaMemoryTool` (TypeScript), `BetaMemoryToolHandler` (Java), a ready-made `BetaLocalFilesystemMemoryTool` (Python and TypeScript), and the tool runner `client.beta.messages.tool_runner(...)` — [Docs: memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- Security, as Anthropic advises:
  - Claude "usually refuses" to write sensitive information; strip it in the handler for stronger guarantees
  - cap file sizes and the characters `view` returns
  - periodically delete memory files not accessed in a long time ("memory expiration")
  - validate every path against traversal (`../`, `..\`, `%2e%2e%2f`); resolve to canonical form and check it stays under the root (e.g. Python `Path.resolve()`/`relative_to()`)
  - [Docs: memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- Multi-session pattern: an initializer session sets up the memory files (progress log, feature checklist, startup script); each later session starts by reading them and updates the progress log before it ends; mark a feature complete only after end-to-end verification — [Docs: memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)

**Context editing (beta, header `context-management-2025-06-27`)**
- `clear_tool_uses_20250919` clears the oldest tool results first and replaces each with a placeholder. Parameters: `trigger` (default 100,000 input_tokens; or tool_uses), `keep` (default 3 tool uses), `clear_at_least`, `exclude_tools`, `clear_tool_inputs` (default false). Clearing invalidates the prompt cache from that point. Edits run server-side; the client keeps the full history. The response reports `context_management.applied_edits` — [Docs: context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- `clear_thinking_20251015` sets how many thinking turns to keep (model-specific defaults). It must be listed before tool clearing — [Docs: context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- With `memory_20250818` and `clear_tool_uses_20250919` together, Claude receives an automatic warning to save important information to memory before tool results are cleared — [Docs: context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)
- The page now recommends server-side compaction for most long-running conversations. The SDK's client-side `compaction_control` is deprecated (removed in Python v1.0); it injected a summary prompt, took a `<summary>` reply and replaced the history with it (default threshold 100,000 tokens) — [Docs: context editing](https://platform.claude.com/docs/en/build-with-claude/context-editing)

**Compaction (beta)**
- Two server-side modes: **threshold compaction** (header `compact-2026-01-12`, edit `compact_20260112` in `context_management.edits`) and **on-demand compaction** (header `compact-2026-09-04`, top-level `compaction` parameter; recommended "wherever it is available"; supports keeping recent turns verbatim and running in the background) — [Docs: compaction overview](https://platform.claude.com/docs/en/build-with-claude/compaction)
- Threshold parameters: `trigger` (default 150,000 input_tokens, minimum 50,000), `pause_after_compaction` (returns `stop_reason: "compaction"`), `instructions` (replaces the default prompt entirely). The response starts with a `{"type":"compaction","content":...}` block; the client appends it as usual, and the API ignores everything before the last compaction block. The block is cacheable with `cache_control`. Usage per step appears in `usage.iterations` — [Docs: compaction threshold](https://platform.claude.com/docs/en/build-with-claude/compaction-threshold)
- Default summarization prompt (verbatim, for "some models"): "You have written a partial transcript for the initial task above. Please write a summary of the transcript. The purpose of this summary is to provide continuity so you can continue to make progress towards solving the task in a future context, where the raw history above may not be accessible and will be replaced with this summary. Write down anything that would be helpful, including the state, next steps, learnings etc. You must wrap your summary in a <summary></summary> block." — [Docs: compaction threshold](https://platform.claude.com/docs/en/build-with-claude/compaction-threshold)
- How they combine: "compaction keeps the active context small without client-side bookkeeping, and memory preserves the information that must survive summarization" — [Docs: memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)

**Managed Agents memory stores (beta, header `agent-memory-2026-07-22`)**
- A memory store is "a workspace-scoped collection of text documents", mounted in the session sandbox at `/mnt/memory/<slug>/`. The agent uses its normal file tools. A note describing each mount (name, path, access mode, description, instructions up to 4,096 characters) is added to the system prompt automatically. Access is `read_write` (default) or `read_only`, enforced at the filesystem level. Up to 8 stores per session, attached only at session creation. Each memory is capped at 100 kB (~25k tokens), and a store holds at most 10,000 memories; the docs advise "many small focused files, not a few large ones". Every change creates an immutable `memver_…` version (kept 30 days; current versions always kept). Versions can be redacted (PII, deletion requests). Optimistic concurrency uses a `content_sha256` precondition. Not ZDR or HIPAA eligible — [Docs: Managed Agents memory](https://platform.claude.com/docs/en/managed-agents/memory)
- Prompt-injection warning: with `read_write`, injected content can be "written into the store. Later sessions then read that content as trusted memory." — [Docs: Managed Agents memory](https://platform.claude.com/docs/en/managed-agents/memory)
- Suggested layouts: one store per end user, team or project; a shared read-only reference store kept separate from each session's read-write store — [Docs: Managed Agents memory](https://platform.claude.com/docs/en/managed-agents/memory)

**Dreams (research preview, headers `managed-agents-2026-04-01, dreaming-2026-04-21`)**
- Purpose: over many sessions, incremental writes pile up "duplicates, contradictions, and stale entries". A dream is an async job that reads one memory store plus 1–100 past session transcripts and writes a **new** output store: duplicates merged, stale or contradicted entries replaced with the latest value, new insights surfaced. The input store is never modified, so the result can be reviewed and discarded. Optional `instructions` steer the synthesis (e.g. "Focus on coding-style preferences; ignore one-off debugging notes."). A run takes minutes to hours and is billed at standard token rates — [Docs: dreams](https://platform.claude.com/docs/en/managed-agents/dreams)

### Inferences
- The memory tool's interface is model-agnostic: it is six file commands with plain-text results. For OpenAI-compatible models (Kimi, DeepSeek, GLM, Gemma), the app can declare the same command set as an ordinary JSON-schema function tool, put the memory-protocol text into its own system prompt, and serve both providers from one handler in PostgreSQL (path → row). For Anthropic models it can send the native `memory_20250818` type instead. This is an inference; Anthropic's built-in tool description is not published in full.
- For a chat (not agent) product, "always view memory first" costs a tool round-trip every turn. The Claude Code approach (inject the index, fetch details on demand) avoids the first call and fits a therapy chat better.
- Dreams suggest a cheap periodic job for the app: e.g. nightly or after N sessions, a model reads the persona's memory plus recent transcripts and proposes a consolidated version. The user or app reviews it before swapping it in, which addresses stale and contradictory memories without in-place destructive edits.
- Versioning with redaction and `content_sha256` preconditions are good patterns for a sensitive-data store (audit trail, right to deletion, concurrent writes from parallel chats).

### Gaps
- Exact GA date of the memory tool and whether it originally needed the `context-management-2025-06-27` beta header (believed so from training knowledge; not verified this session). The exact placeholder text for cleared tool results and the wording of the "save to memory before clearing" warning are not documented. Launch dates of compaction and memory stores are inferred only from their beta-header dates (2026-01-12, 2026-09-04, 2026-07-22) and are not confirmed.

---

## 6. Anthropic engineering guidance on memory and context engineering for agents

### Takeaway
Anthropic's guidance treats context as a finite "attention budget" that suffers from "context rot". It recommends a hybrid: preload a small amount of stable context (like CLAUDE.md), retrieve the rest just in time through tools, compact long histories with a recall-first summary, and keep **structured notes outside the context window** that the agent reads back after resets. For multi-session work it recommends durable, structured state files plus a fixed startup and shutdown routine.

### Cited Findings
- "Context, therefore, must be treated as a finite resource with diminishing marginal returns." The goal is "the smallest set of high-signal tokens that maximize the likelihood of your desired outcome." Recall degrades as context fills ("context rot") — [Anthropic Engineering, 2025-09-29](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Just-in-time retrieval: keep lightweight identifiers (paths, queries, links) and load the data through tools at runtime. A hybrid (preload CLAUDE.md, then glob/grep) works well and may suit less dynamic domains — [Anthropic Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Compaction: "tune for recall first", then improve precision. Tool-result clearing is the lightest form of compaction — [Anthropic Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Structured note-taking: the agent writes notes outside the context window (to-do lists, a NOTES.md) and reads them back later. In the Pokémon example, Claude kept progress, maps and strategy notes across thousands of steps and resumed after context resets, without being prompted to use a memory structure. The memory tool provides this as file-based storage — [Anthropic Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Choose by task: compaction for long back-and-forth, note-taking for iterative work with milestones, sub-agents for parallel research (they return 1,000–2,000-token summaries) — [Anthropic Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Long-running harness:
  - compaction alone was insufficient
  - an initializer agent writes `init.sh`, `claude-progress.txt`, `feature_list.json` (200+ features marked failing) and an initial git commit
  - each coding session reads the progress file and git log, picks one feature, verifies it end-to-end, commits and updates progress
  - JSON was chosen for the feature list because models are less likely to wrongly overwrite it than Markdown, and agents may only flip the `passes` field
  - [Anthropic Engineering, 2025-11-26](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)

### Inferences
- Applied to the therapist persona:
  - preload a short, structured client profile and a "last session" note (stable, high-signal)
  - expose search over earlier sessions as a tool (just in time)
  - at the end of each session, have the model write a structured session note (topics, the client's own words for key issues, agreed homework, open threads, risk flags), much like `claude-progress.txt`
  - start the next session by reading it
  - use a structured format (JSON or typed fields) for fields the model shouldn't freely rewrite
- The app's existing rolling summary is the "compaction" layer for one conversation. Cross-session memory should be a separate layer that compaction never touches.

### Gaps
- No Anthropic guidance found specific to memory in consumer chat or companionship/therapy settings beyond the wellbeing safety-testing note in the September 2025 memory blog.

---

## 7. Known criticisms and limitations (privacy, accuracy, stale memories, user control)

### Takeaway
The main documented issues: deleting chats doesn't delete derived memories; recall through search is non-deterministic; the legacy summary lagged up to 24 h; imports are experimental and biased toward work; memory can carry bad context into fresh chats or anchor the model; memory written from untrusted input is a prompt-injection channel; member edits aren't audit-logged; the new memory isn't offered to HIPAA orgs. Anthropic's mitigations: visible tool calls, editable Topics, pause vs reset, per-chat off switch, incognito, sensitive-topic opt-in with per-save notices, never-store categories, and (for Managed Agents) read-only mounts, versioning and redaction.

### Cited Findings
- Simon Willison's main complaint about memory (aimed at ChatGPT) is a lack of transparency about what enters the context. He also feared memory would undermine starting fresh chats to escape bad context. He welcomed Claude's visible tool calls and the viewable, editable summary — [Simon Willison, 2025-09-12](https://simonwillison.net/2025/Sep/12/claude-memory/)
- Tool-based recall is non-deterministic: Claude may miss relevant history if it doesn't decide to search — [Manthan Gupta (UNOFFICIAL)](https://manthanguptaa.in/posts/claude_memory)
- Deleting a conversation does not remove its memory entries. Owners can't view members' memories, and member edits are not logged. Incognito chats are kept at least 30 days. The new memory isn't available to HIPAA or public-sector orgs. Customer-managed keys disable chat search — [Help center](https://support.claude.com/en/articles/11817273-using-claude-s-chat-search-and-memory-to-build-on-previous-context)
- Imports are experimental, "may not always" be incorporated, and personal details unrelated to work may be dropped — [Help center: import/export](https://support.claude.com/en/articles/12123587-importing-and-exporting-your-memory-from-claude)
- Anthropic tested memory for reinforcing harmful patterns, over-accommodation and safeguard bypass on wellbeing topics before expanding it — [Claude blog: memory](https://claude.com/blog/memory)
- Prompt injection can write malicious content into read-write memory, which later sessions trust — [Docs: Managed Agents memory](https://platform.claude.com/docs/en/managed-agents/memory)
- Incremental writes accumulate "duplicates, contradictions, and stale entries" (Anthropic's reason for dreams) — [Docs: dreams](https://platform.claude.com/docs/en/managed-agents/dreams)
- Claude Code adds `modified` timestamps so staleness is visible, and pushes Claude to "merge or drop stale entries" when the index nears its limit — [Claude Code docs: memory](https://code.claude.com/docs/en/memory)
- Third-party commentary (low-quality sources, anecdotal): stale or speculative statements stored as fact propagate forward (e.g. an old employer after a job change); there is no one-click memory export — [Calmara blog (search snippet)](https://calmara.app/blog/how-to-audit-claude-memory). Treat as commentary.

### Inferences
- For a therapist persona, the highest risks are: (1) stale or wrong memories framed as facts about the client (show provenance and date, let the client correct them); (2) sensitive health data stored without explicit, informed consent (copy the opt-in plus per-save notice); (3) the model over-anchoring on past framings or being too agreeable (Anthropic's own test focus); (4) deletion semantics: decide explicitly whether deleting a session deletes the memories derived from it (Anthropic: no), and offer a hard reset; (5) memory writes from untrusted content (web or tool results) should be blocked or limited to user turns.

### Gaps
- No credible independent study of Claude memory accuracy or privacy was found; criticism is mostly blog-level or anecdotal. No regulatory actions specific to Claude memory were found.
