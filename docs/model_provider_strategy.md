# Model providers and model catalog

Strategy for where Advanced LLM Chat gets its models from, and how models are configured and picked in the app. Written on 2026-10-30. It is based on the provider research in `docs/research/eu_inference_providers_for_open_models.md`; prices are from that date and change often.

## Principles

1. **Usability first, privacy preferred.** The app is for testing models and chatting. If a model is only reasonably available from a non-EU provider, or only through a subscription, use that provider rather than going without the model.
2. **Privacy is shown, not enforced.** Every provider gets a privacy tier, and the model picker shows it. You then know, for example, not to share personal information with a model added through the DeepSeek API.
3. **Prefer EU, then trusted non-EU, then the vendor's own API.** A model is added through the best source that is easy to use. That means pay-as-you-go, no monthly plans and no sales contact.
4. **Models are data, not code.** Providers and models live in a database catalog that can be edited in the app and imported or exported as JSON. Nothing is hard-coded or tied to environment variables.

## Privacy tiers

| Tier | Meaning | Providers |
|---|---|---|
| `local` | Runs in the homelab; data never leaves | llama.cpp / vLLM on the homelab GPU |
| `eu` | EU company, EU processing, no training, zero or short retention | Scaleway, Cortecs (with Sovereign Cloud + ZDR), OVHcloud, Berget AI, Mistral (paid with the training opt-out) |
| `trusted` | Non-EU (mostly US) company, no training, retention zero or limited to abuse monitoring when configured | OpenRouter (with ZDR and `data_collection: deny`), DeepInfra, Fireworks, Cerebras, Groq, Anthropic API, OpenAI API |
| `untrusted` | May keep data long-term or train on it, or sits in a jurisdiction where GDPR rights are hard to enforce | DeepSeek, Moonshot (Kimi), Z.ai and MiniMax first-party APIs; Together and OpenRouter on default settings |

- **In the UI:** the picker shows the tier as a badge. Starting a chat with an `untrusted` model shows a short notice: "This provider may store or train on your messages. Don't share personal information."
- **Assigning tiers:** the tier is set per provider when it is added, so the picker never has to guess. A model can override it, for example an OpenRouter model pinned to EU hosts.
- **Re-check:** the `trusted` tier depends on account settings (ZDR switches, opt-outs), so check them when adding the provider.

## Fallback matrix

For each model, use the first column that works. Fall back when the model isn't listed, or when getting it would need a subscription or sales contact.

| Model | 1. EU, pay-as-you-go | 2. EU router | 3. Trusted non-EU | 4. Vendor API (test-only, `untrusted`) |
|---|---|---|---|---|
| Kimi K3.1 Pro | none yet (weights due 4 Nov) | Cortecs, once EU hosts serve it | OpenRouter / DeepInfra / Fireworks, once weights are out | **Moonshot API**, the only source today ($2 / $10) |
| Kimi K3 | none without a plan (Berget needs €25/month) | **Cortecs** (≈€2.69 / €13.46) | DeepInfra ($2.85 / $14.25), OpenRouter | Moonshot API |
| DeepSeek V4.1 Flash | **Scaleway** (€0.60 / €1.80) | Cortecs | DeepInfra, OpenRouter | not DeepSeek's API (data in China, trains on it) |
| GLM-5.3 | **Scaleway** (€1.80 / €5.50; text only) | Cortecs, Mistral | DeepInfra, OpenRouter | Z.ai API ($1.40 / $4.40) |
| GLM-5.3-Flash | (Berget needs a plan) | **Cortecs** | OpenRouter, Fireworks | Z.ai API |
| Qwen3.8-27B / 3.6-35B-A3B | **Homelab** (`local`), then Scaleway or OVH | Cortecs | DeepInfra | – |
| MiniMax M3.1 Flash | – | **Cortecs** (via TensorX) | OpenRouter | MiniMax API |
| Mistral Large 4 | **Mistral API** (paid, training opt-out on) | Cortecs | OpenRouter | (Mistral is the vendor) |
| gpt-oss-120b / 20b | **OVHcloud** (€0.08 / €0.40). Not Scaleway: no tool calls there. | Cortecs | Cerebras or Groq (very fast), DeepInfra | – |
| Gemma 4 | **Homelab**, then Scaleway | Cortecs | DeepInfra, OpenRouter | – |
| Claude | – | – | **Anthropic API** (existing credits; native SDK) | – |
| GPT-5.x | – | – | **OpenAI API** (existing key) | – |

Resulting starting set of provider accounts:

- **Scaleway**: DeepSeek, GLM, Qwen (`eu`, 1M free tokens).
- **Cortecs**: Kimi K3, MiniMax and anything else EU-hosted. Turn on Sovereign Cloud and ZDR, and exclude Nebius (`eu`).
- **OpenRouter**: the general fallback. Set ZDR and `data_collection: deny` at account level (`trusted`). It covers almost every model with one key, at a fee of about 5.5% on credits.
- **Anthropic** and **OpenAI**: direct, with existing credits (`trusted`).
- **Moonshot**: only for Kimi K3.1 Pro until EU or trusted hosts serve it (`untrusted`).
- **Homelab**: added later (`local`).

Not used:

- **Berget:** monthly plan.
- **IONOS:** commercial use only.
- **T-Systems:** €1,000/month minimum.
- **Nebius without ZDR, and Together on default settings:** both keep prompts.
- **DeepSeek's own API.**
- **Llama 4:** its license reportedly excludes EU users.

## The model catalog

This is the 2024 idea brought back. In March 2024 (`307b612`) the frontend-only app imported a JSON file with `settings` (`name`, `apiKey`, `model`, `temperature`, `top_p`, penalties), `agents` (`role` + `prompt`, i.e. personas) and an optional `conversation`. The catalog keeps that split and stores it in PostgreSQL.

### Tables (sketch; match `schema.sql` conventions when implementing)

```sql
-- One row per API account
CREATE TABLE llm_providers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,                     -- "Scaleway", "OpenRouter (ZDR)"
    kind TEXT NOT NULL,                     -- 'openai_compatible' | 'anthropic'
    base_url TEXT,                          -- https://api.scaleway.ai/v1
    api_key_encrypted TEXT,                 -- entered in the UI, encrypted at rest
    api_key_env TEXT,                       -- or: name of an env var holding the key
    privacy_tier TEXT NOT NULL,             -- 'local' | 'eu' | 'trusted' | 'untrusted'
    notes TEXT,                             -- jurisdiction, retention, account settings
    default_headers JSONB,                  -- e.g. OpenRouter's HTTP-Referer
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- One row per model offered in the picker
CREATE TABLE llm_models (
    id SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL REFERENCES llm_providers(id),
    display_name TEXT NOT NULL,             -- "GLM-5.3 (Scaleway)"
    model_id TEXT NOT NULL,                 -- API id: "glm-5.3"
    -- capabilities
    supports_tools BOOLEAN DEFAULT TRUE,
    supports_vision BOOLEAN DEFAULT FALSE,
    reasoning TEXT DEFAULT 'none',          -- 'none' | 'optional' | 'always'
    reasoning_passback BOOLEAN DEFAULT FALSE, -- send reasoning_content back in tool loops (Kimi, Qwen preserve_thinking)
    context_window INTEGER,
    max_output_tokens INTEGER,
    -- default request settings (what the 2024 "settings" held)
    temperature REAL,
    top_p REAL,
    reasoning_effort TEXT,                  -- passed as the provider expects; NULL = provider default
    extra_body JSONB,                       -- provider-specific, e.g. {"provider": {"zdr": true, "only": ["..."]}}
    -- bookkeeping
    privacy_tier TEXT,                      -- NULL = inherit from the provider
    input_price_per_mtok NUMERIC,           -- optional, for cost display
    output_price_per_mtok NUMERIC,
    available_to_guests BOOLEAN DEFAULT FALSE,
    enabled BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0
);

-- The 2024 "agents": a named system prompt with fill-in variables
CREATE TABLE personas (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,                     -- "Pirate"
    description TEXT,
    system_prompt TEXT NOT NULL,            -- "Answer like a {{style}}. Today is {{date}}."
    variables JSONB,                        -- [{"name": "style", "label": "Style", "default": "pirate"}]
    default_model_id INTEGER REFERENCES llm_models(id),
    available_to_guests BOOLEAN DEFAULT FALSE
);
```

Persona variables are filled in when a persona is picked for a conversation; the values are stored with the conversation. Built-in variables need no input: `{{date}}`, `{{user_name}}` and `{{language}}` (the UI language). The rendered persona prompt is put in front of the general system prompt, so the file access and graph instructions stay.

Plus:

- `conversations.model_id` and `conversations.persona_id`: the current selection, which can be switched mid-conversation.
- On each assistant message, the model that wrote it (`model_id` and a copy of the display name) and its token usage, so answers can be compared and their cost shown.

### Behavior

- **API keys:**
  - Keys entered in the UI are encrypted with a server secret, for example Fernet with a `CATALOG_SECRET_KEY` environment variable. They are never sent back to the frontend; it only sees `sk-…1234`.
  - For deployments, a provider can instead name an environment variable (`api_key_env: SCALEWAY_API_KEY`), so keys live in Kubernetes secrets.
- **Catalog file:**
  - `app_init` can seed the catalog from a JSON/YAML file (`MODEL_CATALOG_FILE`) that has `providers`, `models` and `personas`, with keys referenced by env var.
  - The same format is used for import and export in the settings page, like the 2024 JSON config. Exports leave keys out unless asked.
  - A fresh homelab deployment comes up already configured.
- **"Fetch models":** a button per provider calls `GET /v1/models` and offers the IDs as a pick list. EU catalogs change weekly, so model IDs are never typed from memory.
- **Fallback when the catalog is empty:** the backend creates one model from the current `OPENAI_*` / `ANTHROPIC_*` environment variables, so existing setups keep working.
- **Who manages it:** only admins can add providers, keys and models. There are no roles today, so start with an `ADMIN_EMAILS` environment variable. Guests only see models marked `available_to_guests`, to protect paid credits.

### Model picker

- **Placement:** a dropdown in the chat view. Models are grouped by provider and show the privacy badge plus small capability icons (tools, vision, thinking).
- **Selection:** it is stored per conversation. New conversations use the user's default model, saved in user settings.
- **Persona:** an optional persona dropdown next to it, which supplies the system prompt.
- **Each assistant message shows which model wrote it** (and optionally its tokens and cost), so models can be compared in one conversation.

## Runtime: replace LangChain with a thin layer of our own

**Findings, checked on 2026-10-30:**

- The installed `langchain-openai` is 1.1.6 and the newest is 1.7.3. Both state in the source that `ChatOpenAI` follows OpenAI's own API only, and that `reasoning_content` and `reasoning_details` are "**not** extracted or preserved". They point to provider packages instead.
- The provider package `ChatDeepSeek` (langchain-deepseek 1.1.1) *reads* `reasoning_content` from responses and streams. It does *not* send it back on assistant messages, which is what Kimi K3/K3.1 (and Qwen with `preserve_thinking`) require during tool loops.
- So no LangChain version handles this for generic OpenAI-compatible providers. Each new model family would need its own workaround.
- The official `openai` Python SDK (`AsyncOpenAI`) keeps unknown fields: `reasoning_content` arrives in `message.model_extra` and in stream-chunk deltas, and extra keys on outgoing messages are sent as-is. Every provider in the matrix except Anthropic speaks this API.
- LangChain usage in the backend is small: 8 files.
  - The agent loop: LangGraph `StateGraph` + `ToolNode`.
  - The `@tool` decorator on three tool modules.
  - Message classes in the history builder.
  - `get_llm()` for the title generator and the TTS preprocessor.
  - `langchain-community`, which the web search tool uses, is being sunset.

**Decision (proposed): drop LangChain and LangGraph** in favor of a small `backend/llm/` package.

- `client.py`: builds an `AsyncOpenAI` client (or an Anthropic client) from a catalog row, applying `base_url`, the key, headers, `reasoning_effort` and `extra_body`.
- `agent_loop.py`, about 150 lines: stream a completion, collect text, reasoning and tool-call deltas, run the requested tools, then append the assistant message with `reasoning_content` when `reasoning_passback` is set (and Anthropic thinking blocks for Claude). Repeat until there are no tool calls or a step limit is reached.
  - It emits the same SSE events as today (`message_start`, `step`, `token`, `done`, `error`), so the frontend doesn't change.
  - The model's thinking becomes visible as `step` events.
- `tools.py`: a small registry of plain async functions with explicit JSON schemas. It covers the file, graph and web search tools; web search calls the Tavily API directly.
- Usage tokens from each response are stored per message.

The cheaper alternative is a roughly 50-line `BaseChatOpenAI` subclass that copies `reasoning_content` in and out. It would keep LangChain but keep fighting its OpenAI-only design with every new model.

## Smoke tests per provider and model

A small backend command, e.g. `python -m backend.llm.smoke_test --model <catalog id>`, should check these. Results can be stored as notes on the model row.

1. Streaming with tools bound: are tool calls assembled correctly from the chunks?
2. A three-step tool chain with and without passing reasoning back (decides `reasoning_passback`).
3. Where the thinking text arrives: a `reasoning_content` field, a `reasoning` field, or `<think>` tags.
4. Which `reasoning_effort` values are accepted, and whether `temperature` is accepted on thinking models.
5. Image input through `image_url`, for models marked vision.

## Before deploying to the homelab

- **Authentication:** login is a mock login by email with no password, so anyone who can reach the app can log in as any user. With API keys and paid models in the catalog, the deployment needs real authentication: the homelab's Keycloak (OIDC), as decided. Until then the app has to sit behind an authenticating proxy or VPN, with the `ADMIN_EMAILS` admin check.
- **Voice settings:** `WHISPER_BASE_URL` and `TTS_BASE_URL` currently default to `OPENAI_BASE_URL`. With a catalog, voice should get its own setting (or a catalog entry), so switching chat models doesn't redirect speech.
- **Vision helper:** `VISION_MODEL` should become a catalog reference, for example Qwen3.8-27B on Scaleway, because GLM-5.3 is text-only.

## Order of work

1. Replace LangChain with `backend/llm/` and keep the SSE protocol; the environment-variable model still works. Test against the current OpenAI setup.
2. Catalog tables, admin API, encrypted keys, catalog file seeding, the `/v1/models` fetch, and the smoke test command.
3. Frontend: catalog management in settings (providers, models, personas, JSON import and export), the model picker with privacy badges, and showing per-message model, tokens and cost.
4. Open the accounts (Scaleway, Cortecs, OpenRouter with ZDR, Moonshot for K3.1 Pro), add the models and run the smoke tests.
5. Authentication and admin hardening, then the homelab deployment, then merge into `main`.

## Decisions (2026-10-30)

1. **Drop LangChain and LangGraph completely**, and build the `backend/llm/` layer described above.
2. **Personas ship in the first version**: name, system prompt with fill-in variables, optional default model.
3. **Guests:** an `available_to_guests` flag on models (and personas) decides what guests can use. No other guest rules for now.
4. **Authentication:** long term, use **Keycloak** (OIDC). The homelab already runs a Keycloak instance the user can log in with, and Keycloak roles would also decide who is admin. How much user management the app has today, and how to integrate Keycloak, will be discussed separately.
   - What exists today: a `users` table with `id`, `email`, `name` and `created_at`, plus sessions, guest usage, the mock login (`/api/auth/mock-login`, email only), the guest login, refresh, logout and `/me`.
   - Until Keycloak is in, catalog management is limited to the emails in `ADMIN_EMAILS`.
