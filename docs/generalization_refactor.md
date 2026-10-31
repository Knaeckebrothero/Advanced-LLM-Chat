# Generalization refactor (October 2026)

Handover notes for picking the project back up: what was decided, what was done, what was found along the way and what comes next. Written on 2026-10-30, after the cleanup was merged into `develop` (PR #137), updated the same evening after the model catalog work, and on 2026-10-31 after the first release and the homelab deployment (see "Status" below; it is the place to start).

## Goals and agreed plan

The project started in 2023 as a personal chat app for learning how to build AI systems. From 2024 to 2026 it was reused for university projects and, from October 2025, was rebranded as **Fessi**, a waste disposal assistant for Frankfurt University of Applied Sciences. That left the code Fessi-specific and hard to use as a general chat.

Goals:

- Turn this repository back into a **general LLM chat app** for hobby use. It will run in the homelab, for testing open models (Kimi, DeepSeek, GLM, Qwen, …) and the Anthropic API, for chatting, and for experimenting with vector and graph databases.
- Keep adapted versions (Fessi, Küppelsmühle) as **downstream repositories** that merge this one as `upstream`, the way Ubuntu builds on Debian. Domain-specific branding, prompts, tools and data stay out of upstream; upstream offers configuration points instead.

Agreed order of work:

1. Repository setup and downstream repos (done)
2. Clean up and generalize upstream `develop` (done, PR #137)
3. Choose model providers and set the app up as a proper chat app (done on 2026-10-30, see "Status")
4. Deployment to the homelab (done on 2026-10-30 with the Helm chart, see "Status")
5. Merge `develop` into `main`, then deploy and test in production (done: release 0.1.175)

The user explicitly wants providers and setup settled before the deployment and before touching `main`.

## Status on 2026-10-31

Everything up to `0a55d68` is pushed to `develop` (directly, with the admin bypass) and released as **0.1.175** (`main` at `7492ce8`, PR #138), which runs in the homelab. The commits after `0a55d68` are **committed locally and not pushed yet**; the user asked to hold the push.

### Commits since PR #137

| Commit | What |
|---|---|
| `589e7b2`…`b340018` (12 commits) | New LLM runtime on the `openai`/`anthropic` SDKs (LangChain, LangGraph and Replicate removed), the model catalog (providers, models, personas) with admin API, the model picker, and the model and token usage stored per message |
| `1043e47` | Chat background setting (none, Aurora, Sunset, own image kept in the browser; dim and blur) and settings loaded after login |
| `7523e84` | History fills the model's context window instead of the last 20 messages; reasoning effort per model |
| `2359817` | Agents page (`/agents`, admins only) replaces the placeholder; provider keys only from env vars; providers read-only and defined by `catalog/models.json`; seeding never overwrites edits; agents (personas) get a tool selection |
| `0f60505` | One user per guest login and no guest exception in the ownership check; guests rate-limited by the connection's IP (no more api.ipify.org) |
| `cd0982f` | Roboto, Inter and Material Icons bundled from npm instead of loaded from Google |
| `f37eb3c` | New Chat works from the Agents page; long user names are cut off in the sidebar |
| `84a7777` | Uploaded files belong to their uploader (`uploaded_files` table); files API, agent file tool and history only use the user's own files |
| `8def39c` | First visit (or a session that expired while the app was closed) starts a guest session in the chat instead of showing the login page |
| `a8c83a6` | Settings and the first sync wait for the session, so a first visit or a logout no longer lands on the login page by a race |
| `3e32e58` | Login through Keycloak or another OIDC provider (`AUTH_MODE=oidc`), optional bundled Keycloak for docker compose, mock login for development only (`docs/authentication.md`) |
| `0c6bea7` | Database URLs name the psycopg2 driver: SQLAlchemy 2.1 (in images built since `3e32e58`) defaults to psycopg 3, so the backend image couldn't connect |
| `89440e4` | The Keycloak compose file mounts the realm from `helm/advanced-llm-chat/files/` (the file moved there in `0c6bea7`) |
| `ccb1d57` | Compose keeps uploads, the TTS cache and logs on the volume (they were lost with the container), and passes `TAVILY_API_KEY` |
| `2083ec7` | Helm chart `helm/advanced-llm-chat` and releases from `main` (images, chart on GHCR, GitHub release with the chart and a compose bundle). Its first run on `develop` passed all jobs (version 0.1.172, chart and bundle as artifacts) |
| `0a55d68` | Handover notes after the Helm chart |
| `7492ce8` (on `main`) | **Release 0.1** (PR #138 from `release/0.1`, merged with the admin bypass; `03f60c4` merged `main` into `release/0.1` first, keeping the files `main` had edited but `develop` had deleted). The release run published the images and chart as 0.1.175 and the GitHub release `v0.1.175` (chart and compose bundle); the chart and images pull without credentials |
| `b127b7e` (local) | Messages are ordered by the server's clock: the server stamps the time when it stores a message and the chat sorts by server id (see "How the app works now") |
| `25144bf` (local) | GPT-6 Astra replaces GPT-5.2 in the starter catalog, marked without tools (see "Model test results") |
| `dc45f59` (local) | The sidebar banner shows only "LLM Chat"; the Fessi-era robot logo is gone (redesign pending, see "Next steps") |

The contract for the runtime, the catalog, agents, tools and the history budget is in `docs/model_catalog_api.md`; provider choices are in `docs/model_provider_strategy.md`.

### How the app works now

- **Models:** `backend/llm/` calls OpenAI-compatible endpoints and Anthropic through the official SDKs. Reasoning text is streamed as a live "Thinking" step; models that need it (Kimi) get their `reasoning_content` back in tool loops; Claude gets its thinking blocks back.
- **Catalog:** providers (base URL, key env var, privacy tier, currency) come only from `catalog/models.json` (`MODEL_CATALOG_FILE`, the default; `${VAR}` in a base URL is filled from the environment). Keys are always read from the env var named in `api_key_env`. Models and agents are seeded once and then edited on the Agents page; `app_init` (and Docker's `db-init` on every start) never overwrites existing models or agents.
- **Agents** (the `personas` table; the UI says "Agent"): a name, description, prompt with `{{variables}}` and a tool selection (`files`, `web_search`, `knowledge_graph`, or null for every tool the server enables). No model: the chat's model answers, so models are compared by switching the model in the chat or starting another chat with the same agent.
- **Login** (`AUTH_MODE`, `docs/authentication.md`): `oidc` through Keycloak or another OpenID Connect provider (the backend runs the code flow, no token reaches the browser, logout ends the provider's session too), `mock` for development, `none` (default) for guests only. Users are found by the provider's subject id; a first login links an existing user with the same verified email.
- **Admins** are users with `OIDC_ADMIN_ROLE`, or listed in `ADMIN_EMAILS` (with `oidc` only if the email is verified). Only they see the Agents page; everyone else uses the models and agents in the chat's pickers. Guests only get models and agents marked "available to guests".
- **History** sent to the model: the newest messages that fit the model's `context_window` (estimated at 3 characters per token, minus room for the answer, tool results, system prompt and tool definitions; `DEFAULT_CONTEXT_WINDOW` 32768 for models without one).
- **Guests:** each guest login creates its own user (`users.is_guest`), deleted with its conversations and files by the hourly cleanup once its sessions have expired. Guests are rate-limited per IP with one counter (`guest_usage`, 5 per 3 hours, hard-coded in `backend/api/auth.py` and `backend/security/auth.py`): every answer counts, a guest login only counts when the IP has no entry yet, and once the count reaches 5 both answers and new guest logins are refused until 3 hours after the last counted request. Behind a reverse proxy set `FORWARDED_ALLOW_IPS`.
- **Message order** (`b127b7e`, local): order and time come from the server's clock, never the device's. The server stamps a message's time when it stores it, and message ids are its clock in milliseconds. `Message.compare` sorts stored messages by id, then the messages only in the browser (negative ids from `Message.localId()`, e.g. a failed send) by time; the history sent to the model is ordered by id too. Before, the user message carried the device's time and the answer the server's, so a device clock running ahead put answers above their questions (seen with this PC 42 s fast).
- **Files:** only the uploader can read a file (API, agent tool and history).
- **Privacy:** the browser only talks to the app's own frontend and backend (no Google Fonts, no IP lookup service).

### Starter catalog (`catalog/models.json`)

| Provider | Models | Context | Effort | Notes |
|---|---|---|---|---|
| Cortecs (EU router, Vienna; account settings to use: Sovereign Cloud and ZDR on, Nebius excluded) | DeepSeek V4.1 Flash, DeepSeek V4 Pro, Mistral Large 4, Kimi K3 | 512k | high | Prices in EUR from `api.cortecs.ai/v1/models` |
| Homelab router (`${MODEL_ROUTER_API}`) | Gemma 4 MoE (`gemma-4-26b-a4b`) | 128k | – | Auxiliary model (titles, speech preprocessing) and the guest model |
| Anthropic | Claude Opus 5.5, Sonnet 5.5, Haiku 5.5 | 512k | xhigh | Disabled until `ANTHROPIC_API_KEY` is set |
| OpenAI | GPT-6 Astra (replaced GPT-5.2 in `25144bf`; databases seeded before keep GPT-5.2) | 512k (of 1.05M) | xhigh | Without tools (see "Model test results"); $10/$50 per million tokens, above 272k input twice the input and 1.5 times the output price |

Personas: Pirate (all tools) and Translator (no tools).

### Decisions made by the user (2026-10-30)

- "Usability first, privacy preferred" for providers.
- Start with the newest DeepSeek, Mistral and Kimi models plus one good general model; no coding-focused models such as GLM (those are tested in the user's agent framework instead).
- Gemma 4 MoE from the homelab router.
- **Context:** 512k for every model that supports it; Gemma stays at 128k.
- **Reasoning effort: the second-highest level per model,** because the top level ("max") tends to overthink. That is xhigh for Claude and GPT-6 Astra (low…max) and high for the others: DeepSeek and Kimi go low/high/max, Mistral only has high.
- **Single-admin setup:** no per-user API keys, billing or private agents; provider keys stay in env vars and the catalog is edited by the admin in the app.
- Agents don't include a model, and there is no side-by-side comparison of agents or models.
- **Login:** Keycloak is optional: bundled (docker compose or the Helm chart), the user's own, or none. Guest logins stay. The homelab deployment is public for guests (the user shows the AI to others) and adds login through the user's existing homelab Keycloak, which stays reachable only at home: the user's phone reaches it through a VPN that is on demand for the homelab's internal domain. Guest mode never contacts Keycloak (checked with a backend whose Keycloak doesn't exist), so visitors only hit a dead end if they press "Log in". The homelab realm allows self-registration, so the deployment sets `OIDC_REQUIRED_ROLE=user`.
- **Deployment:** a Helm chart next to the docker compose files; images and chart are built and published when `develop` is merged into `main`. The chart will replace the current homelab deployment, which still runs old Fessi-era images.
- **Releases:** every merge into `main` is a release `<major>.<minor>.<run number>` (major and minor in `Chart.yaml`): images tagged with the version and `latest`, the chart at `oci://ghcr.io/knaeckebrothero/charts/advanced-llm-chat`, and a GitHub release with the chart and a docker compose bundle.
- **2026-10-30/31:** the old homelab deployment was replaced without keeping its data. GPT-6 Astra replaces GPT-5.2. Messages are ordered the way messengers do it: the server's order and the server's time, never the device's clock.

### Model test results (2026-10-30)

`python -m backend.llm.smoke_test --model <id>` passed for all four Cortecs models and Gemma; every model answered real chats through the app.

- **DeepSeek V4 Pro** doesn't think unless `reasoning_effort` is set (now high).
- **GPT-5.2** defaults to no reasoning and got a test question wrong without it; at high it reasons and is right.
- **Gemma 4** must not get its reasoning back (it repeats tool calls), ignores `reasoning_effort`, thinks about 250 tokens even for titles, and returns its reasoning in the `reasoning` field (vLLM).
- **Cortecs** accepts every effort value and maps a level a model lacks to the next lower one.
- **Homelab router:** about 15% of requests failed with "Backend unavailable: All connection attempts failed", in bursts, and some requests stalled for 60–90 s. Long prompts work (45k tokens tested). This is a router problem to look at, not an app problem. The router also serves Whisper (`whisper-large-v3`), Kokoro TTS (`kokoro`, `tts-1`, `tts-1-hd`), Qwen3 embeddings and rerankers, which the app's voice features (`WHISPER_BASE_URL`, `TTS_BASE_URL`) and a future vector search could use.
- **GPT-6 Astra** (`gpt-6-astra`, official specs: 1.05M context with 922k input, 128k output, effort low…max, knowledge cutoff 2026-04-30): plain chats work. On Chat Completions it always reasons (`reasoning_effort: none` is rejected) and rejects tools together with any `reasoning_effort` (400), so tools with reasoning need the **Responses API**, which the runtime doesn't use. The catalog marks it `supports_tools: false`, so the app sends it no tools. It's disabled in the dev database.
- **The original GPT-4** can't be added: `gpt-4`, `gpt-4-0613`, `gpt-4-turbo` and `gpt-3.5-turbo` answer 404 "deprecated" although `/v1/models` still lists them. `gpt-4o` and `gpt-4.1` still work (the user doesn't want GPT-4o).

### Homelab deployment (2026-10-30)

- The Fessi-era deployment was replaced by the chart, release 0.1.175, through Fleet in the HomeLab repository (`~/Repositories/HomeLab`, private; the addresses and the details are in its `deployments_managed/advanced-llm-chat/README.md`). Two bundles: `advanced-llm-chat-config` (an ExternalSecret from Vault with `POSTGRES_PASSWORD`, `OIDC_CLIENT_SECRET`, `MODEL_ROUTER_KEY` and the provider keys) and `advanced-llm-chat` (the OCI chart with its values: `auth.mode: oidc`, `adminRole: admin`, `requiredRole: user`, the bundled Postgres on Longhorn, no ingress).
- **Public for guests** through the homelab's Cloudflare Tunnel; **login** through the homelab Keycloak (client `llm-chat`), which stays reachable only at home or through the VPN. The old namespace, its volumes and the old manifests were deleted (it had no important data).
- **Upgrades:** bump `version:` in the HomeLab `fleet.yaml` to a newer release; the init container migrates the database. Catalog changes (e.g. GPT-6 Astra) only arrive with a release, and seeding adds models but never removes them, so the production database keeps GPT-5.2 until it's disabled on the Agents page.
- **Checks:** a public check as a guest passed 13 of 14 steps (frontend, health, `oidc` mode, mock login gone, guest login, guest models, a streamed answer, the login redirect to Keycloak with the registered client); the only failure was Gemma, while one of the router's backends was down for maintenance. Keycloak accepts the client (its login form is shown).
- **PWA (2026-10-31):** the deployed app is installable (Chromium reports no installability errors with a normal profile; manifest, service worker and icons load) and starts offline from the service worker's cache as "Guest (Offline)". Not tested: Safari on iOS, and the Keycloak login from the installed app (it leaves the app's scope for the backend and Keycloak addresses, so check once on the phone that the session arrives).

### Next steps

1. **Push `develop`** (the four local commits after `0a55d68`) when the user says so.
2. **GPT-6 Astra with tools:** a Responses API adapter in `backend/llm/` (tools together with reasoning, its reasoning shown as "Thinking"). Waiting for the user's decision.
3. **Sidebar banner and app icons:** the robot logo is gone; the redesign is open. Options discussed: A, a quiet wordmark; B, a custom SVG mark plus wordmark that also replaces the favicon and PWA icons (still the 2024 cyborg portrait; recommended); C, no brand in the sidebar. Also the name: "LLM Chat" or "Advanced LLM Chat".
4. **Refused guest login:** when the IP's guest quota is used up, the guest login gets a 429, the app creates an offline guest, the next requests get 401s and send the visitor to the login page, where "Continue as guest" fails again. Show the limit message with the reset time instead, and make the limit configurable (5 per 3 hours is tight for people sharing one connection). Offered to the user, not started.
5. **Next release:** merge `develop` into `main`, then bump the HomeLab `fleet.yaml` version to deploy the message order fix, Astra and the banner.
6. Look at the homelab router's failures.

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
- Since PR #137 the user prefers committing **directly to `develop`** (no feature branches or PRs) and pushing with the admin bypass; GitHub logs these pushes as "Bypassed rule violations". Merging into `main` stays a separate step the user asks for.
- On every push to `develop` and `main`, `docker-build.yml` builds `ghcr.io/knaeckebrothero/advanced-llm-chat-{frontend,backend}`. Images from `develop` are tagged `develop-latest`, `develop` and `sha-<commit>`; a merge into `main` is a release (version tag and `latest`, plus the chart and the GitHub release; CLAUDE.md, "Kubernetes and releases"). On pull requests it builds without pushing.
- `deploy-gh-pages.yml` deploys `develop` to https://knaeckebrothero.github.io/Advanced-LLM-Chat/. It uses the `DEPLOY_GH_PAGES` secret and takes its base path from the repository name.
- After the merge of PR #137, both workflows passed on `develop` (`a45a68d`). The backend image takes about 9.5 minutes, the frontend about 2.5.
- Release 0.1 (PR #138, `7492ce8`) brought `main` up to `develop` at `0a55d68`. The branch `release/0.1` is kept. Before that, `main` was 90 commits behind and had 10 of its own (2 March 2026 edits to `backend_mockup.py`, which `develop` had deleted and the release keeps deleted, a 2024 `LICENSE.txt` edit and 7 PR merge commits). Later releases: a PR from a `release/<major>.<minor>` branch (or `develop`) into `main`, merged with `gh pr merge <n> --admin` when the user asks.

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

Since the catalog work (evening of 2026-10-30):

- `.env` needs `AUTH_MODE=mock` for the email login (the default is `none` since `3e32e58`).
- `.env` also has `CORTECS_API_KEY`, `MODEL_ROUTER_API`, `MODEL_ROUTER_KEY` and `ADMIN_EMAILS` (the user's own address). `ANTHROPIC_API_KEY` isn't set yet, so the Claude models are disabled. The router address is private: it stays in `.env` and never goes into the repository.
- **Changes to `.env` need a backend restart:** `--reload` only watches `.py` files, and the keys are read from the process environment.
- **Reseed after editing `catalog/models.json`:** `python backend/app_init.py --prod` updates providers and adds missing models and agents. Existing models and agents keep their database values, so change those on the Agents page or with SQL.
- **`ng serve` needs a restart** after `angular.json` changes (e.g. the bundled fonts).
- **Tests:**
  - offline runtime tests: `python -m backend.llm.tests.run_all` (27 pass);
  - catalog end to end: `backend/catalog/tests/catalog_api_test.py` (188 pass, 181 with `--skip-network`) on its own database `llm_chat_catalog_test` and a backend on port 8445 with `AUTH_MODE=mock`, see its docstring;
  - login end to end: `backend/security/tests/oidc_test.py` (62 pass) against the bundled Keycloak and a backend with `AUTH_MODE=oidc` on `llm_chat_auth_test`, see its docstring;
  - model smoke test: `python -m backend.llm.smoke_test --model <id>`;
  - frontend: `npx tsc --noEmit -p tsconfig.app.json`, `npm run build`, and the unit tests (57 of 89 fail since `a8c83a6`, all of them failing before; compare the failing spec names, not just the count).
- **Chart checks:** `helm lint helm/advanced-llm-chat`, `helm template` with different values, and `kubeconform -strict` on the output (helm 3.20, kubeconform and k3d are installed). For a real install, a throwaway k3d cluster with its own kubeconfig (`k3d cluster create <name> -p "18080:80@loadbalancer" --kubeconfig-update-default=false --kubeconfig-switch-context=false`) and `localhost:18080` / `keycloak.localhost:18080` as the addresses. On this machine k3d nodes can't pull from Docker Hub (EOF), and `k3d image import` silently skips multi-platform images: import with `docker save --platform linux/amd64 <image> | docker exec -i <node> ctr -n k8s.io images import -`. The backend image is 3.6 GB (PyTorch for local Whisper) and pulls at about 1.5 MB/s here; for chart tests, an image built from `requirements.txt` without `openai-whisper` works (Whisper is imported lazily).
- **Browser checks:** the Playwright MCP browser hung on start on 2026-10-30; a headless script with the cached `playwright-core` and `~/.cache/ms-playwright/chromium_headless_shell-1217` worked. Keycloak's login form: `#username`, `#password`, `#kc-login`. For installability checks use a persistent profile (`launchPersistentContext`; a normal context reports "in-incognito") and the full `chromium-1217` build; Playwright's offline mode doesn't stop the service worker's own requests, so test offline with `--host-resolver-rules=MAP * ~NOTFOUND`. To test clock skew, `context.clock.install({ time: Date.now() + 5 * 60 * 1000 })` runs the page's clock ahead.
- **Checks against the production deployment** from home use the home connection's guest quota (5 guest logins or answers per 3 hours): every fresh browser profile or script is a new guest login. Keep them few; the 429's detail gives the reset time, and a 429 doesn't count.
- **This PC's clock** was 42 s fast on 2026-10-31: chrony runs but has never synced, because its only sources (the gateway and one from DHCP) don't answer. That clock skew is how the message order bug showed up.
- **Browser checks as an admin:** mock-login with an `@example.invalid` address and start a backend with that address added to `ADMIN_EMAILS` in the process environment (`load_dotenv` doesn't override variables that are already set).
- **Dev database:** test users from the sessions were deleted. Still there: the seed users (`guest@guest.local` as user 0, `test@`, `admin@`, `demo@example.com`), the user's account, and three users named `test`, `testsetst` and `tetse` (probably the user's own test logins). Two uploads from December 2025 (`file_1766482527957_…`, `file_1766482575933_…`) have no owner, because no message refers to them, so nobody can read them.

Checks that passed:

- **End to end:** API calls (guest login, create a conversation, send a message, stream the agent) and a real browser run, with the reply streamed back from `gpt-5.2`.
- **Graph tools against a throwaway Neo4j 5.15:** seeding from a file, schema, text search in strings and lists, value shortening, truncation flag, and `CREATE` / `DETACH DELETE` rejected with the counts unchanged.
- **Builds and tests:** `tsc` and the production build pass. Unit tests have 58 of 88 failing, the same 58 as on `develop` before the change, so nothing regressed.

## Known issues and findings (backlog)

Updated on 2026-10-30 (evening). Resolved since PR #137: the LangChain dependency (gone with the new runtime), the Placeholder Component and `/metrics` page (removed), the guest and file access problems, and the mock login (development only since `3e32e58`; see "Status").

**Security and privacy (before exposing the app):**

- **Session token in the body:** the guest login response also returns the session key as `token`, so scripts in the page can read what the httpOnly cookie hides. The frontend doesn't use it.
- **Guest logins are barely rate-limited:** they share the answers' counter per IP (5 per 3 hours) but only count when the IP has no entry yet, so a script that doesn't ask anything can create many guest users (each deleted after its session expires). Once the counter is used up, new guest logins are refused, which the frontend doesn't handle (see "Next steps").
- **Session expiring while the app is open:** the next request gets a 401 and `AuthInterceptor` sends the user to the login page; a guest could get a new guest session instead. (At startup this is fixed: a missing or expired session starts a guest session in the chat.)
- Files belong to users, not to conversations (see `docs/attachment_rework.md`). Deleting a conversation leaves its TTS cache on disk.
- The guest isolation and file ownership end-to-end checks from 2026-10-30 only existed as scratch scripts. They are worth adding to the backend tests.

**Model catalog and runtime:**

- **Homelab router failures:** about 15% of requests fail with "Backend unavailable" and some stall for 60–90 s (router side).
- **Removing a provider:** a provider deleted from `catalog/models.json` stays in the database, because seeding only warns and the API has no delete. Removing it takes SQL.
- **Unused columns:** `llm_providers.api_key_encrypted` and `personas.default_model_id` are left over in existing databases. They are harmless; drop them by hand if wanted.
- **Long context costs money:** every answer resends the history, up to the context window. A 400k-token history costs about €1.08 of input per Kimi K3 answer. Provider caching helps where it exists.
- **Cautious token estimate:** 3 characters per token means a 512k window carries roughly 330k real tokens of English history. Raising it to 4 uses more of the window but risks overflow on tokenizers that count more tokens.
- **Claude Haiku 5.5** costs five times more above 100k prompt tokens. The cost display uses the lower price.
- **Voice settings follow the chat model's server:** `WHISPER_BASE_URL` and `TTS_BASE_URL` default to `OPENAI_BASE_URL`. The homelab router serves Whisper and Kokoro, which could be used instead.

**Frontend:**

- **Unit tests:** 57 of 89 fail, mostly `NullInjectorError: No provider for HttpClient` in component specs. `projects/ngx-agent-chat/tsconfig.spec.json` also errors with "No inputs were found".
- **Unsent messages after a reload:** the sync status (`pending`, `failed`) only lives in memory; IndexedDB doesn't store it. After a reload the next sync treats an unsent message as obsolete and drops it. There's no outbox that retries unsent messages either.
- **Error notice of a failed answer:** if an answer fails before the server starts it, the error notice exists only in the browser and sorts last. If the user sends another message instead of regenerating, the notice stays below the newer messages until the next sync drops it.
- **Console errors:**
  - `ExpressionChangedAfterItHasBeenCheckedError` (NG0100) in the chat input field;
  - `assets/env.js` 404 in development.
- **Bundle size:** the production bundle is 1.39 MB, over the 1 MB budget (a warning, not an error).
- **Dead code:** the `status-bar` component (not rendered, uses old `$color-*` variables from `_variables.scss`).
- **UI nits seen in screenshots:** a horizontal scrollbar at the bottom of the sidebar, and "(2 steps)" wrapping in the thought-process header.
- `projects/ngx-agent-chat` is an empty library scaffold from March 2026; to be decided during the chat refactor.

**Setup and Docker:**

- **Unpinned requirements:** `requirements.txt` only has lower bounds, so every image build that reinstalls packages can pick up breaking releases (SQLAlchemy 2.1 broke the database URL, fixed in `0c6bea7`). A lock file or upper bounds would make builds repeatable.
- **Large backend image:** 3.6 GB, almost all of it PyTorch for `openai-whisper` (local transcription, off by default). An image without it, or a separate variant with it, would be about a tenth of the size.

- **Dev certificates:** they are regenerated on *every* backend start, by `start_backend.py` and again by importing `backend/main.py`. The backend and the Angular dev server therefore use different certificates, and trusting `devcerts/ca.pem` never lasts. They should only be generated when missing.
- `schema.sql` starts with a comment-only statement, which logs a harmless "can't execute an empty query" warning at startup.
- **Two compose files:** dev (builds the images) and prod (pulls them) still duplicate most settings. The CI's heredoc copy is gone: releases bundle the prod file (`.github/scripts/compose-bundle.sh`).
- **Uploads in Docker:** until the Helm chart work, `FILES_DIR` (`./files`) wasn't on the mounted volume in the compose files, so uploads were lost with the container. The compose files and the chart now put files, the TTS cache and logs on the volume. Deployments that set `FILES_DIR=./files` themselves (the old homelab deployment) have the same problem.
- The old `helm/fessi` chart only ever existed as ignored files (`.gitignore` ignores `*.yaml`); a leftover copy may still be on disk locally. The repository's chart is `helm/advanced-llm-chat`, excepted from that rule.
- The provider research (report and the five sets of notes) lives in `docs/research/`.

## Ideas discussed for later

- **Model setup:** done (model catalog, model picker per conversation, model and usage stored per message; see "Status").
- **Knowledge storage:** a setting for a graph database, a vector database or both. The graph tools could become memory or knowledge-base tools, which would need write tools. pgvector code exists in the Küppelsmühle repo (`backend/knowledge/`).
- **Themes:** separate palette from mode (palette × light/dark/auto), maybe a custom accent color. Check how much CSS each Angular Material theme adds before adding many palettes.
- **Custom background image:** done (`1043e47`). Unlike the first idea, an own image stays in the browser (IndexedDB) and isn't uploaded; only the choice, dim and blur sync.
- **Other appearance settings:** font size, chat column width.
- **Configuration point for downstream:** a `SYSTEM_PROMPT_FILE` setting (Küppelsmühle already has one) would let Fessi supply its prompt without code changes. Agents may cover this now: a downstream repo can ship its prompt as an agent in its own catalog file.
- **Homelab router services:** use its Whisper and Kokoro for voice, and its Qwen3 embeddings and reranker for a vector search (pgvector code exists in the Küppelsmühle repo).

## For downstream projects (Fessi)

When Fessi merges upstream, it can re-add its layer through configuration instead of code where possible:

- **Waste graph data:** keep `neo4j_seed.cypher` in the Fessi repo and set `NEO4J_ENABLED=true` plus `NEO4J_SEED_FILE`.
- **Waste-specific tools:** add them next to the generic graph tools, or rely on `query_graph`.
- **Prompt:** Fessi's prompt can be an agent (persona) in Fessi's own catalog file. As the default prompt it still needs a code change in `backend/llm/prompts.py` (the old `agent.py` is gone), until a `SYSTEM_PROMPT_FILE` setting exists.
- **Merge size:** upstream changed a lot since Fessi forked (`e2763d4`): the new runtime without LangChain, the model catalog, agents, guest users and file ownership. Expect a large merge.
- **Branding:** the university logo and Fessi icons; the hook for the logo's dark-mode variant (`isDarkMode`) is still in place.

## Model providers (decided on 2026-10-30)

*Historical record of the provider decision. What was actually set up is in "Status" (Cortecs, the homelab router, Anthropic, OpenAI); Scaleway and Berget AI weren't set up yet. The "App changes needed" below were done in the new runtime, except the separate voice base URLs.*

The user wants inference providers for open models (Kimi, DeepSeek, GLM, Qwen, gpt-oss, Mistral, …), with a strong preference for **European companies and EU data centers with good privacy**: GDPR, a DPA, no training on prompts, little or no retention. The user would rather avoid aggregators like OpenRouter, whose routing makes privacy unclear. The user also has Anthropic API credits, and Anthropic is already supported natively.

Hard technical requirement: an OpenAI-compatible chat completions API with **streaming and tool calling** (at the time the agent used LangChain `ChatOpenAI` with `bind_tools`; it now uses the `openai` SDK directly). Vision is a plus.

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
2. Design the provider and model configuration and the model picker (done).
3. Set up and test (done for Cortecs, the homelab router and OpenAI; Anthropic waits for its key).
4. Deploy to the homelab.
5. Merge into `main`.

Homelab context: the Kubernetes setup lives in `~/Repositories/HomeLab` (GitHub `Kubernetes-Cluster-Project`). The machine already runs an AMD ROCm GPU for voice models, and a local k3d cluster and registry are in use for other projects.
