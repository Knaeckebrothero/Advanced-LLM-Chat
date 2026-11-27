# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Advanced LLM Chat: an Angular 19.2.2 PWA with a FastAPI backend for chatting with LLMs. Uses microservices architecture with:
- **Frontend**: Angular with IndexedDB for offline-first capabilities, Angular Material UI, SCSS styling, ngx-translate for i18n (German/English)
- **Backend**: FastAPI with PostgreSQL for persistence (image `pgvector/pgvector:pg16`), an agent loop with tool use (`backend/llm/`), a knowledge base per user that agents opt into (`kb_*` tools, `docs/knowledge_base.md`; the Knowledge base page `/knowledge-base` to read, edit and export it for Obsidian; a note keeps files of a conversation, above all images, under a name of its own: `kb_write`/`kb_update` take `files`, one note per image whose text says what it shows, and the agent shows a kept file in any conversation by placing it in its answer by that name, `![a fox](red-fox.png)`, table `kb_files`) with the agent's memory (its note `memory`, part of every answer: the system prompt keeps a snapshot of it per conversation so prompt caches keep working, changes go to the model as a note with the newest message, `backend/services/memory_snapshot.py`; `memory_*` tools; a background memory review after quiet conversations; a nightly consolidation into a weekly journal, a Kubernetes CronJob; agents with `own_memory` get their own knowledge base; an agent with **Saves on its own** off (`personas.auto_memory`, e.g. a storyteller whose prompt says what becomes canon) saves only when its prompt says so or the user asks: no save rules in its prompt, no review (its chats' messages only join its memory, the menu's button says "Make searchable for <agent>") and no nightly consolidation, `docs/knowledge_base.md` "Saving on its own"; agents that also pick `past_chats` search and read the user's earlier conversations of their memory with `chat_search` (regular expressions), `chat_list` and `chat_read`, `docs/past_chats.md`: every message belongs to the memory its agent used when it was stored, `messages.memory_vault`), MCP servers as tools of the agents (`docs/mcp.md`: the admins' servers picked per agent on the Agents page, users' own servers on the MCP servers page `/mcp` for agents that select `user_mcp`; Streamable HTTP, SSE, stdio for admins with `MCP_STDIO_ENABLED`; headers or OAuth sign-in, secrets encrypted with `ENCRYPTION_KEY`; servers' questions to the user, elicitation, answered in the chat), the files of a conversation (`docs/files.md`: uploads and what tools create, such as the images of an MCP server, are stored the same way; the agent of the conversation lists and reads them with `list_files` and `read_file` (a model gets an image scaled to 1568 pixels; `read_file`'s `region` gives a part of it at the image's own resolution, to check details), and shows one by placing it in its answer's text as a Markdown image with the file's name, `![what it shows](fox-1.png)`, which the chat shows at that place; images are never cropped and never loaded from web addresses; **Files of this chat**, in a conversation's menu and the composer's attach menu, lists them all to open and download, and **All files** in the settings does so for all conversations; an agent that selects the tool group `web_fetch` opens web addresses with the tool of that name: a page comes back as text, an image, PDF or audio file is saved to the conversation, so the agent can look at an image a tool's result or the user only names by its address; public addresses only, never for guests), optional Neo4j knowledge graph (`NEO4J_ENABLED`)
- **LLM Integration**: Thin runtime on the official `openai` and `anthropic` SDKs (no LangChain): OpenAI, any OpenAI-compatible endpoint, and Anthropic, with SSE streaming for agent responses, which run on the server without the browser (closing the app doesn't stop them, `docs/background_answers.md`)
- **Side chats** (`docs/side_chats.md`): a conversation forked from a message of another one (`conversations.parent_id`, `fork_message_id`, `side_chat`), to ask about something or make an image on the side; its history is its parent's messages up to that message, then its own, with the parent's system prompt and memory snapshot (so the prompt cache covers that part); nothing goes back into the main chat. Shown in a panel next to the chat (a sheet on a phone, `SideChatPanelComponent`), answering with an `AnswerFollower` of its own while the main chat answers; a badge on the message, a button on the chat and a count in the sidebar find them again. **Make it a conversation** copies the parent's messages up to the fork and their files into it (`POST /api/conversation/{id}/promote`); deleting a conversation keeps its side chats as conversations or deletes them (`?sideChats=keep|delete`)
- **Skills** (`docs/skills.md`): texts in the `SKILL.md` format (name, description, Markdown instructions) that admins write or import on the Agents page and attach to agents (`personas.skills`); the system prompt lists an agent's skills by name and description, and the agent loads one with `use_skill` when a request needs it. Two starter skills ship in `catalog/skills/` (named by `catalog/models.json`): `image-generation` (open-weight diffusion models, e.g. on Civitai) and `character-writing`

**Resuming work:** read the "Status" section of `docs/generalization_refactor.md` first (current state, decisions, backlog, next steps), and `docs/model_catalog_api.md` for the runtime and catalog contract.

This repository is the general **upstream**. Adapted versions (e.g. Fessi, a waste disposal assistant) live in separate downstream repositories that merge `upstream/develop`. Keep domain-specific branding, prompts, tools and data out of this repository; add configuration points instead so downstream changes stay small.

## Essential Commands

### Frontend Development
```bash
npm start          # Start dev server with SSL (https://localhost:4200)
npm run build      # Production build (outputs to dist/advanced-llm-chat/browser/)
npm test           # Run unit tests with Karma/Jasmine
npm run watch      # Build with watch mode
npx tsc --noEmit   # Type-check without building (no ESLint configured)

# Run specific test file
ng test --include='src/app/services/chat-state.service.spec.ts'
```

**Note:** Frontend dev server requires SSL certs in `./devcerts/` (server.pem, server.key). These are auto-generated by the backend on first run.

### Backend Development
```bash
# 1. Start PostgreSQL (Neo4j is optional: set NEO4J_ENABLED=true and add `--profile graph neo4j`)
cd docker && docker compose up -d postgres && cd ..

# 2. Initialize databases and filesystem (first time or after reset)
python backend/app_init.py --seed    # Creates tables and seeds the databases (Neo4j only if NEO4J_ENABLED=true)

# 3. Start backend (auto-generates SSL certs on first run)
python start_backend.py              # Default: https://localhost:8443
python start_backend.py --reload     # With auto-reload for development

# Database commands
cd docker && docker-compose stop             # Stop all databases
python backend/app_init.py --force-reset --seed  # Reset and reseed all databases
python backend/app_init.py --skip-neo4j --seed   # Skip Neo4j initialization
python backend/app_init.py --prod            # Production migration (add missing columns, skip Neo4j)
```

**Note:** No Python test framework (pytest) is configured. There are test scripts instead:
- `python -m backend.llm.tests.run_all`: offline tests of the LLM runtime, history (with the tool calls of earlier answers) and tools, with the file tools and `web_fetch` (fake OpenAI server, mocked Anthropic API, a web server on 127.0.0.1)
- `python backend/services/tests/mcp_test.py`: MCP servers against real MCP servers of the SDK (HTTP, SSE, stdio, headers, a fake OAuth authorization server) and a real Postgres, in a `<POSTGRES_DB>_mcp_test` database it creates itself; also the files of conversations (tools' images, uploads, previews, the files API)
- `python backend/services/tests/knowledge_base_test.py`: the knowledge base and memory tools, agents' own knowledge bases, the memory review (fake model server), the files notes keep, the Obsidian export and the `/api/kb` endpoints against a real Postgres, in a `<POSTGRES_DB>_kb_test` database it creates itself
- `python backend/services/tests/past_chats_test.py`: the search over past chats (`docs/past_chats.md`): the memory of every message, its fill-in and the review's claim, the search, list and read and their tools, the trigram index, against a real Postgres, in a `<POSTGRES_DB>_chats_test` database it creates itself
- `python backend/services/tests/message_sync_test.py`: the messages a browser syncs (`GET /api/conversation/{id}/messages`): the newest by id, an answer of the same second as its message that is stored later, the page before a message, only the owner, through the real app and a real Postgres, in a `<POSTGRES_DB>_sync_test` database it creates itself
- `python backend/services/tests/answer_versions_test.py`: the versions of an answer (`docs/answer_versions.md`): regenerating keeps the earlier version (history before the answer), switching, deleting a version, export and import, and stopped answers (kept as a message or a version), through the real app, a real Postgres in a `<POSTGRES_DB>_versions_test` database it creates itself, and the fake OpenAI server
- `python backend/services/tests/background_answers_test.py`: answers that run on without the browser (`docs/background_answers.md`): a closed stream doesn't stop the answer, following it again (all, or after an event's number, merged), Stop, one answer per conversation, only the owner, deleting the conversation, the shutdown's wait, through the real app, a real Postgres in a `<POSTGRES_DB>_background_test` database it creates itself, and the fake OpenAI server
- `python backend/services/tests/side_chats_test.py`: side chats (`docs/side_chats.md`): creating one, its history (the parent's up to the fork, the request beginning as the parent's), the summary, its files, the fork message deleted, making it a conversation (copies, files), deleting a conversation with its side chats kept or deleted, export, past chats, hidden, only the owner; through the real app, a real Postgres in a `<POSTGRES_DB>_side_test` database it creates itself, and the fake OpenAI server
- `python backend/services/tests/skills_test.py`: the agents' skills (`docs/skills.md`): storing and checking them, the agents' lists (rename, delete), `SKILL.md` import and export, the catalog file (also skill files next to a seed file), and the skills of an answer (prompt section, `use_skill`), against a real Postgres, in a `<POSTGRES_DB>_skills_test` database it creates itself
- `backend/catalog/tests/catalog_api_test.py`: catalog end-to-end test against a backend on its own `*_test` database (see its docstring)
- `python backend/services/tests/upload_safety_test.py`: the limits of what reading a file may cost (`docs/files.md`, "Limits"), offline, with files it builds itself: PDFs with huge pages or that take minutes or gigabytes, images that claim millions of pixels, the local Whisper model as a fake
- `python backend/security/tests/guest_limits_test.py`: what guests may use (the counters per client address and every limited endpoint), the error texts for guests, logins and logout from another site's page, the largest request; through the real app and a real Postgres, in a `<POSTGRES_DB>_guest_test` database it creates itself
- `backend/security/tests/oidc_test.py`: login through Keycloak end-to-end, against the bundled Keycloak and a backend in `AUTH_MODE=oidc` on a `*_test` database (see its docstring)
- `python -m backend.llm.smoke_test --model <id>`: real API calls against one catalog model

### Environment Configuration
Copy `.env.example` to `.env`. Required settings:
```bash
OPENAI_API_KEY=your_key_here  # Or ANTHROPIC_API_KEY
USE_DEV_CERTS=True
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=llm_chat
POSTGRES_USER=llm_chat
POSTGRES_PASSWORD=llm_chat_dev_password
```

Login: `AUTH_MODE` is `oidc` (an OpenID Connect provider such as Keycloak, the `OIDC_*` settings), `mock` (any email, no password: development only, set in the dev `.env`) or `none` (the default: guests only). Guests can always chat; what they use is counted per client address (`backend/security/guest_limits.py`, the `GUEST_*` settings: answers, titles, speech, uploads, stored messages, logins), so every endpoint a guest can reach that costs a model call or stores data needs one of these limits. See `docs/authentication.md`, also for the optional bundled Keycloak (`docker/docker-compose.keycloak.yml`).

Model catalog: providers are defined in `catalog/models.json` (`MODEL_CATALOG_FILE`, the default) and their keys are read only from the env vars they name (`CORTECS_API_KEY`, `ANTHROPIC_API_KEY`, `MODEL_ROUTER_API`/`MODEL_ROUTER_KEY`, ...). It ships the agents Assistant (signed-in users only: files, web search, `web_fetch`, knowledge base, past chats), Pirate and Translator; users pick the agent new chats start with in the settings (`defaultPersonaId`, none by default). Models, agents and MCP servers are listed with higher `sort_order` numbers first (catalog file version 2; a version 1 file is read with its numbers turned around). Admins (who may edit models and agents on the Agents page, `/agents`) are users with `OIDC_ADMIN_ROLE`, or listed in `ADMIN_EMAILS` (with `oidc` only if the email is verified). An agent made in the app is only its creator's until its switch **Public** is on (`personas.public`; one without a creator, as seeded ones, is everybody's; a catalog file entry without `public` is public; `persona_of_another()`); **Hidden** only hides it in family mode. Restart the backend after changing `.env`.

See `.env.example` for all optional settings (Neo4j, vision models, Whisper, TTS, web search).

### Docker Development
```bash
cd docker
docker-compose up -d --build              # Build and run locally
docker-compose -f docker-compose.prod.yml up -d  # Use pre-built images from ghcr.io

# Deploy to a remote server (set API_URL to backend address)
API_URL=https://192.168.1.50:8443 docker-compose up -d
```
Settings for compose go in `docker/.env` (template: `docker/.env.example`); `docker/docker-compose.keycloak.yml` adds the optional Keycloak.

### Kubernetes and releases
The Helm chart is `helm/advanced-llm-chat` (see its README): frontend, backend (runs `app_init --prod` in an init container), Postgres, optional Keycloak and ingress, and the CronJob of the nightly memory consolidation (`backend.memoryDream`, not in docker compose). Check it with `helm lint helm/advanced-llm-chat` and `helm template`. The Keycloak realm file lives in the chart (`files/llm-chat-realm.json`) and docker compose mounts it from there.

`.github/workflows/docker-build.yml`: every push to `develop` builds the images (`develop-latest`, `sha-…`); every merge into `main` is a release `<major>.<minor>.<run number>` (major and minor from `Chart.yaml`): images tagged with the version and `latest`, the chart pushed to `oci://ghcr.io/knaeckebrothero/charts/advanced-llm-chat`, and a GitHub release with the chart and the compose bundle (`.github/scripts/compose-bundle.sh`).

## Architecture Overview

### Frontend Structure
Service-oriented architecture with clear separation of concerns:

- **State Management Services** (prefer these over direct repository access):
  - `ChatStateService`: Manages conversations, messages, and chat operations
  - `UIStateService`: Handles UI state (sidebar, responsive behavior)
  - `SettingsStateService`: User preferences with theme integration

- **Core Services**:
  - `ApiService`: Backend communication with retry logic and interceptors
  - `StreamingService`: SSE connection handling for agent response streaming
  - `ChatService`: Orchestrates message sending, AI generation, and streaming
  - `AnswerFollower`: follows one conversation's answer (start, follow again after a broken stream, Stop); `ChatStateService` has one for the open conversation, `SideChatService` one for the open side chat (`docs/side_chats.md`)
  - `SideChatService`: the side chat panel (the list or one side chat), sending, Stop, promote and delete of side chats
  - `DbService`: IndexedDB operations for offline storage (in `src/app/data/`)
  - `AuthService`: Authentication state and session management (in `src/app/auth/`)
  - `ThemeService`: Theme management with system preference detection

- **Repository Pattern** for data access:
  - `BaseRepository`: Abstract base class for CRUD operations
  - `ConversationRepository`, `MessageRepository`, `SettingsRepository`
  - `SyncEngineService`: Data synchronization between IndexedDB and backend

### Backend Architecture
```
backend/
├── main.py           # FastAPI app entry point
├── config.py         # Configuration constants
├── app_init.py       # Database and filesystem initialization
├── api/              # Route handlers (auth, conversations, messages, settings, files, catalog, knowledge_base, mcp)
├── catalog/          # Model catalog: resolver (model/persona per request), service, catalog file seed/import/export, fetch-models
├── database/
│   ├── db.py         # PostgreSQL database manager (SQLAlchemy)
│   ├── tables.py     # SQLAlchemy Core table definitions
│   ├── neo4j_db.py   # Neo4j knowledge graph manager (optional)
│   ├── neo4j_init.py # Neo4j init, seeds from NEO4J_SEED_FILE
│   └── queries/      # SQL files (schema.sql, seed.sql)
├── models/           # Pydantic request/response models
├── llm/              # LLM runtime on the openai/anthropic SDKs
│   ├── types.py          # ModelConfig, Usage, model_from_env()
│   ├── client.py         # AsyncOpenAI / AsyncAnthropic clients from a ModelConfig
│   ├── agent_loop.py     # run_agent() (streamed tool loop) and complete() (one call)
│   ├── openai_chat.py    # Chat Completions adapter (reasoning_content passback, <think> tags)
│   ├── anthropic_chat.py # Messages adapter (format conversion, thinking blocks)
│   ├── tools.py          # Tool registry with JSON schemas, default_tools()
│   ├── tool_record.py    # An answer's tool calls and results as the model got them, kept for later answers
│   ├── prompts.py        # build_system_prompt()
│   ├── smoke_test.py     # python -m backend.llm.smoke_test --env | --model <id>
│   └── tests/            # Offline test scripts (fake OpenAI server, mocked Anthropic API)
├── services/
│   ├── answer_runs.py    # Answers run as tasks of their own, followed by any number of streams, stopped only by Stop (docs/background_answers.md)
│   ├── conversation_history.py  # Conversation history in the OpenAI message format, cut to the model's context window
│   ├── conversation_summary.py  # Rolling summary of the oldest messages once the history nearly fills the window
│   ├── conversation_file.py  # Export and import of conversation files (docs/conversation_file.md)
│   ├── knowledge_base.py # A user's Markdown notes (kb_notes, revisions, links) per vault: slugs, search, versions, the memory, the files notes keep (docs/knowledge_base.md)
│   ├── past_chats.py     # The user's earlier conversations of a memory: grep with regular expressions in Postgres, list, read (docs/past_chats.md)
│   ├── skills.py         # The agents' skills (docs/skills.md): storage, the agents' lists, SKILL.md import and export
│   ├── side_chats.py     # Making a side chat a conversation of its own (docs/side_chats.md): copies of the parent's messages and files
│   ├── memory_review.py  # Reviews quiet conversations of knowledge base agents and saves what matters to the memory
│   ├── memory_dream.py   # Nightly consolidation: weekly journal, tidied memory, patterns (CronJob; python -m)
│   ├── knowledge_base_export.py # The notes as a zip that opens as an Obsidian vault
│   ├── file_store.py     # The stored files (docs/files.md): uploads and tools' files per conversation, previews, the scaled image for a vision model
│   ├── web_fetch.py      # What is at a web address, for the tool web_fetch: public addresses only, limits, a page's HTML as text
│   ├── document_handler.py  # PDFs: text and page images, made in a process of its own with limits (pdf_worker.py), since a PDF comes from anybody
│   ├── vision_helper.py  # Image analysis for text-only models
│   ├── audio_handler.py  # Whisper transcription (API or local)
│   ├── tts_handler.py    # Text-to-speech generation
│   ├── tts_preprocessor.py  # Converts markdown/code to speech-friendly text
│   ├── mcp/              # MCP servers (docs/mcp.md): store, servers (validation, ${VAR}), pool (connections per server and user), oauth (sign-in, token refresh), tools (an answer's MCP tools), media (the images, audio and PDFs of a tool result, kept as files)
│   └── tools/            # Tool implementations (files, web search, web_fetch, read-only knowledge graph, knowledge base, past chats, use_skill)
├── security/         # Sessions, login through an OIDC provider (oidc.py), CSRF, the guests' limits (guest_limits.py), error texts for clients (errors.py), logging, secrets.py (ENCRYPTION_KEY)
└── utils/            # Certificates, hashing
```

### Frontend Data Objects
Located in `src/app/data/objects/`:
- `message.ts`: Message model with discriminated union content types
- `conversation.ts`: Conversation model with metadata
- `settings.ts`: User settings model
- `file-preview.ts`: File attachment handling

### Key Patterns
- **Offline-First**: All data stored in IndexedDB, synced with backend when available
- **Observable Pattern**: Heavy use of RxJS for async operations and state management
- **Interceptor Pattern**: Automatic auth header injection via `AuthInterceptor`; a 401 outside `/api/auth/me` opens the login page, so nothing may call the API before the AuthService has a session (the first sync and the backend's settings wait for it)
- **Message System**: Discriminated union types with factory methods `Message.createText()`, `Message.createAgent()`

## Code Standards

### TypeScript/Angular
- **Strict Mode**: All code must pass strict TypeScript checks - no ESLint configured
- **Angular Material**: Use existing Material components for UI consistency
- **Message Type Safety**: Use factory methods for message creation, type guards for content access
- **No inline scripts**: the Content-Security-Policy (`docker/nginx.conf`, and the meta tag in `src/index.html`) is `script-src 'self'`, so no `<script>` block or `on...=` handler in HTML and no `eval`/`new Function`: the browser refuses them and the feature silently breaks. A script that must run before the app goes into a file under `src/assets/` (like `theme-init.js`; nginx serves it `no-cache`, as it has no hash in its name). The production build keeps `inlineCritical: false` in `angular.json`, since Angular's inline stylesheet loader is an `onload` handler

### Data Layer
- **IndexedDB**: All database operations go through `DbService` - never access directly
- **Serialization**: Use `toJSON()`/`fromJSON()` methods when storing/retrieving objects
- **UUID Conversation IDs**: New conversations use UUIDs; frontend accepts both string and number types
- **schema.sql**: the backend runs it at every start in one transaction (`init_tables()`), split at every semicolon outside `$$` quotes, also in `--` comments: no semicolons in its comments, and no statement that can fail (one failure aborts the rest; wrap such a statement in a `DO` block with a check). A backfill that must run once is detected before `app_init --prod` adds columns (`files_lack_conversations()`, `messages_lack_memory()`)

### API & Authentication
- **SSL Required**: Both frontend (port 4200) and backend (port 8443) require HTTPS
- **HTTP Options**: Use `ApiService.getHttpOptions()` for consistent headers with credentials

## Message System

Uses discriminated union pattern with factory methods:
- **TextContent**: Regular text messages with optional file attachments (including voice messages)
- **AgentContent**: Agent responses with reasoning steps and final response
- Voice messages are TextContent with audio file attachment; transcript is in text content
- Editing (setting `editingMode`): **guided** edits only your own messages and answers an edited one again (`PATCH /api/message/patch` with `deleteFollowing` deletes the later messages, then stream-generate); **manual** edits the text of any message (an agent message keeps its steps) and inserts user, assistant or system messages next to any message (`POST /api/message/insert`, which picks an id between the neighbours), without generating. Once the conversation has a stored message (system messages aside), an empty composer shows **Generate** next to the mic: stream-generate answers the conversation as stored (`answerLatestMessage()`). After an answer too: a history ending with the model's message would be an Anthropic prefill and is refused by other providers, so stream-generate then appends a note in the user's place that asks the model to go on (`CONTINUE_NOTE` in `backend/services/conversation_history.py`) and shows it as the step "Asked to go on"; the note is not stored as a message. A message sent from the composer is answered right away in both modes. Manual editing also shows an input token indicator next to the mic (`ContextMeterComponent`): about how many tokens the next answer sends, against the model's context window (`POST /api/message/context-size`, estimates without the MCP servers' tools, see `docs/model_catalog_api.md`). A patch keeps a text message's attachments, and an answer's tool calls and results (the new text becomes its only text). Manual editing also shows the system prompt the next answer gets as the conversation's first message (`SystemPromptComponent`, `GET /api/message/system-prompt`: as the model gets it, without the conversation's system messages). Editing it gives the conversation its own system prompt (`PUT /api/message/system-prompt`, `conversations.system_prompt`), which is sent as it is in place of the one built from the agent (`''` sends none, `null` goes back to the built one)
- Versions of an answer (`docs/answer_versions.md`): **Regenerate** (on the newest answer) writes a new version and keeps the earlier one; `‹ 2/3 ›` under any answer with versions switches between them, and the version shown is the one the next answers get (no branches: the messages after a switched answer stay). The version shown is the `messages` row with the answer's id (so its place), the others are in `message_alternatives` with their tool records (`messages.alternative_position`, the code says *alternatives* since `version` is the edit counter). stream-generate with `regenerateId` keeps the id and builds the history before the answer; `POST /api/message/alternatives/switch` and `/delete` (Delete on an answer with versions deletes the one shown). A switch or new version raises the message's version counter and drops a covering summary and the cached speech. The server stores stopped answers (as a message or a version) once the model has begun: Stop (`POST /api/message/stop`) cancels the answer's task and stream-generate catches the cancellation (`CancelledError`/`GeneratorExit`, no `await` in that handler)
- System messages (inserted, or from an imported conversation) are instructions to the model for every answer after them: they go to the end of the system prompt (`with_instructions()`), not into the history, so they are never cut off or summarized
- History: the newest messages that fit the model's context window. An earlier answer that called tools goes back with its **tool record** (`backend/llm/tool_record.py`, table `message_tool_records`): the tool calls and their results as real messages, then its text, so the model knows what it did and the next request continues the last one word for word (provider caches). Models with `reasoning_passback` (Kimi K3, DeepSeek, GLM-5.3) get their `reasoning_content` back with it, of every answer: one without tool calls then has a record of its text with its reasoning. Images of results are not sent again, a result over `HISTORY_TOOL_RESULT_CHARS` is cut, `HISTORY_TOOL_CALLS=false` sends only the text. Never trust a model's own account of earlier turns without it: check `messages.agent_steps`. No message goes with more than `HISTORY_MESSAGE_TOKENS` (30000, at most 10% of the window, `message_token_cap()`): a longer one, also the one being answered, goes as its start and its end with a note, so a summary and the newest message always fit. Past 80% of the window, the chat's model folds the oldest exchanges into a rolling summary before answering, keeping only the newest messages of that cap word for word (`conversation_summaries`, the history starts with it; dropped when a message it covers is edited, deleted or inserted); the chat shows it as a divider. **Summarize** in a conversation's menu folds all messages so far into it on request (`POST /api/message/summarize`). See `docs/model_catalog_api.md`
- Conversations are exported and imported as conversation files (`docs/conversation_file.md`); `scripts/convert_legacy_conversations.py` converts the exports of the 2023/24 app
- Order and time come from the server's clock, never the device's: the server stamps a message's time when it stores it, and its ids are that clock in milliseconds. `Message.compare` sorts stored messages by id, then the ones only in the browser (negative ids from `Message.localId()`, e.g. a failed send) by time. A message the server didn't take is not answered: the chat marks it "Not sent" with **Send again** (`resendMessage()`, stores and answers it), or it can be deleted; nothing resends it on its own
- Sync of a conversation's messages (`ConversationRepository.performSync()`, every minute for the open conversation, on focus, on opening one): the browser asks for the server's newest 20 messages (`GET /api/conversation/{id}/messages`, picked by id; `before_id` gives the page before a message for scrolling up) and merges them by id in one IndexedDB transaction (`DBService.applyServerMessages()`): new ones are added, a copy that says something else is replaced, and a message the server had at the last sync and no longer has is deleted (`serverMessageIds` in the sync metadata), so edits and deletions of other devices arrive. Never ask by time ("messages later than my newest"): `messages.time` is in seconds, and an answer carries the second its generation started in, the same as the message it answers, but is stored only when it ends, so a browser that synced in between never got it. What only the browser has stays: a message that was not sent (negative id) and an answer an older version of the app stopped (the server gave it its id and never stored it; since 2026-11-21 the server stores stopped answers). A merge is skipped when the browser changed a message itself while the request ran (`MessageRepository.changedLocallySince()`). The old route `/api/conversation/messages/{id}/{timestamp}/{count}` is only kept for browsers that still run an older version of the app
- A stored message has a version that only the server counts: `PATCH /api/message/patch` takes an edit only of the version it has (409 otherwise) and answers with the new one, which the browser's copy takes (`MessageRepository.patch()`). Nothing in the browser counts a message's version itself (`DBService.saveMessage()` stores it as it is): its copy would run ahead of the server's and the next edit be refused, which is why a message could not be edited twice in a row. On a 409 (edited on another device since the last sync, or a copy an older app version counted up) the browser asks for the message as the server has it (`?limit=1&before_id=<id + 1>`) and saves the edit once more on that version. A rating changes no version. The server's answers to an edit and a rating have the message's text only, so the browser keeps its own copy's steps, model and attachments. An edit the server doesn't take is not kept in the browser either: the chat says why under the message
- The sidebar sorts conversations by `lastMessageAt` (`Conversation.lastActivity`, falling back to `createdAt`): the server sets it to a new message's time when it stores one (not for messages inserted in manual editing), and the browser moves a conversation up right away from the stored message's id. `updatedAt` is only the last change of the conversation itself (rename, title, model). The API sends conversation times as UTC with `Z` (`UtcDatetime`)
- Your own long messages are folded (`ChatUiMessageComponent`, `.text-fold`): after ten lines the text fades out and **Read more** shows the rest in place; **Show less** folds it again and moves the view with it, so the button stays under the pointer. A text at most three lines longer is shown whole. The fold is in the CSS from the first layout and a `ResizeObserver` on the text decides before the first paint, so a message that was just sent has its height at once (the turn is placed by it). A single photo with more than a caption (200 characters) stands on its own above the bubble of its text instead of making the text a column as narrow as the photo (`message-body--photo-wide`, `docs/files.md`)
- Where the view stands (`ChatUiComponent`, "Where the view stands"): an answer is read from its first line while it is written, so the view never follows it. When the user asks for an answer (a message, **Generate**, regenerate, an edited message), their message goes to the top of the view and stays there (a long text is folded, see below, and a message still taller than 60 % of the view, one with a photo, shows only its last lines; after an answer, the new answer goes there). A reserve under the last message (`.turn-reserve`) gives the thread the height for that and shrinks as the answer grows into it; it stays until the next turn. An answer longer than the view grows out of it at the bottom, and the button to the newest message appears. The view only follows the thread's end for a reader who is there: a conversation that opens, the button, or scrolling down to the end with the wheel, a finger or keys. The browser's scroll anchoring is off while the view stands at a turn or an answer is written (`updateAnchoring()`), since the browser otherwise moves the view itself (to keep a line of the growing answer in place when the steps above it grow, or towards the end after the composer shrank). `placeTurn()` waits until the thread shows exactly the messages of the list: right after Regenerate the hidden stored copy of the answer can still stand in it, and the turn would be taken for an answer that goes on. When testing this, record the view's position from scroll events: reading the layout in between (`scrollTop`, `getBoundingClientRect()`) changes what the browser does

## Agent Streaming Protocol

An answer runs on the server on its own (`docs/background_answers.md`, `backend/services/answer_runs.py`): closing the app, a locked phone or a lost network only stops watching it, and only **Stop** (`POST /api/message/stop` with the run's id) stops it. `GET /api/message/stream/{conversationId}` follows it again: what was written so far at once (neighbouring tokens and step deltas merged), then the rest; with `runId` and `after` (the last event's number) only what the browser missed, also of an answer that ended a moment ago; 204 when there is nothing to follow. The browser follows the open conversation's answer when it opens, when the app comes back and with the sync every minute, follows a broken or stalled stream again (`ChatStateService.onStreamEnd()`), and lets go of it (it goes on) when another conversation opens. One answer per conversation: stream-generate answers 409 while one is written. A stopping server waits `ANSWER_SHUTDOWN_WAIT` (100 s) for running answers (the chart's `terminationGracePeriodSeconds` is 120). The answer requests carry `ngsw-bypass` (iOS cuts responses the service worker passes on).

The `/api/message/stream-generate` SSE endpoint emits (every event with its number as the SSE `id:`):
- **message_start**: Message metadata (messageId, conversationId, roleName, time, type, modelId, modelName, runId: the answer's run, to follow it again or stop it); with `regenerateId` in the request the messageId is that answer's (a new version, `docs/answer_versions.md`)
- **step**: Agent reasoning step (thought, tool_call, tool_result, observation); a step with an existing id replaces it, tool steps carry a `callId`; a knowledge base result carries `metadata.kbNote` (the note's slug, which the chat links to) and, when it names files that notes keep, `metadata.kbFiles` (as `metadata.files`: the chat finds a kept file the answer places by its name there). Tools can send steps while they run (`with_step_sink` in `backend/llm/tools.py`): an MCP server's question to the user (elicitation) is an observation with `metadata.elicitation` (status `pending`), which the chat shows with its form and answers through `POST /api/mcp/elicitations/{id}`; the step is then replaced with the outcome. Plain confirmations the user chose to accept automatically (this chat, or always: `mcp_auto_accept`) arrive already accepted (`auto`) (`docs/mcp.md`). A tool result that created files carries them as `metadata.files`, and those of an agent without the file tools also as `metadata.shownFiles` (`[{fileId, name, mimeType, size, width, height}]`): the chat shows a file where the answer's text places it (`answer-parts.ts`), and what the text doesn't place above it, the shown ones large and the other created ones as small previews (`docs/files.md`)
- **step_delta**: `{"id", "delta"}`, text appended to a step (the model's live "Thinking")
- **token**: Individual text tokens for final response
- **summary**: A new summary of the conversation's oldest messages (conversationId, coversUntil, messageCount, content, modelName, createdAt), written before the answer; a step (id `summary-…`) shows it being written
- **done**: Signals completion (messageId, modelId, modelName, usage, and the stored answer's version, alternativePosition, alternativeCount; `stopped: true` when Stop stopped it)
- **error**: Error information; with messageId (and the version fields) when the server stored the failed answer, which the browser then keeps

## Git Workflow

Git Flow branching:
- `main`: Production (protected)
- `develop`: Integration (protected; the sole maintainer commits directly and pushes with the admin bypass)
- `feature/*`: Feature development
- `release/*`: Release preparation
- `hotfix/*`: Emergency fixes