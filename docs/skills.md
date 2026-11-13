# Skills

A skill is a text that tells an agent how to do one kind of work well: writing a character, writing a prompt for an image model, giving feedback on a story. Admins write skills on the Agents page and attach them to agents. The agent sees what each skill is for and loads the whole text when a request needs it. Planned on 2026-11-13; the decisions are the owner's.

## Why

An agent's system prompt already says who it is and how it answers. Skills are for know-how that doesn't belong there:

- **Several agents use it.** A roleplay agent, a writing coach and a general assistant may all need to know how to build a character. Today each would need the same text in its prompt, and every change would have to be made three times.
- **Most answers don't need it.** A guide to image prompts helps only when the user wants an image. Kept in the prompt, it would cost tokens in every answer and draw the model's attention away from the rest. As a skill it costs one line until it's used.

What others do:

- **Anthropic's Agent Skills** (October 2025), since December 2025 the open `SKILL.md` standard ([agentskills.io](https://agentskills.io/specification)), used by Claude Code, Codex and VS Code. A skill is a folder with a `SKILL.md`: YAML frontmatter with `name` and `description`, then the Markdown instructions. The model always sees only the names and descriptions. It loads a skill's text when a task matches, and other files of the skill only when that text points to them ("progressive disclosure").
- **Superhuman-Remote-Worker** adopted the standard (`knowledge-base/knowledge/features/agent_skills.md`, the tool `use_skill` in `src/agent/tools/workspace/skills.py`). What it found applies here too:
  - **Models don't always load a skill when they should.** How often they do depends on how the description is worded. Guidance that must always apply belongs in the agent's prompt, not in a skill.
  - **The list of skills costs tokens in every answer.** An agent should get the skills it needs, not every skill there is.

## Decisions (2026-11-13)

- **The `SKILL.md` format.** A skill has a `name` (lowercase letters, digits and hyphens, at most 64 characters, as the standard requires), a `description` (what it does and when to use it, at most 1,024 characters) and its text (Markdown). Skills can be imported from and exported to `SKILL.md` files, so skills from Claude Code, Anthropic's [skills repository](https://github.com/anthropics/skills) or SRW can be brought in, as far as they are text.
- **Text only.** No scripts, no extra files. A skill that needs other files or runs a script can't be imported as it is; only its `SKILL.md` text can.
- **Loaded on demand.** The system prompt lists the agent's skills by name and description. The tool `use_skill(name)` gives the agent the skill's text, as a tool result the chat shows as a step. Two consequences:
  - The system prompt stays the same from answer to answer, so the providers' prompt caches keep working.
  - The text stays in the conversation, through the answer's tool record (`backend/llm/tool_record.py`). Later answers have it without loading it again.
- **Only admins write skills and attach them to agents,** on the Agents page (`/agents`), like the admins' MCP servers. The tab **Skills** lists, writes, imports and exports them. The agent dialog gets a **Skills** section with a checkbox per skill. Users' own skills come later, once users can make their own agents.
- **Not a tool group.** `use_skill` comes with the skills. An agent with skills gets the tool even with no other tools, and an agent without skills never sees it.
- **Only on demand, only an agent's own skills.** An agent loads a skill when it needs it, and only the skills an admin attached to it. There is no "always in the prompt" mode: guidance that must always apply goes into the agent's own prompt. An agent on a model without tools has no skills, as it has no other tools. The agent dialog says so.
- **Two starter skills ship with the app,** in the repository's catalog file, so every installation gets them on its next start, as it gets the example agents Pirate and Translator (see [Catalog file](#catalog-file)):
  - **`image-generation`:** generating images with open-weight diffusion models, as on Civitai. There a sloppy prompt doesn't give a beautiful image, as it does with Midjourney (which has no API). The agent picks the base model and LoRAs, sets sampler, steps, guidance, size and seed, and writes the prompt and the negative prompt, all in the style of the model family. The skill carries the best practices for that.
  - **`character-writing`:** building characters for stories and roleplay.
  
  Other useful skills come later (see [Later](#later)).

## What a skill is

```markdown
---
name: image-generation
description: Generates images with open-weight diffusion models (SDXL, Pony, Illustrious, Flux, ...), e.g. on Civitai: picks the base model and LoRAs, the settings and size, and writes the prompt and negative prompt. Use when the user wants an image or asks for help with an image prompt.
---

# Image generation

How to pick a model and write a prompt...
```

- **`name`:** the skill's identifier, unique, `^[a-z0-9]+(-[a-z0-9]+)*$`, at most 64 characters. The agent passes it to `use_skill`, and agents store the names of their skills. Renaming a skill updates the agents that have it.
- **`description`:** written for the model: what the skill does and when to use it. It is the only thing the model reads when it decides whether to load the skill, so it says when the skill applies ("Use when the user ..."). 1 to 1,024 characters.
- **The text:** Markdown, at most 20,000 characters, about the 5,000 tokens the standard recommends. A longer skill should be split into two.
- **`enabled`:** a disabled skill is left out of every agent's list and can't be loaded, but stays attached to its agents.
- **Imported `SKILL.md` files:** the frontmatter's other keys (`license`, `metadata`, `allowed-tools`, Claude Code's extensions) are ignored, and the import says which ones were dropped. An export writes `name` and `description` and the text.

## Storage

- **Table `skills`:** `id`, `name` (unique), `description`, `content`, `enabled`, `created_at`, `updated_at`, with a trigger for `updated_at` like the other tables. Added to `schema.sql` and `tables.py`.
- **`personas.skills JSONB`:** the names of the agent's skills in the order the admin picked them. NULL means none. `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for existing databases, like `mcp_servers`.
- **Deleting a skill** removes its name from every agent that has it, in the same transaction, so no agent refers to a skill that's gone.
- **Renaming a skill** replaces the old name in the agents' lists, in the same transaction.

## In the answer

- **Prompt:** a section after the tool sections and before the MCP servers (`with_skills()` in `backend/llm/prompts.py`), only for an agent with enabled skills:
  ```
  ## Skills:
  You have skills: instructions for particular kinds of work. When a request matches a skill's description, load it with use_skill before you start, and follow it. A loaded skill stays in this conversation; load it again when its text is no longer there.
  - character-writing: Builds characters for stories and roleplay...
  - image-generation: Generates images with open-weight diffusion models...
  ```
  The descriptions aren't marked as untrusted, as SRW does, since only admins write them.
- **Tool:** `use_skill(name)` (`backend/services/tools/skill_tools.py`), bound to the agent's skills with `functools.partial` like the other tools, so the agent can only load its own skills. It returns the skill's text with its name as a heading. An unknown name raises `ToolInputError` with the names the agent has. The step title is "Using Skill" (`TOOL_TITLES`).
- **History:** results of `use_skill` are not cut at `HISTORY_TOOL_RESULT_CHARS` (`replayed_record()` in `backend/services/conversation_history.py`). Otherwise later answers would get a cut skill and take it for the whole skill. Once the rolling summary folds that exchange in, the text is gone, and the prompt tells the agent to load it again.
- **Guests** get an agent's skills like everyone else. A skill is only text and costs nothing beyond the tokens of the answer.
- **Not part of** the memory review, the nightly consolidation or the summary. The review and the consolidation get the agent's own prompt as context, but not its skills.
- **The input token indicator** in manual editing (`POST /api/message/context-size`) counts the list of skills, since it builds the same prompt.

## Admin API

All under `/api/admin/skills`, admins only, like the rest of the catalog (`backend/api/catalog.py`, `backend/catalog/service.py`):

| Endpoint | What it does |
|---|---|
| `GET /api/admin/skills` | All skills, with the agents that use each one |
| `POST /api/admin/skills` | Create one (`name`, `description`, `content`, `enabled`) |
| `PATCH /api/admin/skills/{id}` | Change one; a new `name` is also changed in the agents' lists |
| `DELETE /api/admin/skills/{id}` | Delete one, and remove it from the agents |
| `POST /api/admin/skills/import` | One `SKILL.md` as text: creates the skill, or replaces the one of that name with `replace: true`. Returns the skill and the keys it ignored |
| `GET /api/admin/skills/{id}/export` | The skill as a `SKILL.md` file |

Agents get a `skills` field (`PersonaCreate`, `PersonaUpdate`, `PersonaOut`). Unknown names are refused when an agent is saved, as for MCP servers.

## Agents page

- **Skills tab** (`skills-tab.component.ts`), between Agents and MCP servers: each skill with its name, description, whether it's enabled, and the agents that use it. Actions: **New skill**, **Import SKILL.md** (one or more files), and per skill **Edit**, **Export**, **Delete** (the confirmation names the agents that lose it).
- **Skill dialog:** name, description (with a hint that the model decides from it alone), the text in a large monospace field with a character count against the 20,000, enabled.
- **Agent dialog:** a **Skills** section after the MCP servers, with a checkbox and the description per skill. A disabled skill is marked as such. A hint says that skills need a model with tools.
- **Translations** in `en.json` and `de.json`.

## Catalog file

The catalog file (`docs/model_catalog_api.md`) gets a `skills` section, `[{"name", "description", "content", "enabled"}]`, and agents get `skills`:

- **Seeding** (`MODEL_CATALOG_FILE`, every start) creates missing skills and leaves existing ones as they are, like models and agents.
- **Import** in the app creates or updates skills by name.
- **Export** writes all of them.

Skills are imported before agents, so an agent in the same file can refer to them.

## Testing

- **Offline** (`python -m backend.llm.tests.run_all`):
  - the prompt section, and no skills for a model without tools;
  - `use_skill` with a known and an unknown name;
  - the history keeps the whole text of `use_skill` results.
- **Against Postgres** (`backend/services/tests/skills_test.py`, own `<POSTGRES_DB>_skills_test` database):
  - creating, validating, renaming and deleting skills, with the agents' lists following;
  - reading and writing `SKILL.md`, including ignored keys and bad frontmatter;
  - catalog file seeding, import and export;
  - the tool and prompt of an answer;
  - disabled skills.
- **Catalog end to end** (`backend/catalog/tests/catalog_api_test.py`): the endpoints and the agents' `skills` field.
- **Live**, in the browser with the development backend:
  - an agent with both starter skills on DeepSeek and on Gemma 4;
  - does it load `image-generation` when asked for a picture, without being told to?
  - does it leave the skills alone in small talk?
  - does a later answer use the skill without loading it again?

## Later

- **Users' own skills**, once users can have their own agents.
- **An agent that writes skills:** turn what worked in a conversation into a skill, like Anthropic's `skill-creator`.
- **Picking a skill in the chat,** such as `/image-generation` in the composer, for when the model doesn't load it on its own.
- **Files of a skill** (`references/`), read on demand, and importing skill folders as zip files. Scripts stay out: the app has no sandbox to run them in.
