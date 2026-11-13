# Skills

A skill is a text that tells an agent how to do one kind of work well: writing a character, generating an image, giving feedback on a story. Admins write skills on the Agents page and attach them to agents. The agent sees what each skill is for and loads the whole text when a request needs it. Planned and built on 2026-11-13; the decisions are the owner's.

## Why

An agent's system prompt already says who it is and how it answers. Skills are for know-how that doesn't belong there:

- **Several agents use it.** A roleplay agent, a writing coach and a general assistant may all need to know how to build a character. Without skills, each would need the same text in its prompt, and every change would have to be made three times.
- **Most answers don't need it.** A guide to image generation helps only when the user wants an image. Kept in the prompt, it would cost tokens in every answer and draw the model's attention away from the rest. As a skill it costs one line until it's used.

What others do and what is known (research of 2026-11-13):

- **Anthropic's Agent Skills** (October 2025), since December 2025 the open `SKILL.md` standard ([agentskills.io](https://agentskills.io/specification)), used by Claude Code, Codex and VS Code. A skill is a folder with a `SKILL.md`: YAML frontmatter with `name` and `description`, then the Markdown instructions. The model always sees only the names and descriptions. It loads a skill's text when a task matches, and other files of the skill only when that text points to them ("progressive disclosure").
- **Superhuman-Remote-Worker** adopted the standard (`knowledge-base/knowledge/features/agent_skills.md`, the tool `use_skill` in `src/agent/tools/workspace/skills.py`). The tool here is modelled on it.
- **Models often don't load a skill when they should.**
  - In Vercel's tests the skill was never loaded in 56% of cases ([Vercel](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals)).
  - Sonnet 4.5 in Claude Code loaded a matching skill in 50–55% of runs, Haiku 4.5 almost never, unless a hook made the model decide yes or no for each skill first ([Scott Spence](https://scottspence.com/posts/measuring-claude-code-skill-activation-with-sandboxed-evals)).
  - The more skills a model sees, the less often it picks the right one ([arXiv 2610.18522](https://arxiv.org/abs/2610.18522)).
  - What helps: a description that says when to use the skill with the user's own words, the main use first, and an instruction to check the list before answering. Guidance that must always apply belongs in the agent's prompt, not in a skill.

## Decisions (2026-11-13)

- **The `SKILL.md` format.** A skill has a `name` (lowercase letters, digits and hyphens, at most 64 characters, as the standard requires), a `description` (what it does and when to use it, at most 1,024 characters) and its text (Markdown). Skills are imported from and exported to `SKILL.md` files, so skills from Claude Code, Anthropic's [skills repository](https://github.com/anthropics/skills) or SRW can be brought in, as far as they are text.
- **Text only.** No scripts, no extra files. A skill that needs other files or runs a script can't be imported as it is; only its `SKILL.md` text can.
- **Loaded on demand.** The system prompt lists the agent's skills by name and description. The tool `use_skill(name)` gives the agent the skill's text, as a tool result the chat shows as a step. Two consequences:
  - The system prompt stays the same from answer to answer, so the providers' prompt caches keep working.
  - The text stays in the conversation, through the answer's tool record (`backend/llm/tool_record.py`). Later answers have it without loading it again.
- **Only admins write skills and attach them to agents,** on the Agents page (`/agents`), like the admins' MCP servers. Users' own skills come later, once users can make their own agents.
- **Not a tool group.** `use_skill` comes with the skills. An agent with skills gets the tool even with no other tools, and an agent without skills never sees it.
- **Only on demand, only an agent's own skills.** An agent loads a skill when it needs it, and only the skills an admin attached to it. There is no "always in the prompt" mode: guidance that must always apply goes into the agent's own prompt. An agent on a model without tools has no skills, as it has no other tools. The agent dialog says so.
- **Two starter skills ship with the app** (see [Starter skills](#starter-skills)): `image-generation` and `character-writing`. Other useful skills come later (see [Later](#later)).

## What a skill is

```markdown
---
name: image-generation
description: Writes prompts for image models and generates images with open-weight diffusion models (...). Use whenever the user wants an image, ...
---

# Image generation with open-weight models

Open-weight diffusion models are not Midjourney: ...
```

- **`name`:** the skill's identifier, unique, `^[a-z0-9]+(-[a-z0-9]+)*$`, at most 64 characters. The agent passes it to `use_skill`, and agents store the names of their skills. Renaming a skill renames it in the agents that have it.
- **`description`:** written for the model: what the skill does and when to use it. It is the only thing the model reads when it decides whether to load the skill, so it starts with the main use and says when the skill applies ("Use whenever the user ..."), in the words a user would use. 1 to 1,024 characters.
- **The text:** Markdown, at most 20,000 characters, about the 5,000 tokens the standard recommends. A longer skill should be split into two. The limits are in `backend/models/catalog.py` (`SKILL_*`) and `catalog.model.ts`.
- **`enabled`:** a disabled skill is left out of every agent's list and can't be loaded, but stays attached to its agents.
- **`SKILL.md` files** (`backend/services/skills.py`):
  - **Import:** `parse_skill_md()` reads the frontmatter with PyYAML (a byte order mark and Windows line ends are fine). Other frontmatter keys (`license`, `metadata`, `allowed-tools`, Claude Code's extensions) are left out, and the import names them. A name that is taken is refused, unless the import replaces it (`replace`), which changes its description and text and keeps whether it's enabled.
  - **Export:** `format_skill_md()` writes `name`, `description` and the text.

## Storage

- **Table `skills`:** `id`, `name` (unique), `description`, `content`, `enabled`, `created_at`, `updated_at`, with the trigger for `updated_at` like the other tables (`schema.sql`, `tables.py`).
- **`personas.skills JSONB`:** the names of the agent's skills, in the order of the Skills section. NULL means none; an empty list is stored as NULL. Existing databases get the column from `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (`add_skill_columns`).
- **Renaming and deleting a skill** change the agents' lists in the same transaction (`update_skill()`, `delete_skill()`), so no agent refers to a name that's gone. An agent whose only skill is deleted has none (NULL).
- **Saving an agent** with an unknown skill is refused (`check_agent_skills()`, called by `backend/catalog/service.py` like the check of MCP servers); duplicates are dropped.

## In the answer

- **The agent's skills:** `persona_skills()` in `backend/catalog/resolver.py` gives the enabled skills of the conversation's agent, in its order: none without an agent, for an agent the user may not use, or for a model without tools (`_answer_context()` in `backend/api/messages.py`).
- **Prompt:** `with_skills()` in `backend/llm/prompts.py` adds a section after the tool sections and before the MCP servers:
  ```
  ## Skills:
  You have skills: instructions for particular kinds of work, with what you would otherwise miss. Before every answer, go through the list below and decide for each skill whether the request falls under its description. If one does, your first action is to call use_skill with its name, before you write anything, even if you think you know how; then follow it. Skip this only for a skill whose text is already in this conversation.
  - image-generation: Writes prompts for image models and generates images ...
  - character-writing: Builds characters for stories, roleplay and worldbuilding ...
  ```
  The first wording ("When a request matches a skill's description, load it") got no load from Gemma 4 for an image request. The stricter one makes the model check every skill first, as Spence's hook does. The descriptions aren't marked as untrusted, as SRW does, since only admins write them.
- **Tool:** `skill_tools()` in `backend/llm/tools.py` gives `use_skill(name)` (`backend/services/tools/skill_tools.py`). It is bound to the agent's skills with `functools.partial`, so the agent can only load its own, and the schema lists their names as an `enum`. It returns "The skill <name>. Follow these instructions for this task:" and the text. An unknown name raises `ToolInputError` with the names the agent has. The step title is "Using Skill" (`TOOL_TITLES`).
- **History:** results of `use_skill` are never cut at `HISTORY_TOOL_RESULT_CHARS` (`UNCUT_TOOLS` in `backend/services/conversation_history.py`), as later answers would take a cut skill for the whole skill. Once the rolling summary folds that exchange in, the text is gone, and the agent loads it again.
- **Guests** get an agent's skills like everyone else. A skill is only text and costs nothing beyond the tokens of the answer.
- **Not part of** the memory review, the nightly consolidation or the summary. The review and the consolidation get the agent's own prompt as context, but not its skills.
- **The input token indicator** in manual editing (`POST /api/message/context-size`) counts the list of skills, since it builds the same prompt.

## Admin API

All under `/api/admin/skills`, admins only, like the rest of the catalog (`backend/api/catalog.py`):

| Endpoint | What it does |
|---|---|
| `GET /api/admin/skills` | All skills, disabled ones too, by name, each with the agents that have it (`agents: [{id, name}]`) |
| `POST /api/admin/skills` | Create one (`name`, `description`, `content`, `enabled`); 409 for a taken name, 422 for a bad name or a field over its limit |
| `PUT /api/admin/skills/{id}` | Change the fields sent; a new `name` is also changed in the agents' lists |
| `DELETE /api/admin/skills/{id}` | Delete one, and take it off the agents |
| `POST /api/admin/skills/import` | `{text, replace}`: one `SKILL.md`. Creates the skill, or with `replace` changes the one of that name. Returns `{skill, created, ignored}`; 400 for a malformed file, 409 for a taken name without `replace` |
| `GET /api/admin/skills/{id}/export` | The skill as a `SKILL.md` file (`text/markdown`, a download named `<name>.md`) |

Agents have a `skills` field (`PersonaCreate`, `PersonaUpdate`, `PersonaOut`; null or [] for none).

## Agents page

- **Skills section** (`skills-tab.component.ts`), after the models and before the MCP servers: each skill with its name, length, description, whether it's enabled (a switch), and the agents that have it. Actions: **New skill**, **Import SKILL.md** (one or more files; a taken name is replaced only after a confirmation; what each file did is listed, with the keys it left out), and per skill **Download SKILL.md**, **Edit** and **Delete** (the confirmation names the agents that lose it).
- **Skill dialog** (`skill-dialog.component.ts`): name (checked against the pattern), description (the hint says the agent decides from it alone), the text in a large monospace field, both with a character count against their limits, and enabled.
- **Agent dialog:** a **Skills** section after the MCP servers, with a checkbox and the description (two lines) per skill. A disabled or deleted skill is marked as such. The hint says skills need a model that supports tools, and that a few fitting skills work better than many.
- **Translations** in `en.json` and `de.json` (`catalog.admin.skills.*`, `catalog.admin.personas.skill*`).

## Catalog file

The catalog file (`docs/model_catalog_api.md`) has a `skills` section, `[{"name", "description", "content", "enabled"}]`, and agents have `skills`:

- **Seeding** (`MODEL_CATALOG_FILE`, every start) creates missing skills and leaves existing ones as they are, like models and agents. A skill deleted in the app comes back on the next start: disable it instead.
- **Skill files:** an entry of the seed file can name a `SKILL.md` instead, `{"file": "skills/image-generation/SKILL.md"}`, relative to the catalog file and inside its folder. Its other keys (such as `enabled`) apply on top (`_read_skill_files()` in `backend/catalog/catalog_file.py`). That keeps the skills that ship with the app as Markdown that can be read and reviewed in the repository. Only seeding reads such files, never an import in the app, so an upload can't read files of the server.
- **Import** in the app creates or updates skills by name; **export** writes all of them, with their text.
- Skills are imported before agents, so an agent in the same file can name them.

## Starter skills

They live in `catalog/skills/<name>/SKILL.md`, and `catalog/models.json` names them. An admin can change them in the app; the repository's version only matters for new installations. When a skill in the repository changes, an installation that already has it gets the new version by importing the file with replace (Import SKILL.md on the Agents page).

- **`image-generation`** (17,000 characters):
  - **What it does:** the agent picks the model family for the request (a table: anime, photo, text in the image, complex scenes, drafts), then the checkpoint and the LoRAs. It takes the AIR, the trigger words and the recommended strength from the model version. It writes the prompt in the family's language: tags with each family's own quality tags, or prose. It writes a short negative prompt only for families that use one. Then it sets sampler, steps, CFG, clip skip and a native size from a table per family.
  - **With Civitai's generation tools:** `get_input_schema` with the AIRs gives the exact input fields, `run_step` with `whatif` the price in Buzz, then `run_step`; a `blocked` input is never retried. Afterwards the agent opens every image with `read_file` before it shows or describes one (a vision model sees the image, any other model gets a description and can ask the vision model what to check). It checks the image against the request, fixes a clear miss with one more run (a table of symptoms and fixes), shows only the images that pass, and asks before more runs. It describes only what it saw. It also keeps a character consistent across images. An agent with this skill needs the file tools for that.
  - **Sources:** Civitai's developer docs (the orchestration recipes, the OpenAPI spec of `v2/consumer`, the MCP tools page), the generator's open-source code (`generation.constants.ts`, the form graphs, `basemodel.constants.ts`), Civitai's prompt guides, and the model cards on Hugging Face (Pony V6 and V7, Illustrious, NoobAI, Anima, Flux.1 and Flux.2, Qwen-Image, Z-Image, Chroma, HiDream, SDXL).
  - **Looking at the result** was first only "when you can", after the step that showed the images; on the owner's question (2026-11-13) it became a required step before anything is shown, since in this app every model can look at the images.
  - **Gaps:** some details are unverified and left out or hedged: clip skip for Illustrious, weights on Flux's T5, how seeds count up in a batch.
  - **Keeping it current:** new model families appear every few months, so the family table and the settings table need updating now and then.
- **`character-writing`** (9,500 characters):
  - **What it does:** a few questions first. Then the core: want, need, the lie and the wound, a contradiction, flaws that cost something, and Sanderson's three scales. Then voice with sample lines, relationships and arc. It avoids the models' default names and traits.
  - **Writing it up:** as a profile, or as a character card in the V2/V3 format. The card rules: prose instead of W++, 400 to 1,000 permanent tokens, behaviour instead of labels, never mention what you don't want, a first message that never acts for the user. Or as an agent of this app.
  - **Playing it:** the agent plays from the character's want and fear, against the measured drift towards niceness ([arXiv 2511.04962](https://arxiv.org/abs/2511.04962)), and saves the character as a note when it has the knowledge base.
  - **Sources:** the craft sources (Weiland, McKee, Forster, Sanderson's lectures) and the roleplay community's guides (SillyTavern's docs, the Character Card V2/V3 specs, the Rentry guides of Sukino, pixi, kingbri and Ali:Chat).

## Testing

- **Offline** (`python -m backend.llm.tests.run_all`): `test_loaded_skills_are_never_cut` in `test_history.py` (a `use_skill` result goes back whole, another result of the same answer is cut). All suites pass (2026-11-13).
- **Against Postgres** (`python backend/services/tests/skills_test.py`, own `<POSTGRES_DB>_skills_test` database), 5/5:
  - creating and checking skills: names, limits, empty fields, taken names;
  - the agents' lists: unknown names, duplicates, order, renaming and deleting a skill, a rename rolled back on a conflict;
  - `SKILL.md`: ignored keys, CRLF and a byte order mark, no frontmatter, bad YAML, a round trip with colons, quotes and umlauts, import with and without replace;
  - the catalog file: export, import, seeding that keeps edits, skill files next to the seed file (and none outside its folder), and that the shipped skills are valid;
  - the answer: enabled skills in the agent's order, none for a disabled agent, the prompt section, `use_skill` through the tool registry, and `_answer_context()` with and without tool support and for an agent without tool groups.
- **Catalog end to end** (`backend/catalog/tests/catalog_api_test.py`, section "Skills"): the endpoints, the admin rule, an agent's skills, rename and delete following in the agents, export and import of `SKILL.md`, the catalog export. On 2026-11-13: 198 passed. 4 failed, none about skills: three expect six tool groups and no `hide_chat` (from before family mode), and one is the cached input price another session was still adding.
- **Live** (2026-11-13, development backend, both starter skills attached to the test agent "Skills (Test)"):

  | Model | Request | Result |
  |---|---|---|
  | DeepSeek V4.1 Flash | "An elf hanging lanterns in an autumn forest, anime style, put model, LoRAs, settings, prompt and negative prompt together for Civitai" | Loaded `image-generation` as its first step and followed it: Illustrious checkpoint, LoRAs for that family, tags in the family's order with `BREAK`, 832×1216, a short negative prompt, the price |
  | DeepSeek V4.1 Flash | Same chat: "Make her a roleplay character, with a card and a first message" | Loaded `character-writing`, without loading `image-generation` again: chosen name with alternatives, a want and a lie, flaws that cost her, a first message that doesn't act for the user |
  | DeepSeek V4.1 Flash | A prompt for an oil painting of a lighthouse | Loaded `image-generation` |
  | DeepSeek V4.1 Flash | "How are you today?" | Loaded nothing |
  | Gemma 4 | A character for a fantasy roleplay | Loaded `character-writing` |
  | Gemma 4 | The lighthouse prompt | 0 of 2 with the first wording; 1 of 2 after the stricter prompt and a description that starts with "Writes prompts for image models" |

  So smaller models load skills about half the time, as the published tests found. Gemma's answers also show its reasoning, a known problem with its tool answers.

## Later

- **Picking a skill in the chat,** such as `/image-generation` in the composer, which loads it for the next answer. The fix for models that don't load skills on their own.
- **More skills.** The research of 2026-11-13 ranked these text-only skills for this app's use (conversation, roleplay, philosophy, creative writing, worldbuilding):
  1. **roleplay-craft:** playing a role over a long chat: voice, never writing the user's actions, moving the plot, letting flaws land.
  2. **story-cowriting:** questions, structure, then scene by scene with a fixed point of view and tense.
  3. **worldbuilding:** how a world's rules play out (cultures, economies, magic or technology), with the canon kept as notes in the knowledge base.
  4. **game-master:** text adventures with the state in notes, fair outcomes, and options instead of decisions for the player.
  5. **prose-editing:** removing the tells and clichés of model-written text.
  6. **philosophical-dialogue:** Socratic questions, the strongest version of the other side, keeping track of positions.
  7. **brainstorming and naming:** many distinct options, away from the obvious and the models' default names.
  8. **continuity-keeper:** a story bible in the knowledge base, checked against new text.

  Text that could be imported or adapted: [blader/humanizer](https://github.com/blader/humanizer) (MIT) and the standalone skills of [haowjy/creative-writing-skills](https://github.com/haowjy/creative-writing-skills) (Apache-2.0, keep the license text). [jwynia/agent-skills](https://github.com/jwynia/agent-skills) has good fiction skills but no license, so not without permission.
- **Testing whether skills get loaded:** about 20 requests per skill (half that should load it, half near misses), each run a few times, for every model in use, as Anthropic's skill-creator does.
- **Users' own skills,** once users can have their own agents.
- **An agent that writes skills:** turn what worked in a conversation into a skill, like Anthropic's `skill-creator`.
- **Files of a skill** (`references/`), read on demand, and importing skill folders as zip files. Scripts stay out: the app has no sandbox to run them in.
