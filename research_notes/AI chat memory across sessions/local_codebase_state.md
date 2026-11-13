# Local codebase state for a cross-session memory feature (Advanced LLM Chat and Superhuman-Remote-Worker)

Scope: what Advanced LLM Chat (ALC, `/home/ghost/Repositories/Advanced-LLM-Chat`, branch `develop` at `4e4cf70`, 2026-11-01) has today that a memory feature would build on or touch, and how Superhuman-Remote-Worker (SRW, `/home/ghost/Repositories/Superhuman-Remote-Worker`) implements its knowledge base / memory and what was learned there. Sources are local files; links are absolute file paths. Paths below are relative to the repository root unless absolute. No secrets, private hosts or downstream-client details are recorded.

## ALC: how personas are defined, stored and selected, and whether memories could hang off a persona id

### Takeaway
A persona ("agent" in the UI) is a row in the `personas` table with an integer `id` and a unique `name`. It is chosen per conversation (`conversations.persona_id`) and can be switched at any time from the composer. There is no per-user default persona and no FK from conversations to personas. Admins create and edit personas, and every permitted user shares them. So per-user memory would have to be keyed on `(user_id, persona)`. The persona `id` exists but is not portable between databases; the `name` is the natural key.

### Cited Findings
- `personas` table columns: `id` (serial PK), `name` (unique, not null), `description`, `system_prompt` (may contain `{{variable}}` placeholders), `variables` JSONB (`[{"name","label","default"}]`), `tools` JSONB (tool groups, NULL = every enabled tool), `available_to_guests`, `enabled`, `sort_order`, `created_at`, `updated_at` — [backend/database/tables.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/database/tables.py)
- Conversations store the selection: `model_id`, `persona_id` (comment "personas.id", no ForeignKey), `persona_values` JSONB; "NULL = the user's default model, no persona" — [backend/database/tables.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/database/tables.py)
- `Database.delete_persona()` docstring: "Delete a persona. Conversations keep the ID; the persona prompt is then skipped." — [backend/database/db.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/database/db.py)
- `user_settings` has `default_model_id` but no default persona column — [backend/database/tables.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/database/tables.py)
- Frontend: the model and persona dropdowns sit in the chat composer (`ModelPickerComponent`, "Model and persona dropdowns for the active conversation"). `ChatStateService.selectPersona(persona, values)` writes `personaId`/`personaValues` to the active conversation through `conversationRepository.updateSelection()`, or to a draft for a new conversation (`EMPTY_DRAFT` = no model, no persona). So the persona can change in the middle of a conversation — [src/app/chat-ui/model-picker/model-picker.component.ts](/home/ghost/Repositories/Advanced-LLM-Chat/src/app/chat-ui/model-picker/model-picker.component.ts), [src/app/services/chat-state.service.ts](/home/ghost/Repositories/Advanced-LLM-Chat/src/app/services/chat-state.service.ts)
- A persona has no model of its own: "the chat's model answers" — [docs/model_catalog_api.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/model_catalog_api.md); [docs/generalization_refactor.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/generalization_refactor.md) ("How the app works now")
- Prompt rendering: `render_prompt()` / `render_persona_prompt()` / `persona_prompt_for_conversation(user, conversation)` fill `{{name}}` placeholders (`PLACEHOLDER_PATTERN`). Values come from the conversation's `persona_values`, then the variable's default, then "". Built-ins are `{{date}}` (`format_date`), `{{user_name}}` (`user_display_name`: name, else the email local part, "Guest" for guests) and `{{language}}` (`user_language`, from `user_settings`). Unknown placeholders are left unchanged — [backend/catalog/resolver.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/catalog/resolver.py); [docs/model_catalog_api.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/model_catalog_api.md)
- `persona_usable(persona, user)`: the persona must be enabled, and guests only get personas with `available_to_guests`. A persona the user may not use is skipped, and the answer falls back to the default identity and all tools (`persona_prompt_for_conversation`, `persona_tool_groups`) — [backend/catalog/resolver.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/catalog/resolver.py)
- Personas are edited by admins only on the Agents page (`/agents`, `POST/PUT/DELETE /api/admin/personas`). Users see `GET /api/personas` (`PublicPersona`: id, name, description, systemPrompt, variables, tools) — [docs/model_catalog_api.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/model_catalog_api.md)
- User decision (2026-10-30): "Single-admin setup: no per-user API keys, billing or private agents" — [docs/generalization_refactor.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/generalization_refactor.md)
- Catalog file: personas use `name` as the natural key. Seeding only creates missing ones and never overwrites. Import upserts by name. "Export writes every column ... without keys and without ids" — [docs/model_catalog_api.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/model_catalog_api.md)
- Starter personas in `catalog/models.json`: "Pirate" (`{{style}}`, `{{date}}`, no `tools` key, so every tool; guests allowed) and "Translator" (`tools: []`; guests allowed) — [catalog/models.json](/home/ghost/Repositories/Advanced-LLM-Chat/catalog/models.json)

### Inferences
- A memory row could reference `personas.id` within one database. The id is not stable across export/import or a reseeded database, so a portable design would key on the persona name, or add a stable persona column such as a `memory_scope`/`memory_key`.
- Personas are shared and not per-user ("no private agents"). A therapist persona's memory therefore has to be scoped at least to `user_id`, probably to `(user_id, persona)`, so one user's notes never reach another user of the same persona.
- The persona can be switched mid-conversation, and a deleted persona leaves `persona_id` dangling. A memory feature has to decide what happens to memories written under persona A when a conversation switches to B, and to memories of a deleted persona.
- The `{{variable}}` mechanism, with resolver-side built-ins like `{{user_name}}`, already offers an injection point, e.g. a hypothetical built-in `{{memory}}` filled at render time.

### Gaps
- I didn't check whether the frontend warns before switching personas in a conversation that already has messages.

## ALC: how the system prompt is built for an answer

### Takeaway
The prompt is assembled per answer in `stream_generate`: the persona prompt (or the default identity), then one section per tool group the model actually gets, then the conversation's system messages. The rolling summary does not go into the system prompt. It is the first user message of the history. The history budget is computed after the system prompt and tools are known, so anything added to the system prompt (e.g. memory) automatically shrinks the history budget.

### Cited Findings
- `build_system_prompt(persona_prompt, tools)`: the identity paragraph (`IDENTITY_PROMPT`), or the persona prompt in its place. Then `TOOLS_PROMPT` (+ `WEB_SEARCH_PROMPT`) if there are any tools, `FILE_ACCESS_PROMPT` if `get_file_content` is present, `GRAPH_PROMPT` if any graph tool is present, joined by blank lines — [backend/llm/prompts.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/llm/prompts.py)
- `with_instructions(system_prompt, instructions)` appends the conversation's system messages under `INSTRUCTIONS_HEADING` ("## Instructions for this conversation:"), oldest first. "They go here rather than in their place in the history: many chat templates of open models accept a system message only at the start." — [backend/llm/prompts.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/llm/prompts.py)
- `ConversationHistoryBuilder.system_instructions(conversation_id, before_message=None)` reads them via `db.get_system_messages()` — [backend/services/conversation_history.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/services/conversation_history.py)
- In `stream_generate` (`POST /api/message/stream-generate`): `tools = _agent_tools(current_user, conversation, config)`; `system_prompt = with_instructions(build_system_prompt(persona_prompt_for_conversation(current_user, conversation), tools), history_builder.system_instructions(conversationId))`; then `token_budget = history_token_budget(config, system_prompt, tools)` — [backend/api/messages.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/api/messages.py)
- The summary goes first in the history as a user message: `summary_message(summary)` wraps it in `SUMMARY_LEAD_IN` ... `SUMMARY_CONTINUE` ("Continue the conversation from there. Do not mention or recap this summary."). `ConversationHistoryBuilder.assemble()` prepends it — [backend/services/conversation_history.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/services/conversation_history.py)
- `history_token_budget()` subtracts room for the answer (`max_output_tokens`, else 32000, at most a quarter of the window), 10% of the window for tool results, and the system prompt and tool definitions. Tokens are estimated at 3 characters each (`CHARS_PER_TOKEN`) — [docs/model_catalog_api.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/model_catalog_api.md); [backend/services/conversation_history.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/services/conversation_history.py)
- Only `stream_generate` calls `with_instructions()`. The legacy non-streaming endpoints (the generate endpoint around line 368, which also accepts a `request_body.systemPrompt` override, and two more around lines 758 and 948) use `_system_prompt(current_user, conversation_id)`, i.e. the persona with no tools and no system-message instructions — [backend/api/messages.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/api/messages.py)

### Inferences
- There are three natural slots for injected memory. (a) A new section in `build_system_prompt()` (like the tool sections), which fits "always-loaded" memory, e.g. a profile or a memory index. (b) A built-in persona placeholder. (c) An extra synthetic user message at the start of the history, as the summary does now. Slot (a) keeps memory out of the summarizer's input. Slot (c) puts it in the history budget, so it can be truncated.
- System-message instructions are "never cut off or summarized". This shows the developer already prefers the system prompt for durable, high-priority context.

### Gaps
- I didn't trace which frontend flows still call the legacy non-streaming endpoints. CLAUDE.md describes `stream-generate` as the agent path, and the guided edit uses `stream-generate`.

## ALC: how users, conversations, messages, summaries and settings are stored, and guest vs logged-in users

### Takeaway
Everything lives in PostgreSQL through SQLAlchemy Core, mirrored in the browser's IndexedDB for offline use. Every table is per user or per conversation, and nothing spans a user's conversations except `user_settings` and `uploaded_files`. Guests are real `users` rows (`is_guest`), deleted hourly together with their data by explicit code. A new memory table would have to be added to that deletion, to the schema files, and to the additive migration lists.

### Cited Findings
- `users`: `id`, `email` (unique), `name`, `is_guest`, `created_at`, `oidc_sub` — [backend/database/tables.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/database/tables.py)
- `conversations`: `id` (UUID text), `userId` FK users, `name`, `participants`, `createdAt`, `updatedAt`, `version`, `lastModified`, `model_id`, `persona_id`, `persona_values` — [backend/database/tables.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/database/tables.py)
- `messages`: `id` BigInteger ("Millisecond timestamp-based ID", from the server clock), `conversationId` FK, `roleName`, `content`, `time`, `type` ('text' | 'voice' | 'agent'), `rating`, `agent_status`, `agent_steps` JSONB, `agent_error`, `model_id`, `model_name`, `usage` JSONB — [backend/database/tables.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/database/tables.py); [CLAUDE.md](/home/ghost/Repositories/Advanced-LLM-Chat/CLAUDE.md)
- `conversation_summaries` (one per conversation): `conversation_id` PK, FK with `ON DELETE CASCADE`, `covers_until`, `message_count`, `content`, `model_name`, `created_at` — [backend/database/tables.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/database/tables.py)
- `user_settings`: `user_id` PK, `theme`, `language`, `default_model_id`, `background`, `background_dim`, `background_blur`, `editing_mode` ('guided' | 'manual') — [backend/database/tables.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/database/tables.py)
- `uploaded_files` (`file_id`, `user_id`): "Only the owner can read it (API and agent tool)" — [backend/database/tables.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/database/tables.py)
- Schema changes touch `backend/database/queries/schema.sql` (e.g. `create_conversation_summaries_table`), `tables.py`, and the `EXPECTED_TABLES` and `drop_order` lists in `db_init.py`. `migrate_schema()` (`--prod`) is "additive only": `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` — [backend/database/db_init.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/database/db_init.py); [backend/database/queries/schema.sql](/home/ghost/Repositories/Advanced-LLM-Chat/backend/database/queries/schema.sql)
- Guests: "each guest login creates its own user (`users.is_guest`), deleted with its conversations and files by the hourly cleanup once its sessions have expired". Guests are rate-limited per IP: 5 answers per 3 hours (`guest_usage`) — [docs/generalization_refactor.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/generalization_refactor.md)
- `cleanup_expired_sessions()` runs hourly and calls `db.delete_expired_sessions()` and `db.delete_stale_guest_users(...)` — [backend/security/auth.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/security/auth.py). `delete_stale_guest_users()` explicitly selects the guest's `uploaded_files` and `conversations` and deletes them, with conversations, settings and files; "Messages go with their conversations (ON DELETE CASCADE)". `delete_user()` only deletes the `users` row — [backend/database/db.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/database/db.py)
- Login modes: `AUTH_MODE` = `oidc` | `mock` (dev only) | `none` (default, guests only). "Guests can always chat." — [CLAUDE.md](/home/ghost/Repositories/Advanced-LLM-Chat/CLAUDE.md)
- The frontend is offline-first: all data is in IndexedDB via `DbService`, synced by `SyncEngineService`. `ApiService` handles communication — [CLAUDE.md](/home/ghost/Repositories/Advanced-LLM-Chat/CLAUDE.md)
- Ownership checks: `verify_conversation_ownership(conversation_id, user_id)` guards every message endpoint — [backend/security/auth.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/security/auth.py); [backend/api/messages.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/api/messages.py)

### Inferences
- A `memories` (or `persona_memories`) table keyed on `user_id` with a `persona_*` column fits the existing pattern (Core table + schema.sql + db_init lists + additive migration). It must be added to `delete_stale_guest_users()`, or given `ON DELETE CASCADE` on `users`. `delete_user()` alone relies on cascades.
- Guest users vanish once their sessions expire. Memory across sessions is therefore only meaningful for logged-in users (`oidc`/`mock`). The therapist persona is probably best not `available_to_guests`, or should get no memory for guests.
- The IndexedDB/sync layer was built for conversations and messages. A server-side-only memory store, shown in a settings page via REST, would avoid extending the sync engine.

### Gaps
- I didn't check whether `user_settings` or conversations are included in the conversation file export/import in a way that would need to carry memory. `docs/conversation_file.md` describes messages, including system messages, and doesn't mention summaries.

## ALC: the tool registry and how a memory tool group would be added and enabled per persona/model

### Takeaway
Tools are async functions with explicit JSON schemas in a `ToolRegistry`, grouped in `TOOL_GROUPS`. A persona selects groups (`personas.tools`), and the registry is built per answer for the current user. The user id is bound server-side with `functools.partial`, so the model can't target another user. Adding a `memory` group touches about 6 places, backend and frontend. Also, `tools: null` means "every enabled tool", so an always-available memory group would silently reach every persona without a selection.

### Cited Findings
- `Tool` dataclass (`name`, `description`, `parameters` JSON schema, `func` async, `title`). `ToolRegistry` with `openai_schemas()`, `anthropic_schemas()`, and `call(name, arguments)`, which validates the top level via `_check_arguments()` and drops unknown keys. `format_tool_output()` JSON-encodes non-strings. `_in_thread()` wraps blocking DB functions — [backend/llm/tools.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/llm/tools.py)
- `TOOL_GROUPS = {"files": ("get_file_content",), "web_search": ("web_search",), "knowledge_graph": ("get_graph_schema", "search_graph", "query_graph")}`. `TOOL_TITLES` holds the English step titles, which the frontend translates by these strings — [backend/llm/tools.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/llm/tools.py)
- User scoping pattern: `file_content_tool(user_id)` uses `func=functools.partial(get_file_content, user_id=user_id)`; "the model can't choose another user (the argument is not in the schema). None reads no file at all." — [backend/llm/tools.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/llm/tools.py)
- `_group_tools(group, user_id)` maps a group to its tool definitions. `tool_group_unavailable_reason(group)` (graph needs `NEO4J_ENABLED`, web search needs `TAVILY_API_KEY`). `tool_group_status()`. `default_tools(user_id)`. `tools_for_groups(groups, user_id)`: `None` = all enabled, `[]` = none, unknown groups ignored with a warning — [backend/llm/tools.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/llm/tools.py)
- `_agent_tools(current_user, conversation, config)` returns None if `not config.supports_tools`, else `tools_for_groups(persona_tool_groups(current_user, conversation), user_id=current_user['user_id'])` (None if empty). Only `user_id` is passed, not the persona or conversation — [backend/api/messages.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/api/messages.py)
- API validation: `ToolGroup = Literal["files", "web_search", "knowledge_graph"]` in `backend/models/catalog.py`; "Unknown groups are a 422" — [backend/models/catalog.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/models/catalog.py); [docs/model_catalog_api.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/model_catalog_api.md)
- Frontend mirrors it: `export type ToolGroup = 'files' | 'web_search' | 'knowledge_graph'` and `TOOL_GROUPS` in `src/app/data/models/catalog.model.ts`; an icon map in `src/app/catalog-admin/catalog-admin.utils.ts` (`knowledge_graph: 'hub'`); labels in `src/assets/i18n/en.json` (and `de.json`) — [src/app/data/models/catalog.model.ts](/home/ghost/Repositories/Advanced-LLM-Chat/src/app/data/models/catalog.model.ts); [src/app/catalog-admin/catalog-admin.utils.ts](/home/ghost/Repositories/Advanced-LLM-Chat/src/app/catalog-admin/catalog-admin.utils.ts)
- Prompt sections are keyed off tool names in `build_system_prompt()` (e.g. `GRAPH_TOOL_NAMES`) — [backend/llm/prompts.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/llm/prompts.py)
- Agent loop limit: `AGENT_MAX_STEPS` (default 10 model calls per answer) — [backend/config.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/config.py)
- Models without `supports_tools` get no tools at all (GPT-6 Astra is marked `supports_tools: false` because Chat Completions rejects tools together with `reasoning_effort`) — [docs/generalization_refactor.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/generalization_refactor.md)

### Inferences
- A `memory` group would need: tool functions in `backend/services/tools/` (new module); definitions plus a `_group_tools` branch, `TOOL_GROUPS` and `TOOL_TITLES` entries in `tools.py`; a prompt section in `prompts.py`; the `ToolGroup` Literal in `backend/models/catalog.py`; the frontend `ToolGroup`/`TOOL_GROUPS`, icon map and i18n strings; and the docs (`docs/model_catalog_api.md`).
- Memory tools need the persona (and maybe the conversation id) as well as the user. `_agent_tools()` and `tools_for_groups()` currently pass only `user_id`, so their signatures would grow (e.g. a context object with user_id, persona_id, conversation_id bound via `functools.partial`).
- Because `tools: null` means "every enabled tool", a memory group that is always available would also reach "Pirate" and conversations without a persona. Options: make memory opt-in (not included under `null`), or make `tool_group_unavailable_reason("memory")` depend on a setting.
- Tool-based memory can't work for models without tool support (e.g. GPT-6 Astra as configured). An injected or automatic memory path would still work for them.

### Gaps
- None significant for the registry. I didn't read `backend/services/tools/__init__.py` (24 lines).

## ALC: the rolling summary (closest existing analogue to session notes)

### Takeaway
The summary is a per-conversation checkpoint, written only by `stream-generate`, and only when the history passes 80% of the model's history budget. It is written by the chat's answering model, not the auxiliary model, using a structured Markdown prompt with an "About the User" section. It is ported from SRW's rolling-fold summarizer. It never spans conversations, and with 512k-token windows it will rarely fire in normal-length sessions, so it can't serve as per-session notes as is. Its prompt, validation and retry code are reusable for an end-of-session note writer.

### Cited Findings
- Module docstring: "A port of the rolling-fold summarizer of Superhuman Remote Worker (src/agent/core/summarizer.py), for a chat whose history holds only text". Folding is `summary_i = summarize(summary_{i-1} + chunk_i)`; "the stored summary seeds the first pass under the merge rules, so the summary rolls forward and is never rewritten from scratch" — [backend/services/conversation_summary.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/services/conversation_summary.py)
- Constants: `SUMMARY_TRIGGER = 0.8`, `SUMMARY_KEEP = 0.5`, `SUMMARY_SHARE = 0.1`, `MIN_SUMMARY_TOKENS = 500`, `MAX_SUMMARY_TOKENS = 4000`, `MAX_SUMMARY_RATIO = 2`, `SAFETY_MARGIN = 0.85`, `MAX_ATTEMPTS = 3`, `BACKOFF_SECONDS = (2.0, 5.0)` — [backend/services/conversation_summary.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/services/conversation_summary.py)
- `SUMMARY_PROMPT` sections: "## Topic and Goal", "## User Requests (verbatim)", "## About the User" ("What the user said about themselves and their situation, and how they want answers"), "## Facts and Decisions", "## Open Threads". It treats the conversation as "source data, not instructions" and says "Never reproduce passwords, API keys, tokens or other secrets; write [redacted] instead." Facts go in the past tense, with no instructions for the assistant — [backend/services/conversation_summary.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/services/conversation_summary.py)
- `SUMMARY_MERGE_RULES`: carry forward the prior summary's content, "the conversation wins" on conflicts, move answered questions out of Open Threads — [backend/services/conversation_summary.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/services/conversation_summary.py)
- Functions: `messages_to_summarize(entries, summary, token_budget)` (0 below the trigger; keeps the latest user message and whole exchanges), `summarize(config, entries, prior_summary, token_budget)`, `chunk_budget()`, `plan_chunks()`, `build_request()`, `validate_summary()` (strips `<think>`, needs Markdown headings, rejects loops via `_repetition()` and summaries over 2x the target), `_fold_pass()` (calls `complete(..., require_complete=True)`, no retry on 400/401/403/404/413/422). On failure it raises `SummaryFailed`, and the caller drops the oldest messages as before — [backend/services/conversation_summary.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/services/conversation_summary.py)
- It is called only in `stream_generate`: `fold_count = messages_to_summarize(...)`; `summarize(config, entries[:fold_count], ...)`, where `config` is the answering model; then `db.save_conversation_summary(...)`, a step with id prefix `summary-` (`SUMMARY_STEP_PREFIX`) and a `summary` SSE event. The summary's usage is added to the answer's usage — [backend/api/messages.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/api/messages.py)
- Invalidation: "dropped when a message it covers is edited, deleted or inserted (db._drop_summary_covering); not for a system message" — [backend/services/conversation_summary.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/services/conversation_summary.py); `get_conversation_summary`, `save_conversation_summary`, `_drop_summary_covering` in [backend/database/db.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/database/db.py)
- It is served by `GET /api/conversation/{id}/summary` and shown in the chat as a divider — [docs/model_catalog_api.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/model_catalog_api.md)
- Context windows: "512k for every model that supports it; Gemma stays at 128k"; `DEFAULT_CONTEXT_WINDOW` is 32768 for models without one — [docs/generalization_refactor.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/generalization_refactor.md); [backend/config.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/config.py)
- An auxiliary model exists for side tasks: `resolve_auxiliary_model()`, the first enabled model with `is_auxiliary`, else the env model, used for titles and speech preprocessing. In the starter catalog that is Gemma 4 on the homelab router. The router showed "about 15% of requests failed ... in bursts" — [backend/catalog/resolver.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/catalog/resolver.py); [docs/generalization_refactor.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/generalization_refactor.md)
- Commit: `d9c3a99` (2026-10-31) "Summarize the oldest messages when the history nearly fills the context window" — `git log` in ALC

### Inferences
- With a 512k window (about 330k real tokens at the 3-chars estimate, per the backlog note), a therapy session would almost never reach the 80% trigger. So today no summary exists for most conversations, and an "end of session" note writer would need its own trigger: an explicit "end session" action, the next conversation's start, idle time, or a tool call.
- `SUMMARY_PROMPT`'s "About the User" and "Open Threads" sections map closely onto therapist session notes ("what the client shared", "what to follow up"). `validate_summary()`, `_fold_pass()` and the retry/backoff can be reused for a cross-session note writer.
- The summary uses the answering model, so costs are in the answer's usage and quality matches the chat model. A background memory writer could use the auxiliary model, which is cheaper but on a flaky router, or the conversation's model.

### Gaps
- None. The mechanism was read in full.

## ALC: Neo4j graph tools, vector/embedding support, and anything already called "memory"

### Takeaway
The only knowledge store is an optional, global (not per-user), read-only Neo4j graph seeded from a Cypher file. There is no embedding or vector code, no pgvector (Postgres runs as plain `postgres:16-alpine`), and nothing named "memory" in code. Embeddings (Qwen3, plus a reranker) exist only as a service on the developer's homelab model router, mentioned in docs as a future option.

### Cited Findings
- Graph tools `get_graph_schema`, `search_graph(text)`, `query_graph(cypher)`. `_limited_read()` caps at `NEO4J_MAX_RESULTS` (default 25) with a `truncated` flag — [backend/services/tools/neo4j_tools.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/services/tools/neo4j_tools.py); [backend/config.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/config.py)
- Read-only enforcement: `Neo4jDatabase.query_read()` runs "inside a read transaction. Neo4j rejects writes (CREATE, MERGE, SET, DELETE, ...) in a read transaction, which makes this safe for queries written by the agent." — [backend/database/neo4j_db.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/database/neo4j_db.py)
- `NEO4J_ENABLED` defaults to false; `NEO4J_SEED_FILE` seeds an empty graph; Neo4j `neo4j:5.15-community` runs under the compose profile `graph` — [backend/config.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/config.py); [.env.example](/home/ghost/Repositories/Advanced-LLM-Chat/.env.example) (template only); [docker/docker-compose.yml](/home/ghost/Repositories/Advanced-LLM-Chat/docker/docker-compose.yml)
- The graph tools take no user argument; the graph is one shared database for all users — [backend/llm/tools.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/llm/tools.py) (`graph_tools()`)
- Postgres image: `postgres:16-alpine` in the compose files and the Helm chart (`postgresql.image.repository: postgres`, `tag: 16-alpine`), with no vector extension — [docker/docker-compose.yml](/home/ghost/Repositories/Advanced-LLM-Chat/docker/docker-compose.yml); [helm/advanced-llm-chat/values.yaml](/home/ghost/Repositories/Advanced-LLM-Chat/helm/advanced-llm-chat/values.yaml)
- `requirements.txt` has `neo4j>=5.0.0` and `openai-whisper`, but no pgvector or embedding library. A grep for "embedding"/"vector" in `backend/config.py`, `.env.example` and `requirements.txt` found nothing. In code, "embeddings" appears only in the graph tools' truncation of long lists ("lists over 50 items (for example embeddings) are shortened") — [requirements.txt](/home/ghost/Repositories/Advanced-LLM-Chat/requirements.txt); [docs/generalization_refactor.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/generalization_refactor.md)
- Whisper is wired (`WHISPER_BASE_URL`, `WHISPER_MODEL`, `USE_LOCAL_WHISPER`), but no embedding endpoint setting exists — [backend/config.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/config.py)
- The homelab router "also serves Whisper (`whisper-large-v3`), Kokoro TTS ..., Qwen3 embeddings and rerankers, which the app's voice features ... and a future vector search could use" — [docs/generalization_refactor.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/generalization_refactor.md) ("Model test results")
- "memory" in source code appears only in unrelated senses (an in-memory session cache in `backend/security/auth.py`, "free memory" comments in the frontend) — grep over `backend/` and `src/app/`
- Earlier research doc `docs/compact_chat.md` (LangGraph era, after a context overflow crash on 2025-12-29) lists industry approaches, including Anthropic's "Structured note-taking: Agent writes notes to external files (like NOTES.md) for persistent memory outside context", with Mem0 and LangGraph memory docs as references. Its plan focused on summarization, which is now implemented — [docs/compact_chat.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/compact_chat.md)
- A "RAG pipeline" commit `06d92af` (2025-11-05, "Integrate RAG pipeline into modular backend structure", adding `backend/services/pipeline.py`) exists only on a side branch (`claude/integrate-pipeline-modules-…`), not in `develop` — `git log --all`, `git branch -a --contains 06d92af`

### Inferences
- Making the graph tools into memory tools (one of the doc's ideas) would need write tools and per-user scoping, which the current graph lacks entirely, plus Neo4j to be enabled, which it is off by default.
- A Postgres-native memory store (plain tables, maybe full-text search via `tsvector`) needs no new infrastructure. Vector search would need a pgvector-enabled image (e.g. swapping `postgres:16-alpine` in compose and the Helm chart) and an embedding endpoint setting, neither of which exists.

### Gaps
- I didn't verify whether the homelab router's embedding API is OpenAI-compatible (`/v1/embeddings`). Docs only say it "serves Qwen3 embeddings and rerankers".

## ALC: planned directions in the handover docs

### Takeaway
Memory isn't on the "Next steps" list. The only related plan is the "Knowledge storage" idea under "Ideas discussed for later": a graph DB, a vector DB or both, with the remark that the graph tools "could become memory or knowledge-base tools, which would need write tools".

### Cited Findings
- Project goal: a general chat app "for testing open models ... for chatting, and for experimenting with vector and graph databases" — [docs/generalization_refactor.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/generalization_refactor.md) ("Goals and agreed plan")
- "**Knowledge storage:** a setting for a graph database, a vector database or both. The graph tools could become memory or knowledge-base tools, which would need write tools." The doc also points to existing pgvector code in a private downstream repository (not examined here, by constraint) — [docs/generalization_refactor.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/generalization_refactor.md) ("Ideas discussed for later")
- "**Homelab router services:** use its Whisper and Kokoro for voice, and its Qwen3 embeddings and reranker for a vector search" — [docs/generalization_refactor.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/generalization_refactor.md)
- "Next steps" (Status, 2026-10-31): the release merge into `main`; a Responses API adapter for GPT-6 Astra with tools; the sidebar banner and icons; refused guest login handling; the homelab router failures. No memory item — [docs/generalization_refactor.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/generalization_refactor.md)
- Upstream/downstream rule: "Keep domain-specific branding, prompts, tools and data out of this repository; add configuration points instead" — [CLAUDE.md](/home/ghost/Repositories/Advanced-LLM-Chat/CLAUDE.md)
- Backlog note on cost: "every answer resends the history, up to the context window. A 400k-token history costs about €1.08 of input per Kimi K3 answer" — [docs/generalization_refactor.md](/home/ghost/Repositories/Advanced-LLM-Chat/docs/generalization_refactor.md)

### Inferences
- Under the upstream rule, the therapist persona itself (prompt) belongs in a catalog file or the admin UI, not in code. The memory mechanism should be generic (any persona can opt in), with the therapist as one configuration.
- The Status section predates commits `e5c278b`, `d9c3a99`, `b193033`, `4e4cf70` (2026-10-31/11-01). The summary and system-message features are documented in `docs/model_catalog_api.md` and `CLAUDE.md` rather than in the Status table.

### Gaps
- No design notes on memory exist in ALC beyond the one-line idea.

## SRW: what the memory and knowledge base are, and how they are stored

### Takeaway
SRW has two separate persistence systems, and its own guide says compaction is not memory. (1) **Memory** ("RecallStore"): small facts extracted automatically by a helper model, stored in Postgres with pgvector, found by hybrid dense + sparse + recency search. (2) **Knowledge base (KB)**: notes the agent writes deliberately with `kb_*` tools, stored as Markdown files with YAML frontmatter in a git repo per project, with Postgres as a rebuildable search index. Neo4j was once the KB's source of truth and is now optional and unused for the KB. SRW is a coding/research agent platform: nothing there is per-user/persona memory for a chat companion.

### Cited Findings
- App guide: "Compaction therefore preserves a working summary for this conversation; it is not by itself a promise that a fact will be recalled by a future job or session." — [config/skills/app-guide/references/memory-and-knowledge.md](/home/ghost/Repositories/Superhuman-Remote-Worker/config/skills/app-guide/references/memory-and-knowledge.md)
- Memory table `memories` (vector DB migration `0001_initial.sql`, `CREATE TABLE IF NOT EXISTS memories` at line 195):
  - `id`, `job_id UUID NOT NULL`, `project_id`, `agent_id`
  - `content`, `summary VARCHAR(500)`
  - `memory_type` (factual / procedural / error_solution / vocabulary / relational)
  - `source` (observer / todo / compaction / phase_archive / tool_error)
  - `keywords TEXT[]`, `embedding vector(4096)` (qwen3-embedding-8b), `sparse_keywords TSVECTOR`
  - `importance`, `source_turn_start/end`, `source_phase`, `token_count`, `access_count`, `created_at`, `last_accessed`
  - `remaining_turns`, an unused former TTL column
  - [src/orchestrator/database/migrations/vector/0001_initial.sql](/home/ghost/Repositories/Superhuman-Remote-Worker/src/orchestrator/database/migrations/vector/0001_initial.sql) (`vector(4096)` verified)
- `memory_retrieval_messages(memory_id, message, embedding)` holds 3–5 "trigger phrases" per memory, embedded separately — same migration
- `0006_bitemporal_memory.sql` adds `valid_from`, `valid_to`, `superseded_at`, `superseded_by`, so retired facts are hidden, not deleted. SQL function `memory_hybrid_search` fuses dense, sparse and recency results with reciprocal rank fusion (RRF), weights 0.6 / 0.3 / 0.1, `rrf_k=50` — [src/orchestrator/database/migrations/vector/](/home/ghost/Repositories/Superhuman-Remote-Worker/src/orchestrator/database/migrations/vector/)
- Store code: class `RecallStore` (`store`, `_store_with_verdict`, `supersede`, `hybrid_search`, `retrieve`, `get_by_handle`, `summary_stats`) — [src/shared/runtime/services/recall_store.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/shared/runtime/services/recall_store.py)
- KB: files are the truth, and Postgres is "a disposable index over git". A note is `knowledge/<slug>.md` in the project's KB repo, written by the orchestrator as a server-side commit — [knowledge-history/done/okf_knowledge_base.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-history/done/okf_knowledge_base.md) §4; [src/orchestrator/services/kb_materialize.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/orchestrator/services/kb_materialize.py)
- Note frontmatter (from `_render_note_md`):
  - `id`, `type`, `description`, `tags`, `keywords`, `confidence`, `priority`, `ready_at`, `status`
  - `author`, `job`, `branch`, `created`, `modified`, `superseded_by`
  - The body is an H1 title, then the content, then a `## Relationships` section of Markdown links.
  - Types (`NoteTypeValue`): goal, plan, decision, learning, code, source, question, state, retrospective, datasource, feature, issue, idea, charter, report.
  - Status: active, resolved, superseded, archived.
  - [src/agent/tools/knowledge/knowledge_tools.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/agent/tools/knowledge/knowledge_tools.py)
- KB index tables: `knowledge_index`, `knowledge_chunks` (heading-aware chunks), `kb_index_watermark(indexed_commit, pipeline_version)` (reindexing diffs the git tree against this commit), `knowledge_links`, `knowledge_note_revisions`. Code in `knowledge_store.py`, `kb_reindex.py` and `knowledge/chunker.py` — [src/shared/runtime/services/knowledge_store.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/shared/runtime/services/knowledge_store.py); [src/orchestrator/services/kb_reindex.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/orchestrator/services/kb_reindex.py); [src/shared/runtime/knowledge/chunker.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/shared/runtime/knowledge/chunker.py)
- Neo4j is optional: `knowledge_graph.py`, and the KB tools run without it (`if kg is None:` branches) — [src/shared/runtime/services/knowledge_graph.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/shared/runtime/services/knowledge_graph.py)

### Inferences
- The SRW KB is heavy machinery (git repo per project, Gitea commits, chunked index, watermark reindex) built for teams and agents sharing a vault. A single-user chat app can keep the useful core (typed notes with status/supersede, an agent-facing write tool, search) in a plain Postgres table without the git layer.
- The `memories` schema's useful ideas for a chat app: bi-temporal supersede columns, trigger phrases, and hybrid search. The heavy part is the 4096-dim embeddings, which need pgvector and an embedding endpoint.

### Gaps
- I didn't personally re-read `knowledge_store.py` or `kb_reindex.py`. The KB index table details come from the sub-investigation, with the migration paths it named.

## SRW: tools exposed to the agent, and how retrieval reaches the model

### Takeaway
The agent gets a full KB tool family (`kb_write`, `kb_update`, `kb_delete` (archives), `kb_read`, `kb_list`, `kb_search`, `kb_grep`, graph-style helpers) and one pull tool for automatic memory (`memory_search`). Most retrieval is *pushed*: a background pipeline (hybrid recall + top KB notes, reranked, gated, capped at 10) appends each relevant item once as a tagged context block. After months of a passive-only design, the developer added a pull tool on the stated grounds that frontier models use it well.

### Cited Findings
- KB tool schemas: `KNOWLEDGE_TOOLS_METADATA` (e.g. `"kb_write"` at line 655, `"kb_search"` at line 704) — [src/shared/tool_catalog/definitions.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/shared/tool_catalog/definitions.py). Implementations — [src/agent/tools/knowledge/knowledge_tools.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/agent/tools/knowledge/knowledge_tools.py)
  - `kb_write(title, type, content, description, tags, keywords, confidence, priority, links[{target,type}], retrieval_messages, kb)`
  - `kb_update(note, content | append, status, confidence, priority, add_tags, add_links, remove_tags, set_tags)`
  - `kb_delete(note, reason)`, which archives and is reversible
  - `kb_read(note, kb)`, `kb_list(type, tag, status, job_id, kb)`
  - `kb_search(query, max_results=10, kb, exact, tags)`: semantic + literal + tag boost, falling back to full-text search when embeddings fail
  - `kb_grep(pattern, regex, max_matches)`
  - `kb_related`, `kb_contradictions`, `kb_provenance`, `kb_unanswered`
  - `kb_export`, `kb_lint`, `kb_index`
  - The sub-investigation notes that the `kb_write`/`kb_update` descriptions still call Neo4j the source of truth, which is stale.
- `memory_search(query, limit=5 (max 10), handle)`. Its description: "Relevant memories already arrive on their own as context. Call this when you need something from earlier work that the conversation does not hold…". Results carry short handles like `[m:3f9a2c]` — [src/agent/tools/memory/__init__.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/agent/tools/memory/__init__.py); [src/agent/services/memory/plugins/memory_search.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/agent/services/memory/plugins/memory_search.py)
- Retrieval pipeline (`memory.pipeline` in `expert_base.yaml`):
  - retrievers `recall_hybrid` (memories) and `kb_notes` (top 5 notes)
  - scorer `reranker` (qwen3-reranker cross-encoder)
  - policies `gate` (keep items scoring at least 0.01 × the top score) and `bounded` (at most 10)
  - extension `memory_search`
  - [config/expert_base.yaml](/home/ghost/Repositories/Superhuman-Remote-Worker/config/expert_base.yaml)
- "Append-only context injection":
  - Retrieval runs in the background next to each LLM request, and results are queued for the next request.
  - Each item is appended **once** as a `<srw_context kind="memory">` block on the last tool result or the newest user message. It stays in history and is re-eligible only after compaction removes it.
  - The query is the last user message for sessions, and the top todo plus phase for jobs.
  - [src/agent/core/context_injection.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/agent/core/context_injection.py); [src/agent/services/memory/manager.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/agent/services/memory/manager.py)
- Measured effect of append-once versus re-sending memory every turn (commit `67428d3cf`, default from 2026-10-07): prompt-cache share went from 70.8% to 95.9% (GPT) and from 53.0% to 94.3% (Claude) — per the sub-investigation, citing [knowledge-base/knowledge/features/append_only_context_injection.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-base/knowledge/features/append_only_context_injection.md)
- Passive to pull: the June overhaul principle "The model is a consumer, not a memory manager" was relaxed by adding the pull tool (`003ea6880`, 2026-10-05), because "Frontier models do this well" (decisions D25/D34) — [knowledge-base/knowledge/features/agent_memory_overhaul.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-base/knowledge/features/agent_memory_overhaul.md); [knowledge-base/knowledge/features/append_only_context_injection.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-base/knowledge/features/append_only_context_injection.md)
- Rerank + cap result: "Four measured slices took the seam from R@5 0.20 → **1.0 at 3.7 items / 111 tokens per question (80× cheaper than the full dump)**", with the winning stack "`reranker` scorer + relative `gate` + `bounded`-10" — [knowledge-base/knowledge/features/agent_memory_overhaul.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-base/knowledge/features/agent_memory_overhaul.md) (verified)

### Inferences
- ALC's `ToolRegistry` maps directly onto a small subset (e.g. `memory_write`/`note_write`, `memory_search`, `memory_update` with status/supersede, `memory_delete` as archive).
- Appending a block once and keeping it in history (rather than rewriting the system prompt each turn) protects provider prompt caching. That matters for ALC, whose backlog flags long-context cost. ALC's slot (a), the system prompt, would be cache-stable only if the injected memory doesn't change between turns of a conversation.

### Gaps
- I didn't verify the cache-share numbers directly. They come from the sub-investigation's reading of the append-only design note.

## SRW: prompts telling the agent when and what to write, and automatic memory writing

### Takeaway
The prompts tell the agent to persist important facts and decisions with `kb_write`, and to never promise lasting memory unless a durable write succeeded. That rule came from a real incident. Separately, a cheaper helper model extracts memories automatically: every 5 turns, before compaction, at session end, and once per turn via an outbox. A deduplication step (ADD/NOOP/UPDATE/MERGE) runs against the nearest neighbours. A user-focused extraction prompt treats "about the user" facts as first-class.

### Cited Findings
- Interactive system prompt, line 22: "Persist important facts and decisions with kb_write (project sessions): project knowledge is what later sessions and other people can read. notes/ files keep context for this session across compaction, and nowhere else. The memory system also captures key context automatically." — [config/prompts/systemprompt_interactive.txt](/home/ghost/Repositories/Superhuman-Remote-Worker/config/prompts/systemprompt_interactive.txt) (verified)
- Same file, line 65: "Report a save as what the tool confirmed and where it went. ... never promise that something is kept for later sessions, for other people, or "from now on" unless a durable write (kb_write, a cloud folder) succeeded. A tool result that starts with "Error:" saved nothing." — [config/prompts/systemprompt_interactive.txt](/home/ghost/Repositories/Superhuman-Remote-Worker/config/prompts/systemprompt_interactive.txt) (verified)
- Persona prompt, line 17: "Use the knowledge base (kb_write) to persist important discoveries and decisions." — [config/prompts/persona.txt](/home/ghost/Repositories/Superhuman-Remote-Worker/config/prompts/persona.txt) (verified). The job system prompt (line 33) tells the agent to save progress to the KB before compaction — [config/prompts/systemprompt.txt](/home/ghost/Repositories/Superhuman-Remote-Worker/config/prompts/systemprompt.txt)
- Incident behind the rule (issue opened 2026-10-19, P2, open). The agent told the user (in German) "Gespeichert — Test erfolgreich ✅ … ich kann ab jetzt damit arbeiten" while `kb_write` had been refused and the content went to a session-only `notes/` file. A planned "turn-end seam that surfaces failed durable writes to the *user*" was "filed on 09-04 and never built" — [knowledge-base/knowledge/issues/agent_claims_lasting_memory_for_session_local_files.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-base/knowledge/issues/agent_claims_lasting_memory_for_session_local_files.md) (verified)
- Automatic extraction by a helper model (gemma-4-31B per the sub-investigation). The job prompt `memory_extraction_prompt.txt` asks for content, summary, keywords, importance, type and 3–5 trigger phrases per memory — [config/prompts/memory_extraction_prompt.txt](/home/ghost/Repositories/Superhuman-Remote-Worker/config/prompts/memory_extraction_prompt.txt)
- User-focused extraction prompt: "A fact you skip is unrecoverable — there is no second pass over this conversation. When in doubt, extract. Prefer several small, specific, self-contained memories over one broad summary. ... Deduplication happens downstream; gaps cannot be repaired downstream." — [config/prompts/memory_extraction_prompt_complete.txt](/home/ghost/Repositories/Superhuman-Remote-Worker/config/prompts/memory_extraction_prompt_complete.txt) (verified). The sub-investigation found it used in the eval harness but not wired into the live prompt matrix.
- Session writers in `session.yaml`: `persistent_interval_extractor` (every 5 turns), `pre_compaction_extractor` (the span about to be summarized, in chunks), `teardown_extractor` (session end or idle archive). Workers add `phase_boundary_extractor`, `compaction_memory` (stores the summary itself) and `queued_memory` (from `todo_complete`) — [config/overlays/session.yaml](/home/ghost/Repositories/Superhuman-Remote-Worker/config/overlays/session.yaml); [src/agent/services/memory/plugins/legacy_writers.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/agent/services/memory/plugins/legacy_writers.py)
- Dedup verdict before storing: the helper model chooses ADD / NOOP / UPDATE / MERGE against the nearest memories ("When in doubt, ADD … wrongly retiring one loses information permanently"), only when a neighbour is ≥ 0.5 cosine-similar (`ingestion.review_floor: 0.5`, tuned from 0.6 on 2026-06-17) — [config/prompts/memory_ingestion_verdict.txt](/home/ghost/Repositories/Superhuman-Remote-Worker/config/prompts/memory_ingestion_verdict.txt); [knowledge-base/knowledge/features/agent_memory_overhaul.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-base/knowledge/features/agent_memory_overhaul.md)
- Durable end-of-turn extraction for sessions: the orchestrator runs effect `final_memory_extraction` from an outbox, once per turn — [src/orchestrator/services/session_memory_effects.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/orchestrator/services/session_memory_effects.py); [src/orchestrator/services/session_memory_executor.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/orchestrator/services/session_memory_executor.py)
- "Pending memory": after the reply, one retrieval on the latest exchange (3 s budget) is saved in `threads.metadata["aoci_pending_memory"]` (≤ 32 KB) and delivered on the next turn's first request (`MemoryManager.prefetch`) — [src/shared/session_pending_memory.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/shared/session_pending_memory.py)

### Inferences
- For a therapist persona, the "never promise lasting memory unless a durable write succeeded" rule, and surfacing failed writes to the user, transfer directly. A client told "I'll remember that" when nothing was stored is a trust failure.
- The user-focused extraction prompt ("about the user" facts, events, changes; completeness over precision) is the closest SRW artifact to therapist session notes.
- ALC's `SUMMARY_PROMPT` "About the User" section already partly overlaps with it.

### Gaps
- Whether the user-focused prompt was ever used live is unconfirmed (sub-investigation: eval harness only).

## SRW: scoping, and what the agent sees at session start

### Takeaway
Memory and the KB are scoped per project (shared by all jobs and sessions in it), else per job or session thread. There is **no per-user or per-persona memory**; personal/shared buckets are only planned. At session start the agent gets a short memory summary (counts, topics, a hint to use `memory_search`), the project charter note, and pushed items.

### Cited Findings
- `RecallStore._scope_filter`: with `project_scoped: true` (the default) and a project attached, memory is shared across the project's jobs and sessions; otherwise it is limited to the job, or to the session thread (sessions put their thread id into `job_id`). The `memories` table has no `user_id` — [src/shared/runtime/services/recall_store.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/shared/runtime/services/recall_store.py); [src/agent/api/persistent_session.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/agent/api/persistent_session.py)
- "personal" and "shared" buckets are planned only (overhaul Phase 6; `BucketRef`). Users get a "personal project" instead — [src/agent/services/memory/types.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/agent/services/memory/types.py); [knowledge-base/knowledge/features/agent_memory_overhaul.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-base/knowledge/features/agent_memory_overhaul.md)
- `memory.retrieval.same_conversation: skip_in_context` (decision D38): a conversation is not served its own memories while their source turns are still in context — per the sub-investigation (config under [config/](/home/ghost/Repositories/Superhuman-Remote-Worker/config/))
- Session start:
  - the system prompt's `<memory_model>` block
  - a one-time memory summary (count, per-type counts, frequent topics, a `memory_search` hint) from `RecallStore.render_memory_summary`
  - the project charter note, once per conversation
  - pushed KB notes and memories, plus any carried-over pending prefetch
  - [src/agent/core/memory_summary.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/agent/core/memory_summary.py)

### Inferences
- ALC would need the scope SRW never built: per user, and per persona within a user. The SRW "charter note always loaded + small summary + pull tool" pattern maps onto "a client profile always in the system prompt + recent session notes + a search tool".
- D38 (don't re-serve a conversation its own memories while still in context) applies to ALC too: memories written during the current conversation shouldn't be injected back into it.

### Gaps
- None beyond the planned buckets being unbuilt.

## SRW: approaches tried and dropped, and the lessons the developer recorded

### Takeaway
SRW moved from a single rewritten `workspace.md`, to a Neo4j KB, to files-first Markdown notes with a Postgres index. It removed a TTL "pinned" tier and an LLM "assembler". It switched from re-sending memory every turn to append-once. It measured that verbatim storage beat the original extraction pipeline, and that automatic memory "does not pay for itself across jobs", while the KB notes were pushed and pulled in every arm. This supports the developer's view that a deliberately written knowledge base is the part worth keeping, with the caveat that the KB had no clean control arm.

### Cited Findings
- Timeline (commit subjects/dates from the sub-investigation; the 2026-08-18 history rewrite left duplicate SHAs):
  - `workspace.md` (one file the agent rewrites) was replaced 2026-03-14 ("Transition knowledge handling from workspace.md to the knowledge base system"); `src/agent/managers/memory.py` is marked DEPRECATED — [src/agent/managers/memory.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/agent/managers/memory.py)
  - Neo4j as KB source of truth (2026-03-06) moved to files-first OKF notes (2026-07-03) and Neo4j-optional (2026-07-06); a later plan says "Neo4j is optional and never canonical" — [knowledge-base/knowledge/superpowers/plans/2026-07-11-okf-kb-datasource-slice-4.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-base/knowledge/superpowers/plans/2026-07-11-okf-kb-datasource-slice-4.md) (verified)
  - The TTL "pinned" tier (each new memory forced into context for 10 turns) and the "assembler" LLM that boosted or deprecated memories were introduced 2026-03-13 and removed 2026-10-18 ("retire the TTL-pinned memory tier", "remove the memory assembler"; decision D37: "Nothing read its result.")
  - Free write channels (raw tool errors, phase archives) were noisy: raw tool errors were the most-served memories, and todo boilerplate was served 2,986 times — [knowledge-base/knowledge/issues/memory_noise.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-base/knowledge/issues/memory_noise.md)
- Why Neo4j lost: "Empirically, our Neo4j is not doing graph work. Static analysis: of ~40 Cypher statements, only 2 are genuinely graph-shaped ... 0 `cypher_*` tool calls in the audited jobs; agents read the KB via `search_knowledge`/`kb_write` (retrieval), never via traversal." Also: "Three roles must stay separate: source of truth, retrieval substrate, interchange. Our old `docs/` Obsidian vault tried to be all three and drifted" — [knowledge-base/knowledge/features/knowledge_base_substrate_decision.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-base/knowledge/features/knowledge_base_substrate_decision.md) (verified)
- Self-maintenance: "**Having an LLM *author* the docs did not keep the taxonomy coherent** — nobody ran the ingest+lint loop. The artifact shape doesn't self-maintain." And: "The flat index blew its budget. The sibling agent-memory index (`MEMORY.md`) is ~41 KB against a 24 KB limit — no progressive disclosure" — [knowledge-base/knowledge/features/knowledge_base_substrate_decision.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-base/knowledge/features/knowledge_base_substrate_decision.md) (verified)
- Extraction versus verbatim (offline LongMemEval_S harness, 2026-06-12): the production pipeline "retrieves **R@5 0.20 / answers 0.25–0.30** vs **0.94 / 0.74–0.76** for trivial verbatim storage of the same history". The reader "over-abstains: 68% of answerable questions get "I don't [have that information]"". Supersede then took knowledge-update questions from 0/4 to 3/4 (overall 0.40 → 0.50). Caveat in the note: "the harness is N=20 synthetic with a gemma reader, not the product workload" — [knowledge-base/knowledge/features/agent_memory_overhaul.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-base/knowledge/features/agent_memory_overhaul.md) (verified)
- Cross-job test (2026-10-29/30, 27 jobs, arms off | kb-only | current):
  - Verdict: "**memory does not pay for itself across jobs at this scale.**"
  - Totals over positions 2–3: "current 94.0M, kb-only 74.3M, off 99.7M".
  - "96% of it is reasoning in the `auxiliary` verdict calls"; 35% of the memories carried over were the earlier job's framework to-do records.
  - "KB notes were pushed in every arm", and "`off` ≡ `kb-only`: bound-KB injection has no switch".
  - Candidate decision: "switching memory extraction off by default for jobs".
  - [knowledge-base/knowledge/tests/cross_job_memory_chain_test.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-base/knowledge/tests/cross_job_memory_chain_test.md) (verified)
- Deletion: "every mature agent-memory system that tried LLM-decided hard deletes in the write path walked it back (Mem0 v1→v3, Mem0 graph after issue #4187, Letta, Hermes, OpenClaw)". What works is that "the LLM **retires** (supersede / merge / archive ...), **code** decides freshness and protection". This is the developer's own literature claim, not independently checked here — [knowledge-base/knowledge/features/kb_gardening_retire_consolidate_purge.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-base/knowledge/features/kb_gardening_retire_consolidate_purge.md) (verified quote)
- Silent failure: a missing embedding key silently disabled both memory and the KB; the design rule became "Loud degradation, never silent" (`manager.py` docstring) — [knowledge-history/done/embedding_key_missing_silently_disables_memory_and_kb.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-history/done/embedding_key_missing_silently_disables_memory_and_kb.md); [src/agent/services/memory/manager.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/agent/services/memory/manager.py)

### Inferences
- The evidence favours, for ALC: (1) deliberate, agent-written notes (KB style) over a background extraction pipeline; (2) if anything automatic is added, storing past sessions verbatim or as structured summaries, which retrieve better than fragment extraction without heavy tuning; (3) supersede/archive instead of hard deletes by the model; (4) a reranker and a small cap if vector retrieval is added; (5) loud errors when the memory backend (e.g. an embedding endpoint) is unavailable.
- SRW's workloads are coding jobs. A therapy chat is dominated by "about the user" facts and changes over time, the case where SRW's original extraction prompt was weakest (no preferences or events) and supersede mattered most (knowledge-update questions).
- The "kb-only" advantage is suggestive, not proven: off and kb-only were the same configuration, since KB injection couldn't be switched off.

### Gaps
- The commit subjects and dates of the timeline (other than those quoted from the notes) come from the sub-investigation's `git log` and weren't re-run by me. Whether memory extraction was in fact switched off after the cross-job test is unconfirmed (config still has it enabled, per the sub-investigation).

## SRW: summarization / compaction, and how ALC's summary relates to it

### Takeaway
SRW compacts at 80% of the window, keeps the last 10 messages verbatim, and has the model summarize itself ("native", Claude/GPT) or a helper model fold the history in chunks ("auxiliary"). ALC's summarizer is a port of SRW's auxiliary `summarizer.py`. SRW recorded two summary failure modes relevant to memory: facts decaying when each prior summary was replaced, and compactors keeping only 17% of injected session constraints. ALC already counters both, with merge rules and system messages placed outside the summary.

### Cited Findings
- Trigger: 80% of the window (`CONTEXT_THRESHOLD_FRACTION` in `loader.py`), a 200-message branch, or `/compact`; logic in `ContextManager.ensure_within_limits`. Keeps the last 10 messages verbatim, with tool results in that window capped at 16,000 characters — [src/shared/runtime/core/loader.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/shared/runtime/core/loader.py); [src/agent/core/context.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/agent/core/context.py)
- Who summarizes is set per model family in `model_config_matrix.yaml`: "native" (Claude, GPT) uses `config/prompts/compaction/{claude,codex}/prompt.md` (`native_compaction.py`); "auxiliary" uses the helper model, folding chunk by chunk with reasoning off (`src/agent/core/summarizer.py`, `config/prompts/summarization_prompt.txt`, with "User Requests (verbatim)" and "[redacted]" rules) — [config/model_config_matrix.yaml](/home/ghost/Repositories/Superhuman-Remote-Worker/config/model_config_matrix.yaml); [src/agent/core/summarizer.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/agent/core/summarizer.py) (file exists, verified)
- ALC's port statement: "A port of the rolling-fold summarizer of Superhuman Remote Worker (src/agent/core/summarizer.py)" — [backend/services/conversation_summary.py](/home/ghost/Repositories/Advanced-LLM-Chat/backend/services/conversation_summary.py)
- Injected memory and KB blocks are left out of the summary because they get re-injected: "The memory store, not the summary, is the source of truth" (D4). Findings F1 (facts decayed because each prior summary was discarded and replaced) and F8 ("compactors kept only 17% of injected session constraints") — [knowledge-base/knowledge/features/compaction_refactor_fidelity_and_fork_strategy.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-base/knowledge/features/compaction_refactor_fidelity_and_fork_strategy.md)

### Inferences
- ALC's `SUMMARY_MERGE_RULES` (carry forward the prior summary) addresses F1. Putting system messages in the system prompt instead of the history addresses F8. Injected memory in ALC should likewise sit outside the summarized history (system prompt or a marked block the summarizer excludes), following SRW's D4.

### Gaps
- I didn't read SRW's native compaction prompts.

## SRW: user control, deletion and privacy of memory

### Takeaway
Users can browse, re-status, delete and export KB notes in the Cockpit. The agent can only archive. Automatic memories have no user-facing edit/delete at all, only a read-only debug panel. Job deletion removing shared memories is filed as a bug. No secret redaction of extracted memories was found.

### Cited Findings
- KB in the Cockpit (Projects → Knowledge): browse, filter, change status, delete, export. A human delete is an immediate file-removal commit (`DELETE /api/projects/{id}/knowledge/{note_id}`) — [src/orchestrator/routers/knowledge.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/orchestrator/routers/knowledge.py); [cockpit/src/app/core/services/api.service.ts](/home/ghost/Repositories/Superhuman-Remote-Worker/cockpit/src/app/core/services/api.service.ts)
- Agent `kb_delete` only archives, and is refused for charter or pinned notes, notes linked from active decisions, and notes under 24 h old. Physical purge is a separate lane, off by default (`KB_PURGE_ENABLED`). `kb_write`/`kb_update` refuse to write the `[REDACTED]` marker back over real content — [src/orchestrator/services/kb_purge.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/orchestrator/services/kb_purge.py); [src/agent/core/redaction_write_guard.py](/home/ghost/Repositories/Superhuman-Remote-Worker/src/agent/core/redaction_write_guard.py)
- "Memory has no general Cockpit browsing/editor surface" — [config/skills/app-guide/references/memory-and-knowledge.md](/home/ghost/Repositories/Superhuman-Remote-Worker/config/skills/app-guide/references/memory-and-knowledge.md) (verified). There is only a read-only debug panel (`cockpit/src/app/workbench/components/memory-panel/`) and GET endpoints (`src/orchestrator/routers/citations.py`)
- Deleting a job also deletes shared project memories, filed as a bug — [knowledge-base/knowledge/issues/job_delete_removes_project_memories.md](/home/ghost/Repositories/Superhuman-Remote-Worker/knowledge-base/knowledge/issues/job_delete_removes_project_memories.md)
- Pushed memory is labelled "harness context, not a user message" — [config/guardrails/default.yaml](/home/ghost/Repositories/Superhuman-Remote-Worker/config/guardrails/default.yaml) (line 332)
- The sub-investigation found no secret redaction on extracted memories (`recall_store.py`, `auxiliary.py`, `agent/services/memory/`), and noted that the base extraction prompt's own example stores server login details — [config/prompts/memory_extraction_prompt.txt](/home/ghost/Repositories/Superhuman-Remote-Worker/config/prompts/memory_extraction_prompt.txt)

### Inferences
- For therapy content (special-category health data in GDPR terms), SRW is a negative example on user control. ALC would need, from the start, a user-visible list of what the persona remembers, with edit and delete; hard deletion on user request (unlike the agent's archive-only path); and inclusion in guest cleanup and account deletion.
- ALC's summary prompt already redacts secrets. A memory writer should carry the same rule, and the "harness context, not a user message" labelling of injected memory is worth copying, as a guard against prompt injection via stored memories.

### Gaps
- Redaction of memories is unconfirmed either way (only an absence in the files searched).
