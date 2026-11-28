# Weekly check-up of the knowledge base

Feature doc, written on 2026-11-27 before building. It is a first draft: the decisions at the end are still open, and "check-up" is a working name. Once a week a model goes over a whole knowledge base (the notes and the memory) and writes what it would change: what to merge, rewrite, shorten, correct or link. Its proposals arrive as a conversation with the agent of that knowledge base. The user answers there ("1 and 3 yes, 2 no, 4 but shorter"), and the agent applies what the user agreed to with the tools it already has. Once built, this doc becomes the reference, like `docs/knowledge_base.md`.

## Why

Three things write to a knowledge base today (`docs/knowledge_base.md`): the agent while it answers, the memory review after a conversation goes quiet, and the nightly consolidation. All three only look at what is new: one conversation, one day. Their rules say "when in doubt, save it", and notes grow by `kb_update` with `append`. The memory is only merged under pressure: from 90 % of its limit every change reminds the model to merge, and a change that would go over is refused. The consolidation's step "Notes" merges and updates only what the period touches.

So nothing ever reads the whole knowledge base, and over the weeks it collects:

- notes on the same topic written in different weeks;
- notes that became logs, one appended section per conversation, with the current state somewhere in the middle;
- lines and notes that were true once (a plan that is past, "currently …");
- notes that contradict each other, or the memory;
- links to notes that don't exist, and notes nothing links to;
- quoted lines and turns of phrase from a single conversation, which the model then copies into its answers. On 2026-11-27 a character agent's replies grew long and odd for this reason, and the remedy was rebuilding its knowledge base by hand;
- patterns the consolidation inferred, which read like facts after a while.

On the owner's instance the notes had about 20 revisions each on average on 2026-11-27.

## What others do (research of 2026-11-27)

- **Anthropic, "The components of agent memory"** (engineering blog, 2026-11-06, [post](https://www.anthropic.com/engineering/components-of-agent-memory)). It names four layers: transcripts, memory notes, representations such as a wiki, and the context injected into every session. "Dreaming" goes over them between sessions: it checks notes against the transcripts and corrects them, writes new notes and wiki pages, merges duplicates, prunes, and moves details down while it promotes short summaries into the injected layer. It names no schedule and no human review. The failures it reports matter here: wrong notes persist into later sessions, memory drifts as things change, one wiki grew to 1.77 times the size of its sources, and strict rules on what to record ("only failures") made it worse.
- **Karpathy's "LLM Wiki"** (2026-04, [gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)): a wiki an LLM keeps from sources, with a periodic **lint**, a health check for contradictions between pages, claims that newer sources superseded, pages without inbound links, concepts mentioned without a page of their own, missing cross-references, and gaps to fill. Community versions split it in two: a script for the mechanical checks (broken links, orphans, format) and a model for the semantic ones (contradictions, expired claims) ([llm-atomic-wiki](https://awesome.ecosyste.ms/projects/github.com%2Fcablate%2Fllm-atomic-wiki)). At least one only reports and changes nothing without approval ([kb-lint](https://tessl.io/registry/skills/github/bibryam/minimal-karpathy-llm-wiki-skill/kb-lint)). An extension of the pattern argues that a model writing to a knowledge base on its own degrades it, puts a human checkpoint before writes, and warns that inferences written back become indistinguishable from sourced facts ([LLM Wiki v2](https://gist.github.com/rohitg00/2067ab416f7bbe447c1977edaaa681e2)).
- **Letta** ([Memory & dreaming](https://docs.letta.com/guides/agents/architectures/sleeptime), [sleep-time compute](https://letta.com/blog/sleep-time-compute)): background subagents review recent conversations after a number of steps or when the context is compacted, and commit to a git-backed memory filesystem directly. An option has a second agent revise the updates first, without asking the user. Reorganising (splitting large files, merging duplicates, restructuring) happens on request, after a backup; `/doctor` audits duplication, placement and size. An unofficial community guide suggests deduplicating on every run, light consolidation at the end of a session and a full reorganisation weekly ([forum](https://forum.letta.com/t/sleeptime-agents-for-memory-consolidation-best-practices-guide/154)).
- **Claude Code's Auto Dream** (reported from 2026-03, sources disagree on whether it is released; [finisky](https://finisky.github.io/en/claude-code-auto-dream), [tessl](https://tessl.io/blog/anthropic-tests-auto-dream-to-clean-up-claudes-memory/)): consolidates the memory files after 24 hours and five sessions, removes outdated entries and merges duplicates; `/dream` runs it by hand.
- **Zep / Graphiti** ([research report](https://lin-guanguo.github.io/llm-memory-research/graphiti.research/)): a new fact that contradicts an old one doesn't delete it. The old one is marked invalid from a date, with the episode that changed it, so history stays and "what was true then" can be answered.
- **A-MEM** (NeurIPS 2025, [arXiv 2502.12110](https://arxiv.org/abs/2502.12110)): notes in the manner of a Zettelkasten, where a new memory can update the context and tags of the older notes it links to.
- **ChatGPT** (2025-10, [TechRadar](https://www.techradar.com/ai-platforms-assistants/chatgpt/chatgpt-is-smarter-now-that-its-learned-to-forget-a-huge-memory-upgrade-is-coming), [Memory FAQ](https://help.openai.com/en/articles/8590148-memory-and-newer-features-)): manages saved memories automatically by recency and frequency and drops the less relevant ones quietly. That ended "memory full", but it is the opposite of asking the user.

Nothing found proposes changes and waits for the user. The ideas worth taking: a mechanical layer before the model, checking a line against the conversation it came from, superseding with a date rather than deleting, and a full pass at a slower pace than the incremental one.

## The proposal

### When, and for which knowledge bases

- **Per knowledge base** (user and vault, as the consolidation), once it changed since its last check-up.
- **Weekly, from the nightly CronJob:** after the consolidation, `memory_dream.py` runs the check-ups that are due (the last one at least `CHECKUP_INTERVAL_DAYS`, 7, ago), so a check-up sees the week's journal complete. A due date rather than a weekday, so a missed night only delays it. A table `memory_checkups` (user, vault, when, the conversation it made, `failed_at`) keeps track, like `memory_dreams`. No new Helm resource.
- **On request:** "Check up now" on the Knowledge base page (`POST /api/kb/checkup`), for testing and for when the user wants one.
- **Agents that don't save on their own** (`personas.auto_memory` off) get it too: it only proposes, and their rule is that they save when the user asks, which a yes is. Their prompt is the measure: for a storyteller, contradictions in its canon matter, and patterns about the user don't.

### Step 1: mechanical checks, without a model

SQL in `backend/services/memory_checkup.py`:

- **Broken links:** `kb_links.target_slug` without an active note in the vault, with the notes that have them. Links to archived notes are listed apart.
- **Orphans:** active notes without a backlink from an active note or the memory. Journal notes are left out: they are found by their tag.
- **Similar notes:** pairs whose titles or descriptions are close (`similarity()` of `pg_trgm`, which past chats installed already).
- **Size and growth:** the largest notes, those over the 15,000 characters at which a note is told to split, and those appended to most often since the last check-up (a revision whose content starts with the previous one). The memory's lines and characters against `MEMORY_MAX_LINES` and `MEMORY_MAX_CHARS`.
- **Quotes:** lines of the memory and the notes with a long quoted passage, as candidates for wording that steers the voice.
- **Where each memory line comes from:** the first revision of the memory that has the line, with its author (`agent`, `review`, `dream`, `user`), date and conversation (`kb_note_revisions.conversation_id`). So the model can read the source of a line before it calls it wrong, and tell an inferred pattern (`dream`) from something the user said.

### Step 2: the model's pass

- **Model:** the user's memory model, else the model of their latest conversation (`resolve_memory_model()`), as for the review and the consolidation.
- **Tools, read-only:** `kb_search`, `kb_list`, `kb_read`, and `chat_search`, `chat_list`, `chat_read` over the chats of that memory (also when the agent didn't pick past chats: the check-up reads, the agent doesn't). No write tools: it proposes.
- **Input** (the user message): an inventory of the notes (slug, title, description, tags, size, last change, revisions by author since the last check-up, links in and out), the findings of step 1, the memory with the source of each line, the changes since the last check-up (`changes_since()`), and the last check-up's conversation: its proposals and what the user answered. For an agent's own knowledge base the agent's prompt as context, for the shared one the names of the agents that use it (as the consolidation). The notes themselves are read on demand, so the input stays small whatever the knowledge base's size; a budget of about 60 model calls.
- **What it looks for** (`CHECKUP_PROMPT`):
  1. Contradictions between notes, or between the memory and a note: it names both and asks which holds.
  2. What is outdated: a plan that is past, a state a later conversation changed. It proposes the dated fact ("until October 2026: …") rather than deleting it, so the history stays.
  3. Duplicates: notes on the same topic (which one survives, which one is archived), lines that say the same thing.
  4. Notes that became logs: rewritten as the current state. The revisions keep every earlier version.
  5. The memory: details that belong in a note, a note that deserves a pointer line, a memory near its limit.
  6. Quotes and turns of phrase from one conversation: shortened to the fact they carry.
  7. Inferences stated as facts: a pattern the journal doesn't support any more.
  8. Structure: broken links, orphans, a topic spread over several notes without one of its own, missing links.
- **Rules:** check a line against its source before calling it wrong; every proposal says what, why and from where (note, line, conversation and date); don't propose again what the user declined last time, unless something changed since; at most `CHECKUP_MAX_PROPOSALS` (15), the most valuable first, so a check-up takes a few minutes to answer; nothing to propose is a fine outcome, and then no conversation is made.

### Step 3: the conversation

- **Made by the check-up:** a conversation of the user's, titled "Check-up, 2026-W48" (or "Check-up of <agent>'s memory, 2026-W48"), with the agent of the knowledge base: for an agent's own one that agent, for the shared one the user's default agent if it uses the shared memory, else the agent of their latest conversation with it.
- **Its messages:** a system message for the agent (`CHECKUP_CHAT_INSTRUCTIONS`: this conversation is the weekly check-up; apply what the user agrees to, as they word it, with your tools; ask when a proposal or the answer is unclear; say what you changed; nothing else), then the proposals as the agent's message, a numbered Markdown list with `[[links]]` to the notes. Its `lastMessageAt` puts it at the top of the sidebar; there is no notification.
- **A history that begins with the agent's message:** the Anthropic adapter puts `HISTORY_START_PLACEHOLDER` ("Earlier messages of this conversation are not included") in front of it, which is wrong here and needs a text of its own.
- **Marked as a check-up** (`conversations.checkup`): the memory review and the consolidation leave it out, since what the user said there is applied in it already, and a review would save lines like "the user agreed to merge X". Its messages still belong to the memory, so past chats can find why something was merged.
- **Applied changes** are the agent's revisions with this conversation's id, so a note's history on the Knowledge base page leads back to the proposal and the yes, and an earlier version is restored there as now.
- **No answer by the next check-up:** that one carries the open proposals over (they count towards its limit); the old conversation stays until the user deletes it.
- **Hidden content** stays hidden as in the consolidation (`HIDE_RULE`): the conversation is hidden when its agent is, or when a proposal names a hidden note or line.

### Settings

- A user setting **Weekly check-up** in the settings, next to the memory model, and a server setting to turn it off for everybody (`MEMORY_CHECKUP_ENABLED`; the chart passes it).

## Cost

A check-up reads the inventory and the notes it opens, plus the sources of the lines it checks: for a knowledge base of about 40 notes, in the order of 50,000 to 150,000 input tokens a week. That is less than one long conversation, and the owner decided that token cost is no argument for the memory (2026-11-04).

## Testing (planned)

- `knowledge_base_test.py` or a test script of its own, against a real Postgres and the fake model server: the mechanical checks on seeded notes (a broken link, an orphan, two similar notes, a note appended to as a log, a quoted line, the source of each memory line); the due date and the run from the nightly job; the conversation with its system message and the proposals; the review and the consolidation leaving it out; proposals carried over; the agent applying an agreed proposal with its tools in that conversation; nothing written by the check-up itself.
- Live: on a local copy of the owner's database (from a backup) with a real model, judging the proposals with the owner before it runs on the instance.

## Open decisions

1. **Proposals only, or some changes alone?** Recommended: proposals only at first. The consolidation already merges without asking every night, and the mechanical fixes that are certain are few (the memory tools already refuse an exact duplicate line). After a few weeks, kinds the user always accepts could be applied alone and only reported.
2. **Which knowledge bases:** every one that changed, with the user setting (recommended), or a switch per agent like **Saves on its own**.
3. **When:** due after 7 days, run with the nightly job (recommended), or a fixed weekday; and maybe earlier when the memory passes 90 % of its limit.
4. **How the user answers:** in words in the conversation (recommended, no new UI), or with a button per proposal, which needs proposals stored as data and a component in the chat. Words come first, buttons can follow.
5. **On or off by default** for new users. Recommended: on, since an empty check-up makes no conversation.
6. **The name:** "check-up", "weekly review" (close to the memory review), "housekeeping", or another.

## Later

- **Counting reads** of notes (`kb_read`, search hits), so the check-up sees which notes are never looked up.
- **A month's summary of the journal**, so older weeks can be read in one note.
- **`[[links]]` in chat answers as links** (`docs/knowledge_base.md`, "Not built yet"): the proposals name many notes.
