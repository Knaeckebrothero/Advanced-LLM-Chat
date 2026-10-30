# Model catalog and LLM runtime: interfaces

The contract between the new LLM runtime (`backend/llm/`), the model catalog (`backend/catalog/`, `backend/api/catalog.py`) and the frontend. Written on 2026-10-30, before the implementation; the background and decisions are in `docs/model_provider_strategy.md`.

Already in place:
- `backend/llm/types.py`: `ModelConfig`, `Usage`, `model_from_env()`
- `backend/models/catalog.py`: request and response models of the catalog API
- `backend/models/message.py`: `MessageUsage`, plus the model and usage fields on messages and stream events
- `backend/database/queries/schema.sql` and `tables.py`: tables `llm_providers`, `llm_models`, `personas`, and the new columns on `conversations`, `messages` and `user_settings`
- `backend/config.py`: `CATALOG_SECRET_KEY`, `MODEL_CATALOG_FILE`, `ADMIN_EMAILS`, `AGENT_MAX_STEPS`

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

  It streams a completion, collects text, reasoning and tool-call deltas, runs the requested tools, appends the assistant message (with `reasoning_content` when `config.reasoning_passback` is set, and Anthropic thinking blocks with their signatures for Claude) and the tool results, and repeats until there are no tool calls or `max_steps` is reached. Tools are only sent when `config.supports_tools` is set.
- `complete(config, messages, *, system_prompt=None, max_output_tokens=None) -> tuple[str, Usage]`: one call without tools or streaming, for titles, speech preprocessing, the legacy non-streaming endpoints and the smoke test.
- `tools.py`: a registry of async functions with explicit JSON schemas (`get_file_content`, `get_graph_schema`, `search_graph`, `query_graph`, `web_search`). `default_tools()` returns the enabled ones (graph tools with `NEO4J_ENABLED`, web search with `TAVILY_API_KEY`).
- **Request settings** from the `ModelConfig`: `temperature`, `top_p`, `max_output_tokens` and `reasoning_effort` are only sent when set; `extra_body` is merged into the request body as-is.
- **Conversation history** (`backend/services/conversation_history.py`): the newest messages that fit `context_window` (`DEFAULT_CONTEXT_WINDOW`, 32768, for models without one), at most `HISTORY_MAX_MESSAGES`. `history_token_budget(config, system_prompt, tools)` subtracts room for the answer (`max_output_tokens`, else 32000, at most a quarter of the window), 10% of the window for tool results during the run, and the system prompt and tool definitions. Tokens are estimated at 3 characters each. The latest user message is always sent. The context window is therefore also a cost limit: each answer resends the history, up to the whole window.
- **Reasoning shown as steps:** reasoning text becomes a `thought` step titled "Thinking" that grows through `step_delta` events. It arrives as `reasoning_content` (Kimi, DeepSeek, Qwen), `reasoning` (some routers) or Anthropic thinking blocks. The old placeholder steps ("Analyzing request...", "Generating Response") go away.
- **System prompt:** `build_system_prompt(persona_prompt: str | None, tools)` returns the identity paragraph (or the persona prompt in its place), followed by the sections for the enabled tools (file access, knowledge graph).

## Catalog (`backend/catalog/`)

- `resolver.py`:
  - `resolve_model(user, model_id=None, conversation=None) -> ModelConfig`. Order: `model_id`, then the conversation's `model_id`, then the user's `default_model_id`, then the first enabled model by `sort_order`, then `model_from_env()`. Raises `ModelNotAvailable` when nothing is left, and `ModelNotAllowed` when an explicitly requested model is disabled or not available to the user.
  - `resolve_auxiliary_model() -> ModelConfig | None`: the first enabled model with `is_auxiliary`, else `model_from_env()`.
  - `get_model_config(model_id) -> ModelConfig`: no permission check (smoke test, admin test button).
  - `render_persona_prompt(persona_id, values, *, user_name, language) -> str | None`.
- **Visibility:** guests only see and use models and personas with `available_to_guests`. A guest without any guest model gets the environment model, as today. Disabled providers hide their models.
- **API keys:** keys entered in the UI are Fernet-encrypted with `CATALOG_SECRET_KEY`. If that is unset, a key is generated once into `<FILES_DIR>/.catalog_secret` (mode 0600) with a warning in the log. A provider can instead name an environment variable (`api_key_env`); a stored key wins over the variable. Keys are never returned, only `apiKeySource` and `apiKeyMasked` (`sk-…1234`).
- **Admins:** users whose email is in `ADMIN_EMAILS` (and who are not guests). Empty means nobody; the catalog can still be seeded from `MODEL_CATALOG_FILE`.

### Personas

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
| `GET /api/admin/providers` | | `ProviderOut[]` |
| `POST /api/admin/providers` | `ProviderCreate` | `ProviderOut` |
| `PUT /api/admin/providers/{id}` | `ProviderUpdate` | `ProviderOut` |
| `DELETE /api/admin/providers/{id}` | | 204; deletes its models too |
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
| `GET /api/admin/catalog/export?includeKeys=false` | | the catalog file below |
| `POST /api/admin/catalog/import` | the catalog file below | `ImportResult` |

### Changes to existing endpoints

- `GET /api/auth/me`: adds `isAdmin`.
- Conversations (`GET /api/conversations`, `GET /api/conversation/{id}`, `POST /api/conversation/create`, `PATCH /api/conversation/{id}`): accept and return `modelId`, `personaId` and `personaValues` (an object of variable values). `null` means the user's default model and no persona.
- Settings (`GET` / `PUT /api/settings`): add `defaultModelId`.
- Agent messages (message sync and all message responses): add `modelId`, `modelName` and `usage` (`MessageUsage`).
- `POST /api/message/stream-generate`: optional `modelId` to answer with another model than the conversation's.

### Streaming protocol (`/api/message/stream-generate`)

Unchanged events keep their meaning. Additions:

- `message_start`: adds `modelId` (null for the environment model) and `modelName`.
- `step`: if a step with the same `id` already exists, the new one replaces it (the reasoning step is sent once empty at its start and once complete at its end).
- `step_delta` (new): `{"id": "<step id>", "delta": "<text>"}`, append `delta` to that step's content.
- `done`: adds `modelId`, `modelName` and `usage` (`MessageUsage`).

## Catalog file

Used for `MODEL_CATALOG_FILE` seeding and for import and export. JSON with snake_case keys matching the database columns. Import upserts by natural key (providers by `name`, models by `provider` + `display_name`, personas by `name`) and never deletes. Keys are referenced by environment variable; an export only contains `api_key` when `includeKeys=true`.

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
      "default_model": {"provider": "Cortecs", "display_name": "Kimi K3"},
      "available_to_guests": true
    }
  ]
}
```

Every model column from `schema.sql` may appear; left-out columns take their defaults.
