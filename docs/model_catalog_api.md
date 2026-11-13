# Model catalog and LLM runtime: interfaces

The contract between the new LLM runtime (`backend/llm/`), the model catalog (`backend/catalog/`, `backend/api/catalog.py`) and the frontend. Written on 2026-10-30, before the implementation, and revised the same day: provider API keys only come from environment variables, providers are defined only by the catalog file, and models and agents (personas with a tool selection) are edited in the UI. The background and decisions are in `docs/model_provider_strategy.md`.

Already in place:
- `backend/llm/types.py`: `ModelConfig`, `Usage`, `model_from_env()`
- `backend/models/catalog.py`: request and response models of the catalog API
- `backend/models/message.py`: `MessageUsage`, plus the model and usage fields on messages and stream events
- `backend/database/queries/schema.sql` and `tables.py`: tables `llm_providers`, `llm_models`, `personas`, and the new columns on `conversations`, `messages` and `user_settings`
- `backend/config.py`: `MODEL_CATALOG_FILE`, `ADMIN_EMAILS` (and `OIDC_ADMIN_ROLE`, docs/authentication.md), `AGENT_MAX_STEPS`

## Runtime (`backend/llm/`)

Built on the official `openai` and `anthropic` SDKs. LangChain and LangGraph are removed.

- **Message format:** OpenAI Chat Completions message dicts throughout (`role`, `content` as a string or a list of `text` / `image_url` blocks, `tool_calls`, `tool_call_id`). An assistant message may carry `reasoning_content`. The Anthropic client converts to and from this format.
- `client.py`: builds an `AsyncOpenAI` or `AsyncAnthropic` client from a `ModelConfig` (base URL, key, default headers, `LLM_TIMEOUT`).
- `agent_loop.py`:
  ```python
  async def run_agent(config: ModelConfig, messages: list[dict], *, system_prompt: str,
                      tools: ToolRegistry | None = None,
                      max_steps: int = AGENT_MAX_STEPS) -> AsyncIterator[tuple[str, Any]]
  ```
  Yields, in this order of appearance:
  - `("step", AgentStep)`: a new step, or a replacement for a step with the same `id`
  - `("step_delta", {"id": str, "delta": str})`: text appended to the content of an earlier step (live reasoning)
  - `("token", str)`: text of the answer
  - `("usage", Usage)`: exactly once, last, summed over all model calls

  It streams a completion, collects text, reasoning and tool-call deltas, runs the requested tools, appends the assistant message (with `reasoning_content` when `config.reasoning_passback` is set, and Anthropic thinking blocks with their signatures for Claude) and the tool results, and repeats until there are no tool calls or `max_steps` is reached. Before the usage it yields the answer's tool record (`("tool_record", list)`, see "Tool calls of earlier answers"). Tools are only sent when `config.supports_tools` is set.
- `complete(config, messages, *, system_prompt=None, max_output_tokens=None) -> tuple[str, Usage]`: one call without tools or streaming, for titles, speech preprocessing, the legacy non-streaming endpoints and the smoke test.
- **Cost of an answer** (`ModelConfig.cost(usage)`, stored as `cost` in the message's `usage` and shown with the answer): what the provider billed, when it reports that and the provider has a `reported_cost_unit`, else computed from the model's prices.
  - **Reported:** some providers add the cost of a call to its usage (`usage.cost`; Cortecs in millionths of a euro, each part rounded up, with a breakdown in `cost_details`). The provider's `reported_cost_unit` is the value of one unit in its currency (Cortecs: `0.000001`). `Usage` counts its model calls and those that reported a cost (`calls`, `reported_calls`, `reported_cost`); the answer's cost is the reported one only when every call reported it, else it is computed. This is the exact price: a router such as Cortecs sends each request to one host of the model, at that host's price, while the catalog's prices are the cheapest host's (`/v1/models`; per host: `/v1/models/<id>?extended=true`).
  - **Computed:** a model's prices are per million tokens in its provider's currency: `input_price_per_mtok`, `output_price_per_mtok` and `cached_input_price_per_mtok`, the price of input read from the provider's cache. `Usage.cached_input_tokens` counts that input (OpenAI-compatible APIs: `prompt_tokens_details.cached_tokens`; Anthropic: `cache_read_input_tokens`), and it is part of `input_tokens`. With a cached price, the cost is (input − cached) × input price + cached × cached price + output × output price. Without one, all input costs the input price. Without an input or an output price there is no cost. Anthropic charges cache writes (`cache_creation_input_tokens`) at 1.25 times the input price; the cost counts them at the input price, so a Claude answer that writes a large part of its prompt to the cache shows somewhat less than it cost. Prices that depend on the prompt's length (Claude Haiku 5.5 over 100,000 tokens, GPT-6 Astra over 272,000) are not modelled either.
- `tools.py`: a registry of async functions with explicit JSON schemas (`list_files`, `read_file`, `get_graph_schema`, `search_graph`, `query_graph`, `web_search`, and the knowledge base's `kb_search`, `kb_list`, `kb_read`, `kb_write`, `kb_update`, `kb_archive`). `default_tools(user_id=None)` returns the enabled ones (graph tools with `NEO4J_ENABLED`, web search with `TAVILY_API_KEY`), without the opt-in groups. The registry is built per answer for the user it is for: the file tools only see that user's files of the conversation (table `uploaded_files`, `docs/files.md`), other files get the same "not found" error as missing ones, and without a user or a conversation they see none; a tool result may carry images for the model (`ToolText.images`), which each adapter places where its API takes them; the knowledge base tools only see that user's notes (`docs/knowledge_base.md`). The model can't pass a user; the argument is not in the schema.
- **Tool groups** (`TOOL_GROUPS` in `tools.py`), what an agent selects: `files` = `list_files`, `read_file` (the agent shows a file by placing it in its answer's text, `docs/files.md`), `web_search` = `web_search`, `knowledge_graph` = `get_graph_schema`, `search_graph`, `query_graph`, `knowledge_base` = the six `kb_*` tools and the three `memory_*` tools, `past_chats` = `chat_search`, `chat_list`, `chat_read` (the user's earlier conversations of the agent's memory, `docs/past_chats.md`; only together with `knowledge_base`, `REQUIRED_GROUPS`), `user_mcp` = the tools of the user's own MCP servers (none of its own: they are added per answer, `docs/mcp.md`). `knowledge_base`, `past_chats` and `user_mcp` are **opt-in groups** (`OPT_IN_GROUPS`): only an agent that selects them gets them, never "every enabled tool", and only a signed-in user, never a guest. `tools_for_groups(groups, user_id=None, *, guest=False, conversation=None, vault=0, vision=False)` gives the enabled tools of those groups (`None` = `default_tools(...)`, `[]` = none); `conversation` (id, persona_id) is the one whose files the file tools see, and is recorded with every knowledge base change; with `vision`, `read_file` gives the model images themselves. `tool_group_status()` says which groups the configuration enables and why not (`tool_group_unavailable_reason()`, the same checks `default_tools()` uses), and which are opt-in.
- **Request settings** from the `ModelConfig`: `temperature`, `top_p`, `max_output_tokens` and `reasoning_effort` are only sent when set; `extra_body` is merged into the request body as-is.
- **Conversation history** (`backend/services/conversation_history.py`): the newest messages that fit `context_window` (`DEFAULT_CONTEXT_WINDOW`, 32768, for models without one), at most `HISTORY_MAX_MESSAGES`. `history_token_budget(config, system_prompt, tools)` subtracts room for the answer (`max_output_tokens`, else 32000, at most a quarter of the window), 10% of the window for tool results during the run, and the system prompt and tool definitions. Tokens are estimated at 3 characters each. The latest user message is always sent. The context window is therefore also a cost limit: each answer resends the history, up to the whole window.
- **Tool calls of earlier answers** (`backend/llm/tool_record.py`): an answer that called tools is stored with its **tool record**, the messages the agent loop added to the history while it was written: the model's tool calls (with the text before them, and `reasoning_content` for models that get it passed back), the results as the model got them, and the answer's last text. `run_agent()` reports it as a `("tool_record", list)` event before the usage (`[]` when no tool was called), and it is stored in `message_tool_records` (one row per answer, apart from `messages`, so no message list carries it). The history puts it back in place of the answer's text: real tool calls and tool results, then the text. Without it a model can't tell what it did in earlier turns: asked "did you really look at the image?", Kimi K3 found no tool call in its history and said it never had, after reading the image with `read_file` two turns before (2026-11-12).
  - **Exact continuation:** the record is what the model was sent, so the next answer's request starts with the last request of the answer before, word for word. Provider caches read from the start of a request, so that part can be read from the cache. Two things differ once: images (below), and Claude's thinking blocks, which are only passed back within one answer. Measured with Claude Haiku 5.5 on 2026-11-12: 70% of the input read from the cache in the turn after a tool-using answer, 99% in the turn after that. Kimi K3 through the Cortecs gateway read 43% to 69% although the requests matched; that is the gateway's side.
  - **Only complete rounds:** a call whose results never came (the run broke off) is left out. An answer that failed after its tools ran keeps the record: the tools did run.
  - **Images** a tool result carried (`read_file` on an image, for a vision model) are not sent again: the record holds a note in their place that says the model saw them and can call the tool again.
  - **Long results:** a result longer than `HISTORY_TOOL_RESULT_CHARS` (20000; 0: no limit) is cut in later turns, with a note of how much is missing. The stored record stays whole.
  - **Budget:** an answer with a record counts with its calls and results (`entry_tokens()`), and is kept or left out whole, never a result without its call. The summarizer reads the calls and the first 2000 characters of each result.
  - **Editing:** changing an answer's text (`PATCH /api/message/patch`) keeps its calls and results; the new text becomes its only text. The non-streaming regenerate writes a new text without tools, so the record goes. It goes with the message.
  - **Other models:** every model gets the records, also of answers another model wrote. All catalog models reachable on 2026-11-12 accepted them, with or without `tools` in the request, with unknown tool names and with repeated ids (DeepSeek V4.1 Flash, DeepSeek V4 Pro, Mistral Large 4, Kimi K3, GLM-5.3, Gemma 4, Claude Haiku 5.5 and Sonnet 5.5; GPT-5.2 not tested). Claude only takes letters, digits, `_` and `-` in a tool call id, so the Anthropic adapter cleans every id (Kimi's are like `read_file:0`).
  - **Off switch:** `HISTORY_TOOL_CALLS=false` sends only the answers' text, as before 2026-11-12.
  - **Not covered:** an answer the user stopped is stored by the browser, without a record; conversation files don't carry records (an imported conversation has the answers' text only); answers from before 2026-11-12 have none.
- **Summary of the oldest messages** (`backend/services/conversation_summary.py`, a port of Superhuman Remote Worker's rolling-fold summarizer): when the history passes 80% of that budget, the chat's model folds the oldest whole exchanges into a summary before it answers, so that about half the budget stays word for word (minus room for the summary, which is asked for at 10% of the budget, 500 to 4000 tokens). Messages that don't fit the model's window in one call are folded in chunks, each pass merging the previous summary; the stored summary seeds the next fold, so it rolls forward. A reply without the Markdown sections, cut off, looping or longer than twice the asked length is retried (3 attempts); if it still fails, nothing is summarized and the oldest messages that don't fit are left out as before. The summary is stored per conversation (`conversation_summaries`: `covers_until`, the newest message id it covers), sent first in the history as a user message, shown in the stream as a step and a `summary` event, served by `GET /api/conversation/{id}/summary`, and shown in the chat as a divider after the newest covered message. Editing, deleting or inserting a message it covers deletes it (the next answer writes a new one), except for a system message. Its model calls count toward the answer's usage.
- **Summary on request:** **Summarize** in a conversation's menu (sidebar) calls `POST /api/message/summarize` (`{"conversationId"}`, rate-limited for guests like an answer), which folds every message so far into the summary, merging the stored one, and returns it (`ConversationSummary`); the next answer gets the summary and only the messages after it. The chat shows a pending divider at its end meanwhile, then the divider after the newest message. Since a model fills the length it is asked for, the summary is asked for at most a third of what it covers (at least 250 tokens, at most the length for the budget), and only one past twice the length for the budget counts as too long; it must still come out shorter than the messages. 409: nothing after the stored summary; 422: too short (under 500 tokens, checked without a model call, or a summary that isn't shorter); 502: the model failed after its attempts (nothing stored). Its usage is only logged, not stored on a message.
- **Input token indicator (manual editing):** `POST /api/message/context-size` (`{"conversationId", "modelId"?}`, not rate-limited, no model call) counts what stream-generate would send now, with the same `estimate_tokens()`: the system prompt, the tool definitions and the history (the summary, then the newest messages that fit, the latest user message with its attachments, earlier answers with their tool calls and results). It returns `ContextSize`: `inputTokens` (= `systemTokens` + `toolTokens` + `historyTokens`), `contextWindow` (`DEFAULT_CONTEXT_WINDOW` without one), `historyBudget`, `messageCount`, `leftOutCount` (messages that don't fit) and `summarizes` (past 80% of the budget: the next answer first folds the oldest messages, so it sends less). The agent's MCP servers are not asked for their tools (`_answer_context(mcp=False)`), so their tools are not counted. In manual editing the composer shows it next to the mic as a ring and "931 / 524k" (only the count on phones), plus about a token per 3 characters of the draft; the ring turns amber when messages are left out or the next answer summarizes, and the tooltip breaks the count down. The chat asks again 300 ms after the messages, the summary, the model or the agent change, and only with a session. Measured against DeepSeek V4.1 Flash on a short chat: 931 estimated, 901 counted by the model.
- **Reasoning shown as steps:** reasoning text becomes a `thought` step titled "Thinking" that grows through `step_delta` events. It arrives as `reasoning_content` (Kimi, DeepSeek, Qwen), `reasoning` (some routers) or Anthropic thinking blocks. The old placeholder steps ("Analyzing request...", "Generating Response") go away.
- **System prompt:** `build_system_prompt(persona_prompt: str | None, tools)` returns the identity paragraph (or the persona prompt in its place), followed by the sections for the tools it is given (file access, knowledge graph, knowledge base, the web search hint). With the knowledge base tools, `with_memory(system_prompt, memory)` adds the agent's memory with today's date (`docs/knowledge_base.md`, "Memory"). `with_instructions(system_prompt, texts)` adds the conversation's system messages at the end, under "## Instructions for this conversation:" (`ConversationHistoryBuilder.system_instructions()`: all of them, oldest first, or the ones before the message being regenerated). A system message is an instruction for every answer after it; it goes into the system prompt rather than its place in the history because many chat templates of open models accept a system message only at the start, so it is never cut off or summarized, and editing, deleting or inserting one keeps the summary.
- **The system prompt in the chat (manual editing):** `GET /api/message/system-prompt?conversationId=…&modelId=…` returns `{content, custom, tokens}`: the system prompt the next answer gets, as its model gets it (built like stream-generate builds it, with the agent's MCP servers; nothing is sent to a model), without the conversation's system messages, which follow it and which the chat shows where they are. Manual editing shows it as the conversation's first message (`SystemPromptComponent`), plain text, cut to its first lines until it is opened. `PUT /api/message/system-prompt` (`{conversationId, content, modelId?}`) gives the conversation its own system prompt (`conversations.system_prompt`): its answers then get that text as it is, in place of everything built from the agent (`_own_system_prompt()` in `backend/api/messages.py`), so the memory, the notes on tools and the date in it no longer change. `""` sends no system prompt, `null` goes back to the built one. The system messages still follow it, and the tools stay as they are. At most 200,000 characters; a guest's change counts as a write. A conversation's own prompt is not in its conversation file yet. Tested by `test_system_prompt_is_shown_and_can_be_replaced` in `backend/llm/tests/test_summary.py`.
- **Generate after an answer (manual editing):** the composer's Generate answers the conversation as it stands, also when its newest message is the model's. No provider answers such a history as it is (Anthropic takes the last message as the start of the answer or refuses it, others demand that a user message comes last), so `stream-generate` appends `CONTINUE_NOTE` (`backend/services/conversation_history.py`) as a user message and shows that with the step "Asked to go on", which is stored with the answer. The note is not stored as a message, so later requests have the two answers one after the other. Tested by `test_generate_after_an_answer_asks_the_model_to_go_on`, and live on 2026-11-13 with DeepSeek V4.1 Flash, Claude Haiku 5.5 and Mistral Large 4, three times in a row in one conversation.
- **Tools of an answer** (`stream-generate`): the enabled tools of the tool groups of the conversation's persona (`persona_tool_groups()`); a persona without a selection (`tools: null`), no persona, or a persona the user may not use gets every enabled tool except the opt-in groups. Then the tools of the persona's MCP servers (`mcp_servers`, and the user's own with `user_mcp`; `docs/mcp.md`); a server that gives no tools is shown as a step at the start of the answer. An empty result sends no tools at all (`tools=None`), as does a model without `supports_tools`. The system prompt and the history token budget are computed with these tools.
- **Skills** (`docs/skills.md`): an agent's enabled skills (`personas.skills`, `persona_skills()`) are listed in the system prompt by name and description (`with_skills()`, after the tool sections), and the tool `use_skill` (`skill_tools()`) loads one's text. Only for a model with `supports_tools`; an agent with skills gets the tool also without tool groups.

## Catalog (`backend/catalog/`)

- `resolver.py`:
  - `resolve_model(user, model_id=None, conversation=None) -> ModelConfig`. Order: `model_id`, then the conversation's `model_id`, then the user's `default_model_id`, then the first enabled model by `sort_order`, then `model_from_env()`. Raises `ModelNotAvailable` when nothing is left, and `ModelNotAllowed` when an explicitly requested model is disabled or not available to the user.
  - `resolve_auxiliary_model() -> ModelConfig | None`: the first enabled model with `is_auxiliary`, else `model_from_env()`.
  - `get_model_config(model_id) -> ModelConfig`: no permission check (smoke test, admin test button).
  - `render_persona_prompt(persona_id, values, *, user_name, language) -> str | None`.
  - `persona_prompt_for_conversation(user, conversation)` and `persona_tool_groups(user, conversation) -> list[str] | None`: the rendered prompt and the tool groups of the conversation's persona, for the runtime (`None` without a usable persona; for the tools also when the persona has no selection).
- **Visibility:** guests only see and use models and personas with `available_to_guests`. A guest without any guest model gets the environment model, as today. Disabled providers hide their models.
- **Providers** are defined only by the catalog file (`MODEL_CATALOG_FILE`) and are read-only in the API. Changing one means editing the file and running `app_init` again (Docker's `db-init` does it on every `docker compose up`).
- **API keys** only come from environment variables: a provider names one in `api_key_env` (it must end in `_KEY` or `_TOKEN`), and its key is `os.getenv(api_key_env)`. Keys are never stored or returned; the API only says whether the variable is set (`apiKeySet`). Databases from before this change keep an unused `api_key_encrypted` column (`ALTER TABLE llm_providers DROP COLUMN api_key_encrypted` removes it).
- **Admins:** with `AUTH_MODE=oidc`, users with `OIDC_ADMIN_ROLE` or a verified email in `ADMIN_EMAILS`; with the mock login, users whose email is in `ADMIN_EMAILS`. Guests never are (docs/authentication.md). Without admins, the catalog is still seeded from `MODEL_CATALOG_FILE`.

### Personas (agents)

The UI calls them agents; the API, the database and the catalog file keep the name persona.

- `tools`: the tool groups the agent may use, a list of `"files"`, `"web_search"`, `"knowledge_graph"`, `"knowledge_base"`, `"past_chats"` and `"user_mcp"`. `null` (the default) means every tool the server has enabled except the opt-in `"knowledge_base"`, `"past_chats"` and `"user_mcp"`, which an agent only gets by selecting them (`"past_chats"` only together with `"knowledge_base"`, `docs/past_chats.md`); `[]` means no tools. A selected group the server has switched off simply gives no tools (see `GET /api/admin/tools`).
- `mcpServers` (`mcp_servers`): the slugs of the admins' MCP servers the agent uses (`docs/mcp.md`); null for none. Always picked explicitly, also with `tools: null`.
- `skills`: the names of the agent's skills (`docs/skills.md`); null for none. Unknown names are a 400, duplicates are dropped.
- An agent has no model of its own; the conversation's model answers.
- The prompt may use `{{variable}}` placeholders. A value comes from the conversation's `persona_values`, else the variable's `default`, else an empty string.
- Built-in variables: `{{date}}` (e.g. "Friday, 30 October 2026"), `{{user_name}}` (the user's name, else the part of the email before the @, "Guest" for guests), `{{language}}` (the UI language, e.g. "German").
- Unknown placeholders are left unchanged.

## HTTP API

All bodies are camelCase JSON, like the rest of the API. Authentication and CSRF work as for the other endpoints.

### For every user (guests filtered)

| Method and path | Response |
|---|---|
| `GET /api/models` | `PublicModel[]`, enabled models of enabled providers, sorted by `sortOrder`, then name. Empty when the catalog is empty (then the environment model answers). |
| `GET /api/personas` | `PublicPersona[]` |

### Admin only (403 otherwise)

| Method and path | Body | Response |
|---|---|---|
| `GET /api/admin/providers` | | `ProviderOut[]`; there are no endpoints to change providers |
| `POST /api/admin/providers/{id}/fetch-models` | | `FetchModelsResponse` from the provider's `GET /models` |
| `GET /api/admin/models` | | `ModelOut[]` |
| `POST /api/admin/models` | `ModelCreate` | `ModelOut` |
| `PUT /api/admin/models/{id}` | `ModelUpdate` | `ModelOut` |
| `DELETE /api/admin/models/{id}` | | 204 |
| `POST /api/admin/models/{id}/test` | | `{"ok": bool, "latencyMs": int, "reply": str?, "error": str?}`; sends a short prompt. Added during integration. |
| `GET /api/admin/personas` | | `PersonaOut[]` |
| `POST /api/admin/personas` | `PersonaCreate` | `PersonaOut` |
| `PUT /api/admin/personas/{id}` | `PersonaUpdate` | `PersonaOut` |
| `DELETE /api/admin/personas/{id}` | | 204 |
| `GET /api/admin/tools` | | `ToolGroupStatus[]`, all five groups |
| `GET /api/admin/skills` | | `SkillOut[]`, by name, each with the agents that have it (`docs/skills.md`) |
| `POST /api/admin/skills` | `SkillCreate` | `SkillOut` (201); 409 for a taken name |
| `PUT /api/admin/skills/{id}` | `SkillUpdate` | `SkillOut`; a new name is also changed in the agents |
| `DELETE /api/admin/skills/{id}` | | 204; the skill is taken off the agents |
| `POST /api/admin/skills/import` | `{"text": "<SKILL.md>", "replace": false}` | `{"skill": SkillOut, "created": bool, "ignored": [frontmatter keys left out]}` |
| `GET /api/admin/skills/{id}/export` | | the skill as a `SKILL.md` file (`text/markdown`) |
| `GET /api/admin/catalog/export` | | the catalog file below, as a download; usable as `MODEL_CATALOG_FILE` |
| `POST /api/admin/catalog/import` | the catalog file below | `ImportResult` |

### Response and request models

The Pydantic models are in `backend/models/catalog.py`. The ones this revision changed:

```text
ProviderOut      id, name, kind, baseUrl, apiKeyEnv, apiKeySet, privacyTier, currency,
                 defaultHeaders, notes, enabled, modelCount, createdAt, updatedAt
PersonaCreate    name, description?, systemPrompt, variables = [], tools = null,
                 availableToGuests = false, enabled = true, sortOrder = 0,
                 ownMemory = false (with knowledge_base: its own knowledge base and memory per user),
                 mcpServers = null (slugs of admin MCP servers, docs/mcp.md),
                 skills = null (names of skills, docs/skills.md)
PersonaUpdate    the same fields, all optional; left out = unchanged, tools: null = every enabled tool
                 (without the opt-in knowledge_base)
PersonaOut       PersonaCreate + id
PublicPersona    id, name, description, systemPrompt, variables, tools
ToolGroupStatus  id ("files" | "web_search" | "knowledge_graph" | "knowledge_base" | "past_chats" | "user_mcp"),
                 available, reason (e.g. "TAVILY_API_KEY is not set", "NEO4J_ENABLED is off"; null when available),
                 optIn (only for personas that select it, not part of tools null: knowledge_base, past_chats, user_mcp),
                 requires (the group it only works with: "knowledge_base" for past_chats, else null)
SkillCreate      name (^[a-z0-9]+(-[a-z0-9]+)*$, at most 64), description (1 to 1,024), content (1 to 20,000),
                 enabled = true
SkillUpdate      the same fields, all optional
SkillOut         SkillCreate + id, agents [{id, name}], createdAt, updatedAt
ImportResult     models {created, updated}, personas {created, updated}, mcpServers {created, updated},
                 skills {created, updated}, errors
```

`tools` is a list of tool groups or `null`; duplicates are dropped and the groups are stored in the order above. Unknown groups are a 422.

### Changes to existing endpoints

- `GET /api/auth/me`: adds `isAdmin`.
- Conversations (`GET /api/conversations`, `GET /api/conversation/{id}`, `POST /api/conversation/create`, `PATCH /api/conversation/{id}`): accept and return `modelId`, `personaId` and `personaValues` (an object of variable values). `null` means the user's default model and no persona.
- Settings (`GET` / `PUT /api/settings`): add `defaultModelId`, and `memoryModelId` (the model of the memory review, which needs tools; null = the conversation's model; `resolve_memory_model()`).
- Agent messages (message sync and all message responses): add `modelId`, `modelName` and `usage` (`MessageUsage`).
- `POST /api/message/stream-generate`: optional `modelId` to answer with another model than the conversation's.

### Streaming protocol (`/api/message/stream-generate`)

Unchanged events keep their meaning. Additions:

- `message_start`: adds `modelId` (null for the environment model) and `modelName`.
- `step`: if a step with the same `id` already exists, the new one replaces it (the reasoning step is sent once empty at its start and once complete at its end).
- `step_delta` (new): `{"id": "<step id>", "delta": "<text>"}`, append `delta` to that step's content.
- `done`: adds `modelId`, `modelName` and `usage` (`MessageUsage`).

## Catalog file

Used for `MODEL_CATALOG_FILE` seeding and for import and export. JSON with snake_case keys matching the database columns. Natural keys: providers by `name`, models by `provider` + `display_name`, personas by `name`, the admins' MCP servers (section `mcp_servers`, `docs/mcp.md`) by `slug`, skills (section `skills`: `name`, `description`, `content`, `enabled`; `docs/skills.md`) by `name`; servers and skills are imported before the personas, which name them in `mcp_servers` and `skills`. Nothing is ever deleted. Keys are referenced by environment variable (`api_key_env`); an `api_key` entry is ignored with a message.

**Seeding** (`app_init`, on every start and also with `--prod`; Docker's `db-init` runs it on every `docker compose up`). `MODEL_CATALOG_FILE` defaults to `catalog/models.json` (relative to the repository root); an empty value disables seeding.
- Providers: the file is their source of truth. Each entry creates the provider or replaces it completely, so a field removed from the file is cleared. Its models are kept. A provider that is in the database but no longer in the file is left alone, with a warning in the log.
- `${VAR}` in a provider's `base_url` is filled from the environment; a provider whose variable is unset is skipped, together with its models. A provider whose `api_key_env` variable is unset is saved disabled (and enabled again once it is set), unless the entry sets `enabled` itself.
- Models and personas are only created when missing. Existing ones are left untouched, so edits made in the app are never overwritten by a deploy. This includes prices: a price changed in the file only reaches a model the database doesn't have yet. The one exception is the cached price, which came after the models (2026-11-13): an existing model without one takes the file's on the next start, and one set in the app is kept. For an existing model, change it on the Agents page, or import the file there; the import writes every key present in the file, so it also undoes edits made in the app to the other models and agents in it.

**Import in the app** (`POST /api/admin/catalog/import`) upserts models and personas: a new entry gets defaults for the keys it leaves out, an existing entry only changes the keys that are present, and `null` clears optional columns. Provider entries are ignored, with one message in `errors` ("providers ignored: providers come from the server's catalog file"); a model whose provider is not in the catalog is reported in `errors`. Unknown keys are reported and ignored; each bad entry is reported and the others are still imported.

**Export** writes every column of providers, models and personas, without keys and without ids.

**Skills** are seeded, imported and exported like personas. In a seed file a skill can instead name a `SKILL.md` next to the catalog file, `{"file": "skills/image-generation/SKILL.md"}` (inside the catalog file's folder; only when seeding, never in an import in the app). The repository's `catalog/models.json` ships the starter skills this way, from `catalog/skills/`.

```json
{
  "version": 1,
  "providers": [
    {
      "name": "Cortecs",
      "kind": "openai_compatible",
      "base_url": "https://api.cortecs.ai/v1",
      "api_key_env": "CORTECS_API_KEY",
      "privacy_tier": "eu",
      "currency": "EUR",
      "notes": "EU router (Vienna). Account: Sovereign Cloud and zero data retention on, Nebius excluded."
    }
  ],
  "models": [
    {
      "provider": "Cortecs",
      "display_name": "Kimi K3",
      "model_id": "kimi-k3",
      "supports_tools": true,
      "supports_vision": true,
      "reasoning": "always",
      "reasoning_passback": true,
      "reasoning_effort": "high",
      "context_window": 1048576,
      "input_price_per_mtok": 2.693,
      "output_price_per_mtok": 13.464,
      "available_to_guests": false,
      "sort_order": 40
    }
  ],
  "personas": [
    {
      "name": "Pirate",
      "description": "Answers in pirate speak",
      "system_prompt": "You are a helpful assistant who always talks like a {{style}}. Today is {{date}}.",
      "variables": [{"name": "style", "label": "Style", "default": "pirate"}],
      "tools": ["files", "web_search"],
      "available_to_guests": true
    }
  ]
}
```

Every model column from `schema.sql` may appear; left-out columns take their defaults. A persona's `tools` may be left out (or `null`) for every enabled tool except the opt-in `"knowledge_base"`, or `[]` for none.
