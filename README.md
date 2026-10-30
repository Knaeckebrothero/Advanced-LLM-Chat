# Advanced LLM Chat

**A self-hosted chat app for talking to large language models.**

Advanced LLM Chat is an Angular Progressive Web App with a FastAPI backend. Messages are answered by an agent that reasons in steps, uses tools and streams its work, including the model's thinking, to the browser. It runs against OpenAI, any OpenAI-compatible endpoint (llama.cpp, vLLM, OpenRouter, ...) or Anthropic, and keeps your conversations available offline.

The project started in 2023 as a personal project to learn how to build AI systems. Later it became the base for university projects, most notably **Fessi**, a waste disposal assistant built at Frankfurt University of Applied Sciences in 2025. This repository is the general version; adapted versions such as Fessi live in their own repositories and build on top of it (see [Building on top of this project](#building-on-top-of-this-project)).

## Table of Contents

- [Features](#features)
- [Quick Start with Docker](#quick-start-with-docker)
- [Local Development](#local-development)
- [Configuration](#configuration)
- [Knowledge Graph (optional)](#knowledge-graph-optional)
- [Architecture](#architecture)
- [Building on top of this project](#building-on-top-of-this-project)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## Features

**Chat**
- Agent responses streamed over Server-Sent Events: the model's thinking, tool calls and the final answer token by token
- Multiple LLM providers on the official SDKs: OpenAI and OpenAI-compatible servers (llama.cpp, vLLM, EU hosts, routers), Anthropic
- Token usage per answer
- Markdown rendering, copying messages, automatic conversation titles, renaming and deleting conversations

**Tools**
- File retrieval: the agent can reopen files shared earlier in a conversation
- Web search via Tavily (when `TAVILY_API_KEY` is set)
- Read-only Neo4j knowledge graph tools (when `NEO4J_ENABLED=true`)

**Files and voice**
- Image, PDF and document attachments; a separate vision model can describe images for text-only models
- Voice messages transcribed with Whisper (API or local model)
- Text-to-speech playback of answers

**App**
- Offline-first: conversations are stored in IndexedDB and synced with the backend
- Guest sessions and user accounts
- German and English UI, light and dark themes, installable as a PWA

## Quick Start with Docker

Requirements: Docker with Docker Compose, and an API key for at least one LLM provider.

```bash
cd docker

# Provide your LLM settings (or put them in docker/.env)
export OPENAI_API_KEY=your_key
export OPENAI_MODEL=gpt-4o-mini

# Build and start PostgreSQL, the backend and the frontend
docker compose up -d --build
```

- Frontend: http://localhost:8080
- Backend API docs: https://localhost:8443/api/docs (accept the self-signed certificate first)

To use the pre-built images from the GitHub Container Registry instead of building locally:

```bash
docker compose -f docker-compose.prod.yml up -d
```

The images are tagged `develop-latest` (from `develop`) and `latest` (from `main`). To run the frontend on another machine, point it at the backend with `API_URL=https://<host>:8443 docker compose up -d`.

## Local Development

Requirements: Node.js 20+, Python 3.11+, Docker (for PostgreSQL).

1. **Configure the environment**
   ```bash
   cp .env.example .env
   # Set at least one LLM provider, e.g. OPENAI_API_KEY and OPENAI_MODEL
   ```

2. **Start PostgreSQL**
   ```bash
   cd docker && docker compose up -d postgres && cd ..
   ```

3. **Set up the backend**
   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   python backend/app_init.py --seed   # filesystem, .env, dev certificates, database with test data
   ```

4. **Start the backend**
   ```bash
   python start_backend.py --reload    # https://localhost:8443
   ```

5. **Start the frontend** (in a second terminal)
   ```bash
   npm install
   npm start                           # https://localhost:4200
   ```

### Useful commands

```bash
# Frontend
npm run build                     # production build (dist/advanced-llm-chat/browser/)
npm test                          # unit tests (Karma/Jasmine)
npx tsc --noEmit -p tsconfig.app.json   # type check

# Database
python backend/app_init.py --force-reset --seed   # reset and reseed
python backend/app_init.py --prod                 # additive schema migration, never deletes data
docker logs llm-chat-postgres
```

`--prod` only creates missing tables and columns and warns about anything that needs a manual migration, so it is safe to run against a production database.

## Configuration

All settings are environment variables; `.env.example` lists every option with a short explanation. The most important ones:

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `openai` or `anthropic` (detected from the API keys if unset) |
| `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL` | OpenAI, or any OpenAI-compatible server via `OPENAI_BASE_URL` |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | Anthropic |
| `POSTGRES_*` | PostgreSQL connection (required) |
| `TAVILY_API_KEY` | Enables the web search tool |
| `NEO4J_ENABLED` | Enables the knowledge graph tools (default `false`) |
| `REASONING_LEVEL`, `AUXILIARY_REASONING_LEVEL` | Reasoning effort of the model for answers and for titles / speech preprocessing |
| `VISION_*` | Separate vision model that describes images and PDF pages for text-only models |
| `USE_LOCAL_WHISPER`, `WHISPER_*`, `TTS_*` | Speech-to-text and text-to-speech |
| `CORS_ORIGINS`, `SSL_CERTFILE`, `SSL_KEYFILE` | Deployment behind your own domain and certificates |

## Knowledge Graph (optional)

The backend can connect the agent to a Neo4j graph database. The graph is off by default; when it is enabled, the agent gets three read-only tools that work with any graph schema:

- `get_graph_schema`: node labels, their properties and the relationship patterns between them
- `search_graph`: case-insensitive text search across the string properties of all nodes
- `query_graph`: runs a Cypher query in a read transaction, so writes are rejected

To enable it:

```bash
# .env
NEO4J_ENABLED=true
# NEO4J_SEED_FILE=path/to/seed.cypher   # optional: data for an empty graph

cd docker && docker compose --profile graph up -d neo4j && cd ..
python backend/app_init.py               # connects to Neo4j and seeds it if a seed file is set
```

With the full Docker setup, set `NEO4J_ENABLED=true` and `COMPOSE_PROFILES=graph` so the `neo4j` service starts with the rest.

## Architecture

```
Browser (Angular PWA, IndexedDB)  ──HTTPS / SSE──>  FastAPI backend  ──>  LLM provider
                                                       │   │
                                                       │   └──> agent loop (backend/llm) ──> tools (files, web search, Neo4j)
                                                       └──> PostgreSQL (users, conversations, messages, files)
```

**Frontend** (`src/app/`): state services (`ChatStateService`, `UIStateService`, `SettingsStateService`) sit on top of repositories for IndexedDB access and a `SyncEngineService` that syncs with the backend. `ChatService` and `StreamingService` send messages and consume the agent's SSE stream. Messages are a discriminated union (`TextContent`, `AgentContent`) created through factory methods.

**Backend** (`backend/`):

```
backend/
├── main.py           # FastAPI app
├── config.py         # settings from environment variables
├── app_init.py       # filesystem, certificates and database initialization
├── api/              # routes: auth, conversations, messages, settings, files
├── database/         # PostgreSQL (SQLAlchemy Core) and the optional Neo4j manager
├── models/           # Pydantic request/response models
├── llm/              # LLM runtime on the openai / anthropic SDKs: clients, agent loop, tool registry,
│                     # system prompt, smoke test (python -m backend.llm.smoke_test --env)
├── services/
│   ├── conversation_history.py  # history in the OpenAI message format
│   ├── tools/            # file, web search and knowledge graph tool implementations
│   └── ...               # vision, audio, TTS, title generation
└── security/         # authentication, CSRF, logging
```

**Agent streaming protocol** (`POST /api/message/stream-generate`): `message_start` (message metadata and model), `step` (thought, tool call, tool result, observation; a step with an existing id replaces it), `step_delta` (text appended to a step, the model's live thinking), `token` (final answer), `done` (with the token usage) and `error`.

## Building on top of this project

This repository stays general. Projects that need their own branding, prompts, tools or data are kept as separate repositories that pull this one in as `upstream`, much like Ubuntu builds on Debian:

```bash
# In the downstream repository
git remote add upstream https://github.com/Knaeckebrothero/Advanced-LLM-Chat.git
git fetch upstream
git merge upstream/develop
```

Improvements that are useful for everyone go into this repository first and then flow down. Current downstream projects:

- [Fessi](https://github.com/Knaeckebrothero/Fessi): waste disposal assistant for Frankfurt University of Applied Sciences

## Contributing

The project uses Git Flow (see [docs/GitFlow.pdf](docs/GitFlow.pdf)):

- `main`: releases; container images are tagged `latest`
- `develop`: integration branch; changes arrive through pull requests
- `feature/*`, `release/*`, `hotfix/*`: work branches, merged back through pull requests

Pushes to `develop` and `main` build the Docker images and publish them to the GitHub Container Registry. Design notes and implementation plans live in [`docs/`](docs/).

## License

Licensed under the Creative Commons Attribution 4.0 International License (CC BY 4.0). See [LICENSE.txt](LICENSE.txt).

## Acknowledgments

Thanks to the 2025 student team at Frankfurt University of Applied Sciences, in particular Rachid Yagubi and TillCa, who redesigned the user interface while building Fessi on top of this project.
