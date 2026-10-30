# Generalization refactor (October 2026)

Handover notes for picking the project back up: what was decided, what was done, what was found along the way and what comes next. Written on 2026-10-30, after the cleanup was merged into `develop` (PR #137).

## Goals and agreed plan

The project started in 2023 as a personal chat app for learning how to build AI systems. From 2024 to 2026 it was reused for university projects and, from October 2025, was rebranded as **Fessi**, a waste disposal assistant for Frankfurt University of Applied Sciences. That left the code Fessi-specific and hard to use as a general chat.

Goals:

- Turn this repository back into a **general LLM chat app** for hobby use. It will run in the homelab, for testing open models (Kimi, DeepSeek, GLM, Qwen, …) and the Anthropic API, for chatting, and for experimenting with vector and graph databases.
- Keep adapted versions (Fessi, Küppelsmühle) as **downstream repositories** that merge this one as `upstream`, the way Ubuntu builds on Debian. Domain-specific branding, prompts, tools and data stay out of upstream; upstream offers configuration points instead.

Agreed order of work:

1. Repository setup and downstream repos (done)
2. Clean up and generalize upstream `develop` (done, PR #137)
3. **Choose model providers and set the app up as a proper chat app (in progress)**
4. Deployment to the homelab
5. Merge `develop` into `main`, then deploy and test in production

The user explicitly wants providers and setup settled before the deployment and before touching `main`.

## Repositories

| Role | GitHub | Visibility | Local path | Starting point |
|---|---|---|---|---|
| Upstream (general) | `Knaeckebrothero/Advanced-LLM-Chat` | public | `~/Repositories/Advanced-LLM-Chat` | – |
| Fessi | `Knaeckebrothero/Fessi` | public | `~/Repositories/Fessi` | upstream `develop` at `e2763d4` |
| Küppelsmühle | `Knaeckebrothero/Kueppelsmuehle-Chat` | private | `~/Repositories/Kueppelsmuehle-Chat` | old upstream `develop` at `ee52e41` |

- Both downstream clones have an `upstream` remote pointing at Advanced-LLM-Chat. Its push URL is set to `DISABLE`, so nothing gets pushed upstream by accident; `git remote set-url --push upstream <url>` undoes that. They also have `checkout.defaultRemote=origin`, because `develop` exists on both remotes.
- **GitHub Actions are disabled** in both downstream repositories until their workflows are adapted. If they were enabled, the gh-pages job would fail without a `DEPLOY_GH_PAGES` secret, and the Docker images are named after the repository.
- To pull upstream changes into a downstream repo: `git fetch upstream && git merge upstream/develop`.
- As of 2026-10-30, Fessi is 5 commits and Küppelsmühle 7 commits behind upstream `develop`. Merging upstream into Fessi will *remove* the waste disposal parts there, because the generalization commits delete them. That merge is where Fessi has to re-add its layer through the new configuration points (see "For downstream projects").
- The Küppelsmühle repo holds a client's system prompt, which is why it is private. It added its own `AGENT_PROFILE` (`waste` / `knowledge`) and `SYSTEM_PROMPT_FILE` settings in `backend/config.py` and `agent.py`, so expect conflicts there when it merges upstream.
- The **barcode scanner** (`feature/barcode-scanner`, product lookup tool) is a Fessi-only feature. It was created upstream by mistake, merged into Fessi `develop` as `58a3ad8`, and deleted from upstream. That branch also carried `multimodal_support_implementation.md` (a vision/audio-on-GPU plan) and `review.md`. Both now exist only in Fessi; the multimodal plan is general and could be copied back into upstream `docs/`.
- `Advanced-LLM-Chat-demo` used to be a git worktree of this repo on `demo/kueppelsmuehle` (15 commits that had never been pushed). The commits now live in the Küppelsmühle repo, and the worktree and local branch were removed.

### Branch policy

**Never delete the legacy branches** (`backup/*`, old feature branches, branches whose remote is gone). They contain the earliest versions of the app, which the user may want to bring back or host one day. Leftovers from this refactor that can be deleted once the user agrees:

- `feature/generalize-chat`, locally and on GitHub. It was merged by rebase, so its commit IDs differ from `develop`'s.
- `feature/graphite-teal-theme`, local only. It points at the same commit as `feature/generalize-chat`.

### GitHub rules and CI

- The ruleset **"Main & develop"** applies to the default branch, `main` and `develop`. It blocks deletion and force pushes, requires linear history, and requires PRs with 2 approvals (`merge` or `rebase` only). It also requires CodeQL and Copilot code review. The ruleset **"Backup-and-Deployment-Protection"** protects `backup-**-**-****` and `gh-pages`.
- As the sole maintainer, the user can't satisfy the approvals, so PRs are merged with the admin bypass when asked: `gh pr merge <n> --rebase --admin`. Rebase keeps the linear history.
- On every push to `develop` and `main`, `docker-build.yml` builds `ghcr.io/knaeckebrothero/advanced-llm-chat-{frontend,backend}`. Images from `develop` are tagged `develop-latest`, `develop` and `sha-<commit>`; images from `main` get `latest`. On pull requests it builds without pushing.
- `deploy-gh-pages.yml` deploys `develop` to https://knaeckebrothero.github.io/Advanced-LLM-Chat/. It uses the `DEPLOY_GH_PAGES` secret and takes its base path from the repository name.
- After the merge of PR #137, both workflows passed on `develop` (`a45a68d`). The backend image takes about 9.5 minutes, the frontend about 2.5.
- `main` is 90 commits behind `develop` and has 10 commits of its own:
  - 2 March 2026 edits to `backend_mockup.py`, a file `develop` replaced in November 2025;
  - a 2024 `LICENSE.txt` edit;
  - 7 PR merge commits.

## What changed in PR #137

Merged on 2026-10-30 by rebase. Commits on `develop`:

| Commit | Change |
|---|---|
| `0fc3bb3` | Move the planning documents and `GitFlow.pdf` into `docs/` |
| `7570f80` | Rename the project back to Advanced LLM Chat and make Neo4j optional |
| `f80f62a` | Remove the university and recycling branding from the frontend |
| `8fc325e` | Rewrite the README for the general project |
| `a45a68d` | Switch to the Graphite & Teal color theme |

### Naming

| Thing | Before | After |
|---|---|---|
| Display name | Fessi / Recycling Bot | Advanced LLM Chat (sidebar: "LLM Chat") |
| npm package, Angular project | `fessi`, `Fessi` | `advanced-llm-chat` |
| Build output | `dist/fessi/browser` | `dist/advanced-llm-chat/browser` |
| Postgres database / user / dev password | `fessi_chat` / `fessi` / `fessi_dev_password` | `llm_chat` / `llm_chat` / `llm_chat_dev_password` |
| Neo4j dev password | `fessi_neo4j_dev` | `llm_chat_neo4j_dev` |
| Containers | `fessi-*` | `llm-chat-*` (postgres, neo4j, db-init, frontend, backend) |
| Docker `PROJECT_FOLDER` | `fessi` | `advanced-llm-chat` |
| gh-pages base path | `/Fessi/` | `/${{ github.event.repository.name }}/` (works unchanged in forks) |

### Backend

- **Agent** (`backend/services/agent.py`): `FessiAgent` is now `ChatAgent` and `create_fessi_agent()` is now `create_agent()`. The German waste disposal prompt was replaced by a general English one ("respond in the user's language") that keeps the file access instructions. The `GRAPH_PROMPT` section is only added when Neo4j is enabled.
- **Neo4j is optional and off by default.** The settings in `backend/config.py`:
  - `NEO4J_ENABLED` (default `false`): registers the graph tools and adds the graph prompt section.
  - `NEO4J_SEED_FILE`: optional Cypher file used to seed an empty graph; relative paths are resolved from the repo root.
  - `NEO4J_MAX_RESULTS` (default `25`): the maximum number of rows a graph tool returns.
  - The waste-specific `NEO4J_REQUIRE_DISPOSAL_METHOD` was removed.
- **Graph tools** (`backend/services/tools/neo4j_tools.py`): the five waste tools were replaced by three read-only tools that work with any schema.
  - `get_graph_schema`: node and relationship counts, the properties per label (via `db.schema.nodeTypeProperties()`) and the relationship patterns.
  - `search_graph`: case-insensitive text search over all string properties and string lists. It uses `IS :: STRING` / `IS :: LIST<STRING NOT NULL>`, which needs Neo4j 5.9 or later (compose uses 5.15).
  - `query_graph`: runs agent-written Cypher.
  - Results are capped at `NEO4J_MAX_RESULTS` with a `truncated` flag. Strings over 2000 characters and lists over 50 items (for example embeddings) are shortened, and Neo4j temporal types are turned into strings.
  - The agent shows the tools as "Inspecting / Searching / Querying Knowledge Graph", translated in `src/assets/i18n/{de,en}.json`.
- **`Neo4jDatabase.query_read()`** (`backend/database/neo4j_db.py`) runs queries with `session.execute_read`, so Neo4j rejects any write (`Neo.ClientError.Statement.AccessMode`). The waste-specific query methods were removed.
- **`neo4j_init.py`** seeds from `--seed-file` or `NEO4J_SEED_FILE` instead of the bundled `neo4j_seed.cypher` (deleted; Fessi still has it). The check for waste labels was replaced by a summary of what the graph contains.
- **`app_init.py`** skips Neo4j unless `NEO4J_ENABLED=true` and passes the seed file through.
- Removed the unused duplicate `backend/services/neo4j_service.py`.
- The seed SQL welcome message now reads "Welcome to Advanced LLM Chat! How can I help you today?".

### Docker and CI

- The `neo4j` service is behind the compose profile `graph`. `db-init` depends on it with `required: false`, and the backend and `db-init` receive `NEO4J_ENABLED`. To use the graph in Docker, set `NEO4J_ENABLED=true` and `COMPOSE_PROFILES=graph`, or use `docker compose --profile graph up`.
- The same change exists in three places: `docker/docker-compose.yml`, `docker/docker-compose.prod.yml`, and the compose file that `docker-build.yml` writes as a heredoc.

### Frontend

- Removed the Frankfurt UAS logo from the chat view. The `isDarkMode` code in `chat-ui.component.ts` was kept on purpose, so Fessi can put its logo back easily.
- The sidebar text changed from "Recycling Bot" to "LLM Chat", and the recycling symbol was cut out of the robot SVGs (`robo_light_modev2.svg`, `robot_dark_new.svg`).
- The `/metrics` page's "Recycling Bot kann Fehler machen…" is now a translated "AI can make mistakes. Check important information."
- **Original icons restored.** Rachid swapped the original cyborg-portrait icons for a recycling robot in `c46586a` (2025-10-31); all 112 Android, iOS and Windows 11 icons were restored from `c46586a^`. The original favicon was only the default Angular logo, so a new favicon was generated from the cyborg icon.
- Deleted 9 unused university and recycling assets (`fra_*` logos, `logo-recyclingbot.png`, unused robot variants).

### Theme: Graphite & Teal

The user chose this palette from a theme lab (https://claude.ai/artifact/LdJwaDCduDhSP4e7coseNd). The lab compares Classic (the original 2023–2025 palette: Abbey `#474B51`, Bali Hai `#8E9BAC`, Edward `#99A5A6`, Cloud `#C9C6C1`, Charcoal `#343A40`), Violet (the December 2025 theme), Graphite & Teal, Ember and a custom accent.

| Token | Light | Dark |
|---|---|---|
| background | `#eef3f3` | `#111518` |
| surface | `#ffffff` | `#181e21` |
| text | `#162024` | `#e3e8ea` |
| text-secondary | `#566a70` | `#8fa0a7` |
| primary | `#0e7468` | `#2cb5a5` |
| secondary | `#127d70` | `#5ccfc1` |
| primary-contrast | `#ffffff` | `#062421` (dark text on the light teal) |
| border | `#d3dede` | `#263035` |
| link | `#0e6e63` | `#6fd6ca` |
| code-bg | `#f2f6f6` | `#1d2528` |
| avatars | `#227a86→#17806f`, `#0e7468→#178f80` | same as light (white icons stay readable) |

- Every key text/background pair passes WCAG AA in both modes. Text is about 14:1, and buttons, links and muted text are at least 5:1.
- The Angular Material palettes now take their text color from the theme's `primary-contrast` (`_themes.scss`). Before, white or black was hard-coded, which would have put white on light teal in dark mode.
- The thought-step icon uses the assistant avatar gradient instead of a hard-coded violet. The login skip button uses `primary-contrast` instead of white.
- The browser `theme-color` has separate light and dark values. The PWA manifest uses `theme_color #0E7468` and `background_color #111518`.
- The purple and blue triangle backgrounds were removed (`'background-image': none`).
- Colors live in `src/styles/themes/_theme-config.scss` and are applied through the mixin in `_themes.scss` on `.theme-light` / `.theme-dark`.

### Documentation

- The README was rewritten for the general project. It covers features, Docker and local setup, configuration, the knowledge graph, architecture, downstream projects, Git Flow and acknowledgments (credit to Rachid Yagubi and TillCa for the 2025 UI redesign). The license is **CC BY 4.0**; the old README wrongly said MIT.
- `CLAUDE.md` describes the general project and the rule to keep domain-specific code out of upstream.
- In `docker/README.md` only the names were updated; the rest is still outdated.

## Local development setup

Status on 2026-10-30. Everything runs from `develop`.

1. `.venv` (Python 3.13) had been missing `langchain-community` and `tavily-python`; `pip install -r requirements.txt` fixed that and `pip check` is clean.
2. `.env`: only `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD` were changed, to the `llm_chat` values. The old file was backed up in the session scratchpad, which is temporary; its only differences were the `fessi` values. `.env` uses `LLM_PROVIDER=openai` with `OPENAI_MODEL=gpt-5.2-2025-12-11` and a working OpenAI key.
3. Postgres: `cd docker && docker compose up -d postgres` starts the container `llm-chat-postgres` on port 5432.
4. `python backend/app_init.py --seed` creates the tables, test users and a welcome conversation, and skips Neo4j because it is disabled. Test users: `test@example.com`, `admin@example.com`, `demo@example.com`, via mock login.
5. Backend: `python start_backend.py --reload` → https://localhost:8443 (API docs at `/api/docs`).
6. Frontend: `npm start` → https://localhost:4200.
7. In a browser, accept the certificate at https://localhost:8443 first, then open :4200. The two use different self-signed certificates (see "Known issues").

Checks that passed:

- **End to end:** API calls (guest login, create a conversation, send a message, stream the agent) and a real browser run, with the reply streamed back from `gpt-5.2`.
- **Graph tools against a throwaway Neo4j 5.15:** seeding from a file, schema, text search in strings and lists, value shortening, truncation flag, and `CREATE` / `DETACH DELETE` rejected with the counts unchanged.
- **Builds and tests:** `tsc` and the production build pass. Unit tests have 58 of 88 failing, the same 58 as on `develop` before the change, so nothing regressed.

## Known issues and findings (backlog)

All of these were already there before the refactor unless noted.

- **Unit tests:** 58 of 88 fail, mostly `NullInjectorError: No provider for HttpClient` in component specs. `projects/ngx-agent-chat/tsconfig.spec.json` also errors with "No inputs were found".
- **Session expiring while the app is open:** the next request gets a 401 and `AuthInterceptor` sends the user to the login page; a guest could get a new guest session instead. (At startup this is fixed: a missing or expired session starts a guest session in the chat.)
- **Dev certificates:** they are regenerated on *every* backend start, by `start_backend.py` and again by importing `backend/main.py`. The backend and the Angular dev server therefore use different certificates, and trusting `devcerts/ca.pem` never lasts. They should only be generated when missing.
- **Deprecated dependency:** `langchain-community` is being sunset, and the Tavily web search tool uses it. Move to `langchain-tavily`.
- **Old model default:** the Anthropic default is still `claude-3-haiku-20240307` (`llm_provider.py`, plus the CI-generated `.env.example`). This will be handled with the model work.
- `schema.sql` starts with a comment-only statement, which logs a harmless "can't execute an empty query" warning at startup.
- `docker/README.md` still describes SQLite and a Replicate-only backend.
- **Duplicated compose files:** dev, prod and the CI heredoc are three copies to keep in sync. The `version: '3.8'` field is obsolete.
- **Bundle size:** the production bundle is 1.29 MB, over the 1 MB budget (a warning, not an error).
- **Dead code:** `status-bar` component (not rendered, uses old `$color-*` variables from `_variables.scss`), the "Placeholder Component" nav item, and the `/metrics` page that only shows the disclaimer.
- **UI nits seen in screenshots:** a horizontal scrollbar at the bottom of the sidebar, and "(2 steps)" wrapping in the thought-process header.
- `projects/ngx-agent-chat` is an empty library scaffold from March 2026; to be decided during the chat refactor.
- The provider research (report and the five sets of notes) lives in `docs/research/`.

## Ideas discussed for later

- **Model setup (next):** today one model is configured per deployment through environment variables (`LLM_PROVIDER`, `OPENAI_BASE_URL`, `OPENAI_MODEL`), and switching models means a restart. The planned direction:
  - a **list of providers and models** in configuration;
  - a **model picker per conversation**;
  - storing which model wrote each message, so models can be compared.
  - Any OpenAI-compatible endpoint already works through `OPENAI_BASE_URL`, but only one at a time.
- **Knowledge storage:** a setting for a graph database, a vector database or both. The graph tools could become memory or knowledge-base tools, which would need write tools. pgvector code exists in the Küppelsmühle repo (`backend/knowledge/`).
- **Themes:** separate palette from mode (palette × light/dark/auto), maybe a custom accent color. Check how much CSS each Angular Material theme adds before adding many palettes.
- **Custom background image:**
  - Options for theme default, none, or your own image, with dim and blur sliders.
  - Semi-transparent bubbles and input field when an image is set.
  - Stored through the existing file API, with the file ID in user settings so it syncs. Shrink large images on the server; guests keep it in the browser only.
- **Other appearance settings:** font size, chat column width.
- **Configuration point for downstream:** a `SYSTEM_PROMPT_FILE` setting (Küppelsmühle already has one) would let Fessi supply its prompt without code changes.

## For downstream projects (Fessi)

When Fessi merges upstream, it can re-add its layer through configuration instead of code where possible:

- **Waste graph data:** keep `neo4j_seed.cypher` in the Fessi repo and set `NEO4J_ENABLED=true` plus `NEO4J_SEED_FILE`.
- **Waste-specific tools:** add them next to the generic graph tools, or rely on `query_graph`.
- **Prompt:** Fessi's prompt currently needs a code change in `agent.py`, until a `SYSTEM_PROMPT_FILE` setting exists.
- **Branding:** the university logo and Fessi icons; the hook for the logo's dark-mode variant (`isDarkMode`) is still in place.

## Current task: choosing model providers

The user wants inference providers for open models (Kimi, DeepSeek, GLM, Qwen, gpt-oss, Mistral, …), with a strong preference for **European companies and EU data centers with good privacy**: GDPR, a DPA, no training on prompts, little or no retention. The user would rather avoid aggregators like OpenRouter, whose routing makes privacy unclear. The user also has Anthropic API credits, and Anthropic is already supported natively.

Hard technical requirement: an OpenAI-compatible chat completions API with **streaming and tool calling**, because the agent uses LangChain `ChatOpenAI` with `bind_tools`. Vision is a plus.

A research run on 2026-10-30 covers five areas. The notes go to `docs/research/eu_inference_providers_notes/` and the final report to `docs/research/eu_inference_providers_for_open_models.md`.

1. European clouds: Scaleway, OVHcloud, IONOS, STACKIT, Open Telekom Cloud, Infomaniak, …
2. European AI inference companies and EU routers: Nebius, Mistral, Regolo, Berget AI, Cortecs, Nscale, …
3. Big clouds with EU regions (Bedrock, Azure, Vertex) and US inference specialists (Together, Fireworks, DeepInfra, Groq, Cerebras, …) as a fallback
4. The model makers' own APIs (Moonshot, DeepSeek, Z.ai, Alibaba, MiniMax) under GDPR, plus OpenRouter's privacy controls
5. Which open models are current, including the actual name of what the user called "Kimi K3.1", and what the homelab could self-host

### Research results (report: `docs/research/eu_inference_providers_for_open_models.md`)

Recommended setup. Every provider here is reached through the existing OpenAI-compatible path.

| Role | Provider | Base URL | Start with |
|---|---|---|---|
| Primary | **Scaleway Generative APIs** (Paris; zero retention by default; states it is not subject to the CLOUD Act; first 1M tokens free; parallel tool calls) | `https://api.scaleway.ai/v1` | `deepseek-v4.1-flash` (€0.60/€1.80), `glm-5.3` (€1.80/€5.50, text only), `qwen3.8-27b`, `qwen3.6-35b-a3b` |
| Kimi | **Berget AI** (Stockholm; DPA of 22 Oct 2026: no stored prompts, metadata-only logs; €5 trial, then a €25/month plan whose credits stay valid 12 months) | `https://api.berget.ai/v1` | `moonshotai/Kimi-K3` (€3/€15), upgrading to `Kimi-K3.1-Pro` on 6 Nov |
| Everything else | **Cortecs** router (Vienna) with Sovereign Cloud and ZDR on, **Nebius excluded** | `https://api.cortecs.ai/v1` | MiniMax M3.1 Flash, Mistral Large 4, Qwen3.8-2.4T |
| Baseline (optional) | OVHcloud AI Endpoints | `https://oai.endpoints.kepler.ai.cloud.ovh.net/v1` | gpt-oss-120b (€0.08/€0.40). Scaleway's gpt-oss can't use tools through Chat Completions. |
| Local | `llama-server --jinja` (try Vulkan on RDNA4) or AMD's `rocm/vllm` image | homelab | Qwen3.6-35B-A3B, Qwen3.8-27B, Gemma 4 (fit a 24 GB card) |

**Avoid:**
- The DeepSeek, Moonshot and MiniMax first-party APIs. DeepSeek stores data in China and trains on it; Moonshot may use content to improve its services.
- Nebius without ZDR, and Together with its default settings (it stores prompts).
- Bedrock `global.*` profiles, and Vertex or Azure for open models.
- OpenRouter: EU processing needs its Business plan, and it puts a US company in the data path.
- Mistral free-tier keys.
- IONOS (commercial use only) and T-Systems (€1,000/month minimum).
- Llama 4: its license reportedly excludes EU users.

**Models:** "Kimi K3.1" is **Kimi K3.1 Pro**. It has been on Moonshot's own API only since 23 Oct, and its weights are due by 4 Nov. Kimi K3 is the newest open Kimi. The other current open models to test:

- DeepSeek V4.1 Flash 1017 (MIT)
- GLM-5.3 and GLM-5.3-Flash
- Qwen3.8-27B
- MiniMax M3.1 Flash
- Mistral Large 4 (weights since 29 Oct)
- gpt-oss-120b/20b
- Gemma 4

Estimated hobby cost (5M input + 1M output tokens a month): about €5 (DeepSeek), €15 (GLM-5.3), €30 (Kimi K3).

**App changes needed before testing models seriously:**

- **Keep the reasoning text.** `ChatOpenAI` (langchain-openai 1.1.12) drops `reasoning_content`. Kimi K3/K3.1, and Qwen3.8 with `preserve_thinking`, need it sent back unchanged during tool loops. Fix: a small `ChatOpenAI` subclass that keeps `reasoning_content` in `additional_kwargs` and writes it back on outgoing assistant messages. That would also let the UI show the model's thinking.
- **Per-model reasoning effort.** The `Reasoning: <level>` prompt prefix only works for gpt-oss, but every custom base URL counts as "openai". Kimi defaults to `reasoning_effort: max`, which drives up cost. Test which `reasoning_effort` values each provider accepts, and whether `temperature=0` works with thinking models.
- **Separate base URLs for voice.** `WHISPER_BASE_URL` and `TTS_BASE_URL` default to `OPENAI_BASE_URL`, so switching to an EU host redirects voice too. Point them somewhere else, or use `USE_LOCAL_WHISPER=true`.
- **Vision model.** GLM-5.3 is text-only, so set `VISION_MODEL` to a vision-capable model such as `qwen3.8-27b`.
- **Test before trusting.** Test streaming with tools bound per provider (only T-Systems documents streamed tool calls). Treat model IDs as configuration refreshed from `/v1/models`, because catalogs change weekly. The report closes with a table of 10 smoke tests.

**Follow-up decisions (2026-10-30):** the user set the rule "usability first, privacy preferred". EU providers come first. If a model isn't listed there, or is only available with a subscription (e.g. Berget's €25/month plan), fall back to OpenRouter or US companies. Even the vendor's own API is acceptable for test-only use.

Models will come from a **database catalog**: providers with an API key and a privacy tier, models with their settings, personas. Users pick from it with a **model picker** that shows the privacy tier. This brings back the 2024 JSON config idea (commit `307b612`).

The fallback matrix, catalog schema, the runtime design and the order of work are in **`docs/model_provider_strategy.md`**.

LangChain was checked. Even the newest `langchain-openai` (1.7.3) does not keep `reasoning_content` by design, and `ChatDeepSeek` only reads it. The proposal is to replace LangChain/LangGraph with a thin layer over the `openai` and `anthropic` SDKs (`backend/llm/`).

Next steps (see the strategy doc for details):

1. Pick providers (done: Scaleway, Cortecs, OpenRouter with ZDR, Anthropic, OpenAI, Moonshot for K3.1 Pro only, homelab later).
2. Design the provider and model configuration and the model picker.
3. Set up and test.
4. Deploy to the homelab.
5. Merge into `main`.

Homelab context: the Kubernetes setup lives in `~/Repositories/HomeLab` (GitHub `Kubernetes-Cluster-Project`). The machine already runs an AMD ROCm GPU for voice models, and a local k3d cluster and registry are in use for other projects.
