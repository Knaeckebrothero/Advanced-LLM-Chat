# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Angular 19.2.2 PWA with FastAPI backend for a waste disposal assistant chatbot (Fessi). Uses microservices architecture with:
- **Frontend**: Angular with IndexedDB for offline-first capabilities, Angular Material UI, ngx-translate for i18n (German/English)
- **Backend**: FastAPI with PostgreSQL for persistence, Neo4j knowledge graph for waste disposal data, LangGraph agent with multi-step reasoning
- **LLM Integration**: Multi-provider support (Replicate, OpenAI, Anthropic) with SSE streaming for agent responses

## Essential Commands

### Frontend Development
```bash
npm start          # Start dev server with SSL (https://localhost:4200)
npm run build      # Production build (outputs to dist/fessi/browser/)
npm test           # Run unit tests with Karma/Jasmine
npm run watch      # Build with watch mode
ng test --include='**/specific.spec.ts'  # Run specific test file
npx tsc --noEmit   # Type-check without building (no ESLint configured)
```

### Backend Development
```bash
# 1. Start databases (PostgreSQL required, Neo4j optional for knowledge graph)
cd docker && docker-compose up -d postgres neo4j && cd ..

# 2. Initialize databases and filesystem (first time or after reset)
python backend/app_init.py --seed    # Creates tables and seeds all databases

# 3. Start backend (auto-generates SSL certs on first run)
python start_backend.py              # Default: https://localhost:8443
python start_backend.py --reload     # With auto-reload for development

# Database commands
cd docker && docker-compose stop             # Stop all databases
python backend/app_init.py --force-reset --seed  # Reset and reseed all databases
python backend/app_init.py --skip-neo4j --seed   # Skip Neo4j initialization

# Backend testing
pytest                      # Run all tests
pytest -v                   # Verbose output
pytest tests/test_api.py    # Run specific test file
```

### Environment Configuration
Copy `.env.example` to `.env` and configure:
```bash
# Required
REPLICATE_API_TOKEN=your_token_here
USE_DEV_CERTS=True

# PostgreSQL (required)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=fessi_chat
POSTGRES_USER=fessi
POSTGRES_PASSWORD=fessi_dev_password

# Neo4j (optional - for knowledge graph)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=fessi_neo4j_dev

# LLM Provider (optional - defaults to Replicate)
# LLM_PROVIDER=openai          # or "anthropic"
# OPENAI_API_KEY=your_key      # Required if using OpenAI
# OPENAI_MODEL=gpt-4o-mini
# OPENAI_BASE_URL=http://custom-server:8080/v1  # For llama.cpp or compatible servers

# Vision/Multimodal (optional)
# MODEL_RECEIVE_IMAGES=false   # Set true if primary model supports vision
# VISION_MODEL=gpt-4o-mini     # Separate model for image analysis

# Audio Transcription (optional)
# USE_LOCAL_WHISPER=false      # Set true for local Whisper model
# LOCAL_WHISPER_MODEL=base     # tiny, base, small, medium, large
```

### Docker Development
```bash
cd docker
docker-compose up -d --build              # Build and run locally
docker-compose -f docker-compose.prod.yml up -d  # Use pre-built images from ghcr.io
```

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
  - `DbService`: IndexedDB operations for offline storage

- **Repository Pattern** for data access:
  - `ConversationRepository`, `MessageRepository`, `SettingsRepository`
  - `SyncEngineService`: Data synchronization between IndexedDB and backend

### Backend Architecture
```
backend/
├── main.py           # FastAPI app entry point
├── config.py         # Configuration constants
├── app_init.py       # Database and filesystem initialization
├── api/              # Route handlers (auth, conversations, messages, settings, files)
├── database/
│   ├── db.py         # PostgreSQL database manager (SQLAlchemy)
│   ├── tables.py     # SQLAlchemy Core table definitions
│   ├── neo4j_db.py   # Neo4j knowledge graph manager
│   └── queries/      # SQL files (schema.sql, seed.sql)
├── models/           # Pydantic request/response models
├── services/
│   ├── llm_provider.py   # Multi-provider LLM abstraction
│   ├── agent.py          # LangGraph agent with Neo4j tools
│   └── tools/            # LangChain tools for knowledge graph
├── security/         # Auth, CSRF, logging
└── utils/            # Certificates, hashing
```

### Key Patterns
- **Offline-First**: All data stored in IndexedDB, synced with backend when available
- **Observable Pattern**: Heavy use of RxJS for async operations and state management
- **Interceptor Pattern**: Automatic auth header injection via `AuthInterceptor`
- **Message System**: Discriminated union types with factory methods `Message.createText()`, `Message.createAgent()`

## Code Standards

### TypeScript/Angular
- **Strict Mode**: All code must pass strict TypeScript checks - no ESLint configured
- **Angular Material**: Use existing Material components for UI consistency
- **Message Type Safety**: Use factory methods for message creation, type guards for content access

### Data Layer
- **IndexedDB**: All database operations go through `DbService` - never access directly
- **Serialization**: Use `toJSON()`/`fromJSON()` methods when storing/retrieving objects
- **UUID Conversation IDs**: New conversations use UUIDs; frontend accepts both string and number types

### API & Authentication
- **SSL Required**: Both frontend (port 4200) and backend (port 8443) require HTTPS
- **HTTP Options**: Use `ApiService.getHttpOptions()` for consistent headers with credentials

## Message System

Uses discriminated union pattern with factory methods:
- **TextContent**: Regular text messages with optional file attachments (including voice messages)
- **AgentContent**: Agent responses with reasoning steps and final response
- Voice messages are TextContent with audio file attachment; transcript is in text content

## Agent Streaming Protocol

The `/api/message/stream-generate` SSE endpoint emits:
- **message_start**: Message metadata (messageId, conversationId, roleName, time, type)
- **step**: Agent reasoning step (thought, tool_call, tool_result, observation)
- **token**: Individual text tokens for final response
- **done**: Signals completion
- **error**: Error information

## Git Workflow

Git Flow branching:
- `main`: Production (protected)
- `develop`: Integration (protected, requires PR)
- `feature/*`: Feature development
- `release/*`: Release preparation
- `hotfix/*`: Emergency fixes
