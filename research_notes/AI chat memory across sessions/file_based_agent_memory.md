# File-based memory in open-source and CLI agents (OpenClaw first), as of 2026-11-01

Research date: 2026-11-01. Most OpenClaw facts come from the current docs at docs.openclaw.ai (which track `main`) and the v2026.8.1 "Memory" release page. Where a value comes only from secondary sources (blogs, docs mirrors), it is flagged as such.

## 1. OpenClaw: name, files, writers, tools, search backend, memory flush, loading, privacy, known problems

### Takeaway
"The model just writes to a memory file" was roughly true of early Clawdbot. It is no longer an accurate description of OpenClaw in late 2026. Plain Markdown files in a workspace are still the source of truth: `MEMORY.md`, `USER.md`, daily `memory/YYYY-MM-DD.md` logs, plus identity files such as `SOUL.md`, `AGENTS.md` and `IDENTITY.md`. Around them, OpenClaw has built a full memory subsystem:
- injection budgets per file
- a hybrid vector and keyword index in SQLite, with optional Postgres, Honcho or LanceDB engines
- `memory_search` and `memory_get` tools
- a silent "memory flush" turn before compaction
- a nightly "dreaming" job that promotes daily notes into `MEMORY.md`
- provenance and trust tagging, plus a `forget` command

These were added after bloat, silent truncation and memory-poisoning attacks became visible problems.

### Cited Findings

**Name and history**
- The project started as Clawdbot in late 2025. After an Anthropic trademark notice (the name was close to "Claude") it became Moltbot on 2026-01-27, and three days later OpenClaw. — [Wikipedia mirror (CNBC-sourced)](https://wiki.krisyotam.com/content/wikipedia_en_all_nopic_2026-03/OpenClaw); [nanoglobals](https://nanoglobals.com/glossary/openclaw/); [AlternativeTo news, Jan 2026](https://alternativeto.net/news/2026/1/the-viral-ai-agent-clawdbot-rebrands-a-third-time-and-now-has-a-social-network-for-bots)
- Creator: Peter Steinberger, an Austrian developer and PSPDFKit founder. He joined OpenAI in February 2026, and OpenClaw reportedly stayed open source under an independent foundation. One source stresses that this was a hire, not an acquisition. — [Android Authority](https://www.androidauthority.com/openclaw-peter-steinberger-openai-3641150); [Fortune, 2026-02-15](https://www.fortune.com/2026/02/15/openai-openclaw-ai-agent-developer-peter-steinberg-moltbot-clawdbot-moltbook); [Verdent](https://www.verdent.ai/guides/openclaw/founder)
- Versions use calendar numbering (`2026.M.x`). Docs exist for v2026.8.1 (a dedicated "Memory" release) and v2026.9.6, and GitHub has a v2026.10.3 tag. A third-party tracker lists 2026.10.10-beta.3 (October 2026) as the latest, with memory fixes such as "memory files keep indexing after plugin reloads". I did not verify that against the primary changelog. — [v2026.8.1 Memory](https://docs.openclaw.ai/releases/2026.8.1/memory); [v2026.9.6](https://docs.openclaw.ai/releases/2026.9.6); [GitHub v2026.10.3](https://github.com/openclaw/openclaw/releases/tag/v2026.10.3); [Releasebot (secondary)](https://releasebot.io/updates/openclaw)

**Workspace files (memory and identity)**
- The workspace is plain Markdown in `~/.openclaw/workspace` by default. "The model only knows what is saved to disk." — [docs: concepts/memory](https://docs.openclaw.ai/concepts/memory); [GitHub docs/concepts/memory.md](https://github.com/openclaw/openclaw/blob/main/docs/concepts/memory.md)
- Workspace file map, from the official docs:

  | File | Purpose | When loaded |
  |---|---|---|
  | `AGENTS.md` | Operating instructions, including how to use memory | Every session |
  | `SOUL.md` | Persona, tone, boundaries | Every session |
  | `USER.md` (optional) | Stable preferences and communication style, written as dated active/superseded directives | Every session, under its own 4,000-character cap |
  | `IDENTITY.md` | Name, vibe, emoji | Bootstrap file |
  | `BOOT.md` (optional) | Startup checklist | Only on Gateway startup, only with the `boot-md` hook enabled |
  | `BOOTSTRAP.md` | One-time first-run ritual | Created only for a brand-new workspace, deleted after the ritual |
  | `memory/YYYY-MM-DD.md` | Daily log | — |
  | `MEMORY.md` (optional) | Curated long-term facts, decisions, short summaries | Only in the main private session |
  | `skills/` | Workspace skills | — |

  `TOOLS.md` and `HEARTBEAT.md` do not appear in the current workspace file map. Tool conventions sit in a `## Tools` section of `AGENTS.md`, and heartbeat has its own docs page. — [docs: agent-workspace](https://docs.openclaw.ai/concepts/agent-workspace)
- Memory files listed on the memory concept page:
  - `MEMORY.md`: "durable non-profile facts and decisions", loaded at session start.
  - `USER.md`: preferences and profile facts, with a small separate budget.
  - `memory/YYYY-MM-DD.md` or `memory/YYYY-MM-DD-<slug>.md`: daily notes. Today's and yesterday's notes load automatically on a bare `/new` or `/reset`. They are indexed for search but "not injected every turn".
  - `DREAMS.md`: Dream Diary for human review.
  - `memory/imports/{codex,claude-code,hermes}/`: imported memory from other agents, indexed but not merged into `MEMORY.md`.

  — [docs: concepts/memory](https://docs.openclaw.ai/concepts/memory)
- Lowercase `memory.md` used to be accepted as a fallback. A third-party blog says that was dropped around 2026.4.10; I have not verified this. — [Petronella blog (secondary)](https://petronellatech.com/blog/openclaw-ai-agent-guide-2026/)

**Who writes the files and when**
- The agent itself writes with ordinary file tools: when asked ("remember that…") or as it works, following the instructions in `AGENTS.md`.
- The pre-compaction flush appends to the daily note.
- "Dreaming" promotes qualified items from daily notes into `MEMORY.md`. Only the "deep" phase writes `MEMORY.md`.
- Import Memory copies memory from Codex, Claude Code or Hermes.

  — [docs: concepts/memory](https://docs.openclaw.ai/concepts/memory)
- Instructions in the default `AGENTS.md` template:
  - Daily notes are "raw logs". `MEMORY.md` is "curated, durable facts and decisions, not raw logs".
  - `USER.md` holds directives tagged with observed date and status. A changed preference is marked superseded, so no two contradictory directives are active.
  - Read memory files before writing to them. "Mental notes don't survive a restart." Lessons go into `AGENTS.md` or skills.
  - A scheduled maintenance automation reviews daily notes, folds stable directives into `USER.md`, moves durable facts into `MEMORY.md` (main sessions only) and prunes outdated entries.

  — [GitHub docs/reference/templates/AGENTS.md](https://github.com/openclaw/openclaw/blob/main/docs/reference/templates/AGENTS.md)
- Dreaming:
  - On by default (`plugins.entries.memory-core.config.dreaming.enabled`, default `true`).
  - Runs as a cron job, `dreaming.frequency` default `"0 3 * * *"`.
  - Promotion is gated by score, recall frequency and query diversity.
  - `phases.deep.maxPromotedSnippetTokens` default 160; `phases.deep.maxPriorEntryLossFraction` default 0.25.
  - "Untrusted and system-derived candidates are excluded from consolidation and promotion."
  - Dream journals from before July 2026 are no longer imported.

  — [docs: reference/memory-config](https://docs.openclaw.ai/reference/memory-config); [docs: concepts/memory](https://docs.openclaw.ai/concepts/memory)
- Guidance for "action-sensitive memories": record approval requirements, expiry and source authority. "Memory preserves this context but does not enforce policy"; hard controls belong in approvals and sandboxing. — [GitHub docs/concepts/memory.md](https://github.com/openclaw/openclaw/blob/main/docs/concepts/memory.md)

**Tools**
- `memory_search`: hybrid semantic plus keyword search. It can also return session-transcript hits.
- `memory_get`: reads a memory file or a line range. It cannot read transcript hits; those go through `sessions_search` and then `sessions_history`.
- `intent`: event-conditioned standing intents.

  — [docs: concepts/memory](https://docs.openclaw.ai/concepts/memory)
- CLI: `openclaw memory status | search "q" | index --force | reset`. `reset` clears derived data and needs a re-index. — [docs: concepts/memory](https://docs.openclaw.ai/concepts/memory)

**Search backend**
- Default engine is the built-in SQLite `memory-core` (keyword, vector, hybrid). Alternatives: Honcho ("cross-session user modeling") and LanceDB. An optional `memory-wiki` plugin adds a provenance-tracked knowledge vault. — [GitHub docs/concepts/memory.md](https://github.com/openclaw/openclaw/blob/main/docs/concepts/memory.md)
- Embeddings default to OpenAI. Other providers: Gemini, Voyage, Mistral, Bedrock, DeepInfra, local GGUF, Ollama, LM Studio, GitHub Copilot, generic OpenAI-compatible. `memory.search.provider: "none"` gives keyword-only search. — [docs: concepts/memory](https://docs.openclaw.ai/concepts/memory)
- PostgreSQL backend:
  - Uses `ts_rank`, calibrated as `r / (r + 0.0027)`. The docs say this is not BM25, since there is no corpus-wide IDF.
  - Needs the `unaccent` extension, `pg_trgm` for the trigram tokenizer and `vector` (pgvector) for semantic search.

  — [docs: concepts/memory](https://docs.openclaw.ai/concepts/memory)
- Official config defaults:

  | Key | Default |
  |---|---|
  | `memory.search.provider` | `"openai"` |
  | `memory.search.query.maxResults` | 6 |
  | `memory.search.query.minScore` | 0.35 (applied before recency decay and importance weighting) |
  | `memory.search.cache.enabled` | `true` (chunk embeddings cached in SQLite) |
  | `memory.search.store.vector.enabled` | `true` (sqlite-vec) |
  | `memory.search.store.fts.tokenizer` | `"unicode61"` (alternative `trigram`) |
  | `memory.search.sources` | `["memory"]` (add `"sessions"` for transcripts; also needs `experimental.sessionMemory`) |
  | `memory.search.rememberAcrossConversations` | on for personal installs, off with DM isolation |
  | `memory.search.extraPaths` | — |
  | `memory.citations` | `"auto"` |

  Not configurable: MMR diversity uses a fixed lambda of 0.7, and dated daily notes decay with a fixed 30-day half-life. `MEMORY.md`, `USER.md` and other "evergreen" files do not decay. There is no supported `memory.search.sync.watch` setting. — [docs: reference/memory-config](https://docs.openclaw.ai/reference/memory-config)
- From secondary sources only:
  - Chunks of about 400 tokens with 80-token overlap.
  - Hybrid weights `vectorWeight` 0.7 / `textWeight` 0.3, normalized to 1.0, fused as a union so a chunk with zero keyword score can still rank.
  - Fallback to pure vector search if FTS5 cannot be created.
  - Sources disagree on the config key names (`memorySearch.chunking.*` vs `agents.defaults.memory.chunkSize`).

  — [docs.openclaw.ai zh-CN mirror](https://docs.openclaw.ai/zh-CN/concepts/memory); [lin-guanguo research notes](https://lin-guanguo.github.io/llm-memory-research/openclaw-memory.research/); [wujiaming88 report, 2026-03-10](https://wujiaming88.github.io/2026/03/10/openclaw-memory-system-architecture.html)
- QMD was an earlier alternative backend. It was retired in v2026.8.1: `openclaw doctor --fix` migrates its settings and rebuilds the index from the Markdown files. QMD-only reranking, query expansion and cross-agent transcript search are gone. — [v2026.8.1 Memory](https://docs.openclaw.ai/releases/2026.8.1/memory)

**Pre-compaction memory flush**
- How it works:
  - Before compaction, a silent turn runs on a private copy of the conversation and asks the agent to save durable context.
  - The `write` tool appends only new text to the daily note (`memory/YYYY-MM-DD.md`), and replayed notes are rejected.
  - Success means a persistence tool completed, or the agent replied `NO_REPLY`.
  - It uses the session model and its fallback chain.
  - It is skipped when the workspace is read-only or unavailable, and a skipped flush does not block compaction.

  — [docs: concepts/memory](https://docs.openclaw.ai/concepts/memory); [docs: compaction](https://docs.openclaw.ai/concepts/compaction)
- Config under `agents.defaults.compaction.memoryFlush`:
  - `enabled` (default `true`)
  - `softThresholdTokens` (default 4000), the "gap below the compaction threshold that triggers a flush"
  - `forceFlushTranscriptBytes` (default `"2mb"`), which forces a flush even when token counters are stale

  The flush runs once per compaction cycle ("tracked in the session row"), only for embedded sessions; CLI backends and heartbeat turns skip it. Example from the docs: in a 32,768-token window the reserve is 8,192 (the 20,000 default is capped at a quarter of the window), so flushing starts at 20,576 tokens and blocking compaction at 24,576. — [docs: housekeeping](https://docs.openclaw.ai/reference/session-management-compaction/housekeeping)
- During flush turns, provider server-side compaction (Anthropic's threshold compaction, OpenAI inline) is disabled, so extraction sees the unsummarized history. — [docs: compaction](https://docs.openclaw.ai/concepts/compaction)
- Compaction itself:
  - Triggers at the smaller of 75% of the window and the window minus the reserve (20,000).
  - `keepRecentTokens` default 20,000.
  - The summarizer input is capped at 160,000 characters: the newest messages get half the budget verbatim, older user messages are trimmed to 2,000 characters each, and tool results are projected to 2,000 characters.
  - The full history stays on disk.

  — [docs: compaction](https://docs.openclaw.ai/concepts/compaction)

**Loading into sessions and budgets**
- Per-file injection limit `agents.defaults.bootstrapMaxChars` = 20000 characters; total `agents.defaults.bootstrapTotalMaxChars` = 60000; separate `USER.md` cap of 4,000. Over-budget files are truncated in the prompt but kept intact on disk. The editor accepts files up to 2 MiB, a separate limit. — [docs: agent-workspace](https://docs.openclaw.ai/concepts/agent-workspace)
- If `MEMORY.md` exceeds the bootstrap budget, "the injected copy is truncated". Diagnose with `/context list`, `/context detail` or `openclaw doctor`. — [GitHub docs/concepts/memory.md](https://github.com/openclaw/openclaw/blob/main/docs/concepts/memory.md)

**Privacy rules**
- `MEMORY.md`: "Load only in the main session (direct chats with your human)". It is never loaded in shared contexts such as Discord, group chats or sessions with other people. — [AGENTS.md template](https://github.com/openclaw/openclaw/blob/main/docs/reference/templates/AGENTS.md); [docs: agent-workspace](https://docs.openclaw.ai/concepts/agent-workspace)
- The memory concept page itself "does not distinguish private from group sessions"; the rule lives in the template and the workspace doc. Cross-conversation recall (`rememberAcrossConversations`) is off when DM isolation is on. — [docs: concepts/memory](https://docs.openclaw.ai/concepts/memory); [docs: reference/memory-config](https://docs.openclaw.ai/reference/memory-config)
- Other hygiene advice:
  - Generated memory files default to mode `0600`.
  - Keep the workspace in a private git repository.
  - Do not store secrets or raw chat dumps in it.
  - The workspace "is the default cwd, not a hard sandbox".

  — [docs: agent-workspace](https://docs.openclaw.ai/concepts/agent-workspace)
- v2026.8.1 provenance and trust model:
  - Automatic memory is "bounded and provenance-gated".
  - Content from network or restricted sessions "keeps an untrusted origin and stays out of automatic context even though an explicit search can still surface it".
  - Fixes: "Quarantine memory writes from network-tainted agent turns" (#115818); "Mark post-network provider memory writes as untrusted" (#118760).
  - New `openclaw memory forget` previews and purges derived memory by session, hook source or participant, and keeps that session from returning through backfill, indexing or dreaming. It does not erase original transcripts, older notes without lineage, or backups.

  — [v2026.8.1 Memory](https://docs.openclaw.ai/releases/2026.8.1/memory)

**Known problems: bloat and silent truncation (community reports)**
- `MEMORY.md` grows until it passes `bootstrapMaxChars`, then gets cut silently, with "no error, no warning". The agent loses whatever sat at the bottom, sometimes keeping stale rules and dropping newer ones.
- Advice varies: keep it under about 100 lines / 2,000 words, or trim it once it passes about 200 lines.
- Other causes of "forgetting": preferences said in chat but never written down, and stale entries that never expire.

  — [clawmage blog](https://clawmage-website.pages.dev/blog/openclaw-memory-not-working); [Remote OpenClaw](https://remoteopenclaw.com/blog/openclaw-memory-not-working-fix); [gu-log: 5 days debugging OpenClaw memory, 2026-02-22](https://gu-log.vercel.app/en/posts/en-sp-82-20260222-coderams-openclaw-memory-debugging)
- Vendor criticism, so expect bias: Supermemory says "everyone is complaining about OpenClaw's memory". — [Supermemory blog (vendor)](https://blog.supermemory.ai/why-everyone-is-complaining-about-openclaws-memory-it-sucks-and-why-supermemory-fixes-it)
- v2026.8.1 fixed bugs in OpenClaw's own MEMORY.md rewriting: "Preserve user-authored headings during MEMORY.md compaction" (#116057), user notes lost during budget compaction (#116180), "restoring MEMORY.md after a failed in-place write" (#126486), and quadratic migrations (#109355). — [v2026.8.1 Memory](https://docs.openclaw.ai/releases/2026.8.1/memory)

**Known problems: security incidents and memory poisoning**
- CSA research note dated 2026-06-13 describes the attack chain:
  1. Injected instructions arrive in a document, email or web page the agent reads.
  2. The agent appends rules to `SOUL.md` or `AGENTS.md`, or writes into `MEMORY.md`.
  3. The poisoned file loads as system context in every later session.
- Zenity Labs demonstrated a full chain from a shared Google Workspace document to remote code execution and a C2 implant.
- "Behavioral residue": restoring `SOUL.md` does not fully remediate, because the vector index still holds the poisoned period, so the store must be purged as well.
- The note also flags a `soul-evil` hook that can silently swap `SOUL.md`.
- Recommended mitigations: file-integrity monitoring and making identity files immutable to the agent.

  — [CSA Labs research note](https://labs.cloudsecurityalliance.org/research/csa-research-note-openclaw-indirect-prompt-injection-2026061/)
- Zenity's proof of concept had the agent create a scheduled task that re-injects attacker logic into `SOUL.md`, which survives restarts. — [eSecurity Planet](https://www.esecurityplanet.com/threats/openclaw-or-open-door-prompt-injection-creates-ai-backdoors/)
- Lasso reported that indirect injection made NVIDIA's sandboxed "NemoClaw" rewrite `SOUL.md` and then its memory file. — [BD TechTalks](https://bdtechtalks.substack.com/p/how-prompt-injection-broke-nvidias)
- Akamai calls `MEMORY.md` and `SOUL.md` "sticky" attack surfaces that can lie dormant for weeks. — [Akamai](https://www.akamai.com/blog/security/clawdbot-openclaw-practical-lessons-building-secure-agents)
- An arXiv taxonomy lists memory poisoning of `SOUL.md` and `MEMORY.md` as one of five prompt-injection subtypes. It is unreviewed. — [arXiv 2608.05201](https://arxiv.org/pdf/2608.05201)
- Ecosystem incidents cited by CSA:
  - more than 21,000 publicly reachable instances (Censys, January 2026)
  - 341 malicious ClawHub skills between 2026-01-27 and 2026-01-29, about 12% of the 2,857 listed
  - CVE-2026-25253 and CVE-2026-25157 (skill delivery and injection chains), fixed in 2026.1.29

  — [CSA Labs](https://labs.cloudsecurityalliance.org/research/csa-research-note-openclaw-indirect-prompt-injection-2026061/)
- CVE-2026-100539: memory tool access was not revoked when memory was hot-disabled; fixed in 2026.8.1. I only saw this in a search summary. — [OSV](https://osv.dev/vulnerability/CVE-2026-100539)
- A community guide says OpenClaw's SECURITY.md treats prompt injection, and reports that need write access to workspace files, as out of scope. I have not checked this against the repo. — [centminmod/explain-openclaw](https://github.com/centminmod/explain-openclaw/blob/master/05-worst-case-security/prompt-injection-attacks.md)

### Inferences
- Read literally, "just a memory file the model writes to" describes the storage format and the write path (the model writes with normal file tools). It does not describe the system that makes the memory work. OpenClaw needed several extra pieces:
  1. hard injection budgets
  2. a separate always-loaded profile file (`USER.md`) from curated facts (`MEMORY.md`) and from raw daily logs, with only the first two injected
  3. on-demand hybrid search over everything else
  4. a forced save step before context is lost (the flush)
  5. a scheduled consolidation job (dreaming)
  6. trust and provenance tagging so injected text cannot reach automatic context
- The private-session rule for `MEMORY.md` exists because one workspace can serve one human and also group chats. In a multi-user web app the same concern becomes strict per-user (and possibly per-persona) scoping, enforced by the backend rather than by a prompt instruction.
- Advanced LLM Chat already summarizes at 80% of the context window. That is the natural hook for an OpenClaw-style "flush": one extraction call before summarizing that writes durable items to memory. OpenClaw's rules carry over directly: run once per summary cycle, append only new text, accept "nothing to save" (`NO_REPLY`), and never block the summary if extraction fails.

### Gaps
- I did not read the `memory-core` TypeScript source. The chunk size/overlap and hybrid weights (400/80 and 0.7/0.3) are confirmed only by a Chinese docs mirror and blogs; the current English config reference omits them.
- I did not find the default flush prompt text. The docs only say it includes a `NO_REPLY` hint and point to the plugin SDK docs.
- Release dates of v2026.8.1 and later versions were not stated on the pages read.
- I did not find a GitHub issue thread quantifying memory bloat; the evidence is community blogs.

## 2. Other agents with file memory (Codex CLI, Gemini CLI, Cursor, Windsurf, Hermes Agent, Cline, Aider, Anthropic memory tool)

### Takeaway
There are three families:
1. **Static instruction files that humans write**, which the agent loads every session: AGENTS.md, GEMINI.md, CONVENTIONS.md, Cursor/Windsurf rules.
2. **Agent-written memory files under hard size caps**, injected as a frozen snapshot: Hermes `MEMORY.md`/`USER.md`, OpenClaw.
3. **Background-generated memories** extracted from past sessions by a separate pipeline: Codex memories, Gemini "Auto Memory", formerly Cursor Memories.

Two products have stepped back from automatic memories. Cursor removed its Memories feature in favor of rules. Codex tells users that anything that must always apply belongs in AGENTS.md, not in memories.

### Cited Findings

**Nous Research Hermes Agent**
- Two files in `~/.hermes/memories/` (per profile `~/.hermes/profiles/<name>/memories/`):
  - `MEMORY.md`: agent notes, environment facts, lessons; capped at 2,200 characters (about 800 tokens).
  - `USER.md`: user profile; capped at 1,375 characters (about 500 tokens).
  - A write that would exceed the cap returns an error, and the agent must consolidate or remove entries itself; there is no auto-compaction.

  — [Hermes docs: memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)
- Both files are injected at session start as a block with a capacity header and `§`-separated entries, as a "frozen snapshot" to keep the LLM prefix cache valid. Writes during a session go to disk immediately but appear in the prompt only next session. — [Hermes docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)
- The tool has actions `add`, `patch`, `remove` (no read action) and a required `target` of `memory` or `user`. `patch` and `remove` match a unique substring (`old_text`) and reject ambiguous matches. — [Hermes docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)
- What to save, per the guidance:
  - Save: preferences, environment facts, corrections, conventions, completed work, explicit requests.
  - Skip: trivia, facts that are easy to search again, raw dumps, session ephemera.
  - A background "self-improvement review" after turns can save memories (`auxiliary.background_review.enabled`).

  — [Hermes docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)
- Session search: all sessions are stored in SQLite (`~/.hermes/state.db`) with FTS5 full-text search, returning raw messages without summarization. Memory files hold always-available facts; session search covers on-demand recall. — [Hermes docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)
- Memory entries are scanned before acceptance for prompt injection, credential exfiltration and SSH-backdoor patterns, and invisible Unicode is blocked. External providers can run alongside built-in memory: RetainDB and ByteRover are bundled; Honcho, Hindsight, Supermemory, Mem0, OpenViking and Holographic install as plugins. — [Hermes docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)

**OpenAI Codex (CLI, app, IDE)**
- `AGENTS.md` is the human-written instruction file. Separately, "Local Codex memories are off by default". They are enabled in Settings > Personalization or with `memories = true` under `[features]` in `config.toml`. — [OpenAI Codex docs: memories](https://learn.chatgpt.com/docs/customization/memories?surface=app)
- Config keys:
  - `memories.generate_memories` and `memories.use_memories` (write and read switches)
  - `memories.disable_on_external_context`: excludes chats that used MCP tools, web search or tool search; the alias `no_memories_if_mcp_or_web_search` is still accepted
  - `memories.min_rate_limit_remaining_percent`
  - `memories.extract_model` and `memories.consolidation_model`

  — [Codex docs: memories](https://learn.chatgpt.com/docs/customization/memories?surface=app)
- Storage is `~/.codex/memories/` (or `$CODEX_HOME/memories/`): summaries, durable entries, recent inputs and evidence. Generation runs in the background, skips active or short sessions, and waits until a chat has been idle. Secrets are redacted. Memory files are "generated state", and hand-editing is not the main way to control them. "Required team guidance belongs in AGENTS.md… Memories are a recall aid." `/memories` per chat can opt that chat out of using or contributing. — [Codex docs: memories](https://learn.chatgpt.com/docs/customization/memories?surface=app)
- Unverified third-party claims: a two-phase pipeline (per-rollout extraction, then global consolidation), a `memory_summary.md` injected into every prompt, and nine tunables such as `max_rollout_age_days`. — [Daniel Vaughan, 2026-04-18 (secondary)](https://codex.danielvaughan.com/2026/04/18/codex-built-in-memory-system-deep-dive/); [Daniel Vaughan, 2026-04-08](https://codex.danielvaughan.com/2026/04/08/codex-cli-memory-internals/); [Mem0 library (vendor)](https://mem0.ai/blog/how-memory-works-in-codex-cli)

**Google Gemini CLI**
- Hierarchical `GEMINI.md`:
  - global `~/.gemini/GEMINI.md`
  - workspace directories and their parents
  - just-in-time scanning of the directories tools touch, up to a trusted root

  All found files are concatenated and sent with every prompt. `context.fileName` can be set to e.g. `["AGENTS.md","CONTEXT.md","GEMINI.md"]`. `@path/to/file.md` imports other files. Commands: `/memory show`, `/memory reload`. — [Gemini CLI docs: gemini-md.md](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/gemini-md.md)
- The current memory tool doc no longer describes a dedicated `save_memory` tool. "Memory is handled by editing Markdown files directly" with `write_file` or `replace`. Routing: shared project instructions go to repository `GEMINI.md`, private project notes to a per-project private memory folder, cross-project preferences to `~/.gemini/GEMINI.md`. — [Gemini CLI docs: tools/memory.md](https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/memory.md)
- An experimental "Auto Memory" feature "extracts memory updates and reusable skills from past sessions automatically". — [Gemini CLI tutorial: memory-management](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/tutorials/memory-management.md)

**Cursor**
- Cursor removed its "Memories" feature in 2.1.x (staff cite 2.1.17) and folded it into Rules. Users are told to "Export memories" to an `.mdc` rules file.
- Before removal, "Generate Memories" let the model add memories without being asked "when it thinks information is important".
- Leftover memories could stay active with no UI to clear them.
- One earlier staff reply said only the UI had been removed, which conflicts with the later statements.

  — [Cursor forum: Are my memories gone?](https://forum.cursor.com/t/are-my-memories-gone/144057); [Cursor forum: Memories not showing](https://forum.cursor.com/t/memories-not-showing/143820); [Cursor forum: Can't clear memories](https://forum.cursor.com/t/cant-clear-memories/148254)

**Windsurf (now Devin Desktop under Cognition)**
- The Windsurf memories docs URL redirects to docs.devin.ai. That page covers only rules:
  - files: `AGENTS.md`, `AGENTS.local.md`, `.devin/rules/*.md`, `~/.devin/global_rules.md`; legacy `.windsurf/rules` and `.windsurfrules` are imported
  - activation triggers: `always_on`, `glob`, `model_decision`, `manual`
  - advice to keep rules short, since they cost tokens on every message

  It does not describe auto-generated Cascade memories. — [Devin Desktop docs: Cascade memories](https://docs.devin.ai/desktop/cascade/memories)

**Cline Memory Bank**
- A methodology, not a built-in feature: custom instructions in `.clinerules/memory-bank.md` tell Cline to keep six Markdown files in `memory-bank/`:
  - `projectbrief.md`, `productContext.md`
  - `activeContext.md` (updated most often)
  - `systemPatterns.md`, `techContext.md`, `progress.md`

  The rule reads: "I MUST read ALL memory bank files at the start of EVERY task." Updates happen on "update memory bank", after significant changes, or when new patterns are found. — [Cline docs: Memory Bank](https://docs.cline.bot/prompting/cline-memory-bank)

**Aider**
- Conventions are a static `CONVENTIONS.md` the user writes, loaded with `/read`, `--read` or `read:` in `.aider.conf.yml`. It is read-only and "cached if prompt caching is enabled". There is no automatic memory the model writes to. — [Aider docs: conventions](https://aider.chat/docs/usage/conventions.html)

**Anthropic memory tool (API, client-side; relevant because the app serves Anthropic models)**
- Tool entry: `{"type": "memory_20250818", "name": "memory"}`.
- Commands: `view` (directory listing two levels deep, or file with line numbers and optional `view_range`), `create`, `str_replace`, `insert`, `delete`, `rename`. All paths are under `/memories`.
- The tool is client-side: "The `/memories` path is a prefix that your handler maps onto real storage, such as a per-user directory or keys in a database."
- Available on all Claude 4 and later models.

  — [Claude docs: memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- The API auto-injects this system prompt text: "IMPORTANT: ALWAYS VIEW YOUR MEMORY DIRECTORY BEFORE DOING ANYTHING ELSE. MEMORY PROTOCOL: 1. Use the `view` command … ASSUME INTERRUPTION: Your context window might be reset at any moment…" `view` truncates text over 16,000 characters. — [Claude docs: memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- Security guidance from the docs:
  - Strip sensitive data before writing; "Claude usually refuses to write sensitive information".
  - Cap file sizes and the size of `view` output.
  - Expire files not accessed in a long time.
  - Strictly validate paths against traversal (`../`, URL-encoded `%2e%2e%2f`, `pathlib.Path.resolve()`/`relative_to()`).
  - Pair with compaction: "memory preserves the information that must survive summarization."
  - SDK helpers: `BetaAbstractMemoryTool` (Python/C#), `betaMemoryTool` (TS), `BetaLocalFilesystemMemoryTool`.

  — [Claude docs: memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)

### Inferences
- How the agents decide what to save, from most to least explicit:
  1. Only on request: Aider, Cline (on "update memory bank"), Gemini's direct edits.
  2. Model judgment guided by prompt rules: Hermes save/skip lists, OpenClaw `AGENTS.md`, Anthropic's memory protocol.
  3. Forced by lifecycle events: OpenClaw's flush before compaction, Hermes background review.
  4. Offline extraction and consolidation by a separate model: Codex, Gemini Auto Memory, OpenClaw dreaming.

  Mature systems combine 2, 3 and 4.
- Hermes's tiny caps (about 1,300 tokens in total), frozen snapshots and substring-based `patch` are the simplest pattern that holds up. They avoid bloat by design and keep prompt caching intact. That makes them a strong reference for a chat app, where caching matters for cost on both Anthropic and OpenAI-compatible endpoints.
- The Anthropic memory tool is a ready-made file-style interface that can be backed by PostgreSQL rows (path → content). For OpenAI-compatible models (Kimi, DeepSeek, GLM, Gemma), the same six commands can be exposed as an ordinary function tool, so all providers share one store.
- Codex's `disable_on_external_context` and OpenClaw's network-taint quarantine converge on the same defense: never let a turn that read untrusted external content (web search, fetched pages, MCP) write automatic memory. That applies directly to Advanced LLM Chat's web-search tool.

### Gaps
- I did not verify when or whether Gemini CLI's older `save_memory` tool was removed or renamed. The current docs describe direct Markdown edits, and the historical behavior (appending to `~/.gemini/GEMINI.md`) was not re-checked in this session.
- I found no current official documentation for Windsurf/Devin auto-generated memories (storage location, scoping).
- Codex internals (file names, phases, default models) are documented only by third parties.
- Claude Code's own memory (CLAUDE.md hierarchy, auto memory) was not researched in this pass.

## 3. File memory vs database-backed memory: where it works, where it breaks, community view

### Takeaway
File memory works well for a single user, a single agent and a small curated profile. Humans can read and edit it, diff it, back it up with git, and the model already knows how to edit text files. It breaks down in five places:
- **Scale and retrieval:** silent truncation, and the need to add an index.
- **Consistency:** stale or contradictory facts, and in-place rewrite bugs.
- **Multi-user privacy:** `MEMORY.md` leaking into group chats.
- **Concurrency.**
- **Security:** every file the agent can write becomes a prompt-injection persistence point.

In practice every serious file-memory system has rebuilt a database layer underneath: SQLite FTS5 and sqlite-vec, Postgres with pgvector, LanceDB, Honcho. The files remain the human-facing source of truth.

### Cited Findings
- OpenClaw keeps Markdown as the source of truth but derives a SQLite index (FTS plus sqlite-vec, embedding cache) and supports Postgres with pgvector and pg_trgm. `openclaw memory reset` drops derived data, which can be rebuilt from the files. — [docs: concepts/memory](https://docs.openclaw.ai/concepts/memory); [docs: reference/memory-config](https://docs.openclaw.ai/reference/memory-config)
- OpenClaw also ships alternative engines: Honcho for "cross-session user modeling", and LanceDB. — [GitHub docs/concepts/memory.md](https://github.com/openclaw/openclaw/blob/main/docs/concepts/memory.md)
- Scale failure: files over 20,000 characters are truncated at injection without a warning to the agent, so behavior varies between sessions. Community advice is manual curation. — [clawmage blog](https://clawmage-website.pages.dev/blog/openclaw-memory-not-working); [docs: agent-workspace](https://docs.openclaw.ai/concepts/agent-workspace)
- Consistency failures fixed in v2026.8.1:
  - lost user headings and notes during MEMORY.md compaction
  - MEMORY.md restore after a failed in-place write
  - forgotten content returning through consolidation or retries (#130451, #131179, #131248)

  — [v2026.8.1 Memory](https://docs.openclaw.ai/releases/2026.8.1/memory)
- To prevent contradictions, OpenClaw's `USER.md` directives carry an observed date and an active/superseded status. — [AGENTS.md template](https://github.com/openclaw/openclaw/blob/main/docs/reference/templates/AGENTS.md)
- Multi-user: `MEMORY.md` is loaded only in the private main session, because one workspace serves both private and group chats. Sharing a workspace between OS users requires widening the file mode, with a warning that memory "may contain sensitive information". — [docs: agent-workspace](https://docs.openclaw.ai/concepts/agent-workspace)
- Portability: Codex memories are local and per-user, so "a second laptop, or a server, or a fresh container has no memory". — [Daniel Vaughan (secondary)](https://codex.danielvaughan.com/2026/05/01/codex-cli-memories-persistent-context-session-memory-ecosystem/)
- Security: poisoned memory files persist across sessions, and vector indexes keep "behavioral residue" after the file is restored. — [CSA Labs](https://labs.cloudsecurityalliance.org/research/csa-research-note-openclaw-indirect-prompt-injection-2026061/)
- Hermes scans each memory write for injection and exfiltration patterns before accepting it. — [Hermes docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)
- Codex positions memories as "a recall aid, not the only source for rules that must always apply". — [Codex docs](https://learn.chatgpt.com/docs/customization/memories?surface=app)
- Cursor removed automatic Memories and moved users to explicit rules files. — [Cursor forum](https://forum.cursor.com/t/are-my-memories-gone/144057)
- The Anthropic memory tool does not prescribe files or a database. `/memories` is a prefix "your handler maps onto real storage, such as a per-user directory or keys in a database". — [Claude docs: memory tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool)
- Community and vendor opinion:
  - Letta (a memory-framework vendor) argues the retrieval mechanism matters less than the agent's ability to use its tools: "memory is more about how agents manage context than the exact retrieval mechanism used". — [Letta blog](https://www.letta.com/blog/benchmarking-ai-agent-memory)
  - Supermemory (a vendor selling an OpenClaw plugin) argues OpenClaw's built-in memory is inadequate. — [Supermemory blog](https://blog.supermemory.ai/why-everyone-is-complaining-about-openclaws-memory-it-sucks-and-why-supermemory-fixes-it)

### Inferences
- "A markdown file plus search" is good enough for the profile layer: who the user is, standing preferences, a few durable facts. It is not enough on its own for long, multi-session histories. A therapy persona needs the episodic layer (what was discussed in session 7) to be searchable and dated, with recency decay. OpenClaw's design addresses exactly this: daily logs that decay, evergreen files that don't, and searched rather than injected.
- For a multi-user server app with PostgreSQL, real files on disk add little except familiarity for the model. The parts worth copying are:
  - the file-like interface (view/create/str_replace, or Hermes's add/patch/remove), which the model handles reliably
  - the structure (profile vs curated facts vs dated episodic notes)
  - the budgets

  Store them as rows keyed by user and persona, with `created_at`, `source_conversation_id`, `source_message_id` and a trust flag. That gives backend-enforced per-user privacy, transactional updates (avoiding OpenClaw's failed in-place writes), provenance for a "forget" feature, and FTS through Postgres `tsvector` plus optional pgvector, which OpenClaw itself supports.
- For a therapist persona specifically, the sensitive-data guidance in the Anthropic docs and OpenClaw's `0600`/no-raw-dumps advice point to a few requirements: a user-visible, editable memory view, an explicit "forget" path, and possibly encryption at rest. These are design inferences, not sourced recommendations.

### Gaps
- I found no systematic study of concurrency failures in file memory, such as two sessions writing `MEMORY.md` at once. The OpenClaw fix list hints at write-safety problems but does not quantify them.
- I found no non-vendor survey of community sentiment on whether file memory is "good enough"; the available opinions are mostly from vendors or individual blogs.

## 4. Evaluations and benchmarks of file-based memory vs dedicated memory systems

### Takeaway
The main data point remains Letta's August 2025 experiment. A GPT-4o-mini agent with only file tools (`grep`, `search_files`, `open`, `close`) over the raw LoCoMo conversation history scored 74.0%, against 68.5% reported for Mem0's best graph variant. Letta concluded that agent tool-use skill matters more than the retrieval backend, and that current memory benchmarks "may not be very meaningful". I found no OpenClaw-specific benchmark.

### Cited Findings
- Letta "Benchmarking AI Agent Memory" (2025-08-12):
  - Setup: the LoCoMo history was placed in one file, attached to a Letta agent and embedded for semantic search. The model was GPT-4o mini. Tool rules required starting with `search_files` and continuing until `answer_question`.
  - Result: 74.0% on LoCoMo, vs 68.5% for Mem0's top graph variant. Letta calls Mem0's numbers "controversial" and says Mem0 did not respond to requests for clarification.
  - No LangMem or Zep numbers are given.
  - Conclusion: "it's much more important to consider whether an agent will be able to effectively use a retrieval tool"; "memory is more about how agents manage context than the exact retrieval mechanism used".

  — [Letta blog](https://www.letta.com/blog/benchmarking-ai-agent-memory)
- Letta points to its own Letta Memory Benchmark and to Terminal-Bench as better tests, and notes its open-source terminal agent ranked #4 overall and #1 among open-source agents on Terminal-Bench. This is self-reported. — [Letta blog](https://www.letta.com/blog/benchmarking-ai-agent-memory)

### Inferences
- The Letta result supports "files plus search tools" for retrieval-style recall ("what did the user say about X"). The test was single-user and read-only: it measured nothing about how the agent writes or curates memory over time, and nothing about poisoning or privacy. Those are where the OpenClaw problems actually showed up.
- The benchmark was run by a memory-framework vendor against a competitor whose numbers it disputes. Treat it as indicative, not conclusive.
- For a therapist persona, the relevant quality is less factual Q&A recall (LoCoMo) and more continuity and correct handling of changing facts: superseded preferences, or a resolved issue no longer treated as current. No benchmark I found measures this for file memory.

### Gaps
- I did not find (in this pass) independent replications of the Letta filesystem result, or LongMemEval or LoCoMo scores for OpenClaw, Hermes or Codex memories.
- I did not retrieve the Mem0 paper's own LoCoMo numbers, or Zep's and LangMem's, for a full comparison table.
- I found no evaluation of the cost of the "memory flush" or "dreaming" approaches, in tokens or latency.
