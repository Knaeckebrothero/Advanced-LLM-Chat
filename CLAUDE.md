# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Angular 19.2.2 application with FastAPI backend for a waste disposal assistant chatbot (Fessi). Uses microservices architecture with separate frontend and backend containers, supports multiple LLM models via Replicate API, and includes offline-first capabilities with IndexedDB. Supports i18n with German and English via ngx-translate.

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
# Start backend (auto-generates SSL certs on first run)
python start_backend.py              # Default: https://localhost:8443
python start_backend.py --reload     # With auto-reload for development
python start_backend.py --host 0.0.0.0 --port 8443  # Custom host/port

# Required .env file:
# USE_DEV_CERTS=True
# REPLICATE_API_TOKEN=your_token_here

# Backend testing
pytest                      # Run all tests
pytest -v                   # Verbose output
pytest tests/test_api.py    # Run specific test file
```

### Docker Development
```bash
cd docker
docker-compose up -d --build              # Build and run locally
docker-compose -f docker-compose.prod.yml up -d  # Use pre-built images from ghcr.io
```

## Architecture Overview

### Frontend Structure
The Angular app follows a service-oriented architecture with clear separation of concerns:

- **Core Services** handle business logic and data management:
  - `ApiService`: Backend communication with retry logic and interceptors
  - `AuthService`: Authentication state and session management  
  - `DbService`: IndexedDB operations for offline storage
  - `ThemeService`: Theme management and system preference detection

- **State Management Services** provide reactive state:
  - `ChatStateService`: Manages conversations, messages, and chat operations
  - `UIStateService`: Handles UI state (sidebar, responsive behavior) 
  - `SettingsStateService`: User preferences with theme integration

- **Repository Pattern** for data access:
  - `ConversationRepository`: Conversation CRUD operations with caching
  - `MessageRepository`: Message operations with offline queue
  - `SettingsRepository`: Settings persistence
  - `SyncEngineService`: Handles data synchronization between IndexedDB and backend

- **Components** are organized by feature:
  - `chat-ui/`: Main chat interface with input field and message display
    - `chat-ui-inputfield/`: Text/voice input with audio visualization
    - `chat-ui-message/`: Message rendering with markdown support
  - `sidebar/`: Conversation list with search and management
  - `auth/`: Login components and authentication guards
  - `settings/`: User configuration interface
  - `status-bar/`: Connection status and sync indicators

### Backend Architecture
The FastAPI backend (`backend/`) is a modular Python package:
```
backend/
├── main.py           # FastAPI app entry point
├── config.py         # Configuration constants
├── api/              # Route handlers (auth, conversations, messages, settings, files)
├── database/db.py    # SQLAlchemy models and database setup
├── models/           # Pydantic request/response models
├── services/llm.py   # Replicate API integration
├── security/         # Auth, CSRF, logging
├── middleware/       # Request/response middleware
└── utils/            # Certificates, hashing

start_backend.py      # Entry point script
```

Key backend features:
- RESTful API endpoints for chat operations
- WebSocket support for streaming responses
- Session-based authentication with mock/guest providers
- SQLite database for conversation persistence
- Integration with Replicate API for multiple LLM models

### Key Patterns
- **Offline-First**: All data stored in IndexedDB, synced with backend when available
- **Observable Pattern**: Heavy use of RxJS for async operations and state management
- **Guard Pattern**: Route protection via AuthGuard (currently allows guest access)
- **Interceptor Pattern**: Automatic auth header injection via `AuthInterceptor`
- **Message System**: Discriminated union types for different message formats (text, voice, files)

## Git Workflow

The project follows Git Flow:
- `main`: Production branch (protected)
- `develop`: Integration branch (protected, requires PR)
- `feature/*`: Feature development
- `release/*`: Release preparation
- `hotfix/*`: Emergency fixes

## CI/CD Pipeline

### GitHub Actions
1. **Docker Build** (`docker-build.yml`): Builds and pushes images to ghcr.io on develop push
2. **GitHub Pages** (`deploy-gh-pages.yml`): Deploys static build to GitHub Pages

### Deployment
- Frontend and backend containers communicate via HTTPS
- Self-signed certificates for development
- Production uses GitHub Container Registry images

## Important Considerations

### Code Standards
- **TypeScript Strict Mode**: All code must pass strict TypeScript checks - no ESLint configured
- **Angular Material**: Use existing Material components for UI consistency
- **State Services**: Prefer injecting state services (`ChatStateService`, `UIStateService`, `SettingsStateService`) over direct repository access
- **Message Type Safety**: Use factory methods `Message.createText()`, `Message.createVoice()` for type-safe message creation

### Data Layer
- **IndexedDB**: All database operations go through `DbService` - never access IndexedDB directly
- **Serialization**: Use `toJSON()`/`fromJSON()` methods when storing/retrieving objects from IndexedDB
- **UUID Conversation IDs**: New conversations use UUIDs; frontend accepts both string and number types for backward compatibility

### API & Authentication
- **SSL Required**: Both frontend (port 4200) and backend (port 8443) require HTTPS
- **Authentication**: All API calls require session authentication via `AuthInterceptor`
- **HTTP Options**: Use `ApiService.getHttpOptions()` for consistent headers with credentials
- **Error Handling**: API errors return `ErrorResponse` model with error message

### Build & Environment
- **Build Output**: Production builds output to `dist/fessi/browser/` (Angular 19+ pattern)
- **Environment Variables**: Use Angular environments (`src/app/environments/`) for frontend config
- **i18n**: Use ngx-translate - translations in `src/assets/i18n/` (de.json, en.json)

## Testing Approach

- Unit tests use Karma/Jasmine framework
- Test files are co-located with components (`.spec.ts`)
- Run specific tests: `ng test --include='**/specific-component.spec.ts'`
- Backend tests would use pytest (not currently implemented)

## API Endpoints

The backend provides these main endpoints (all require session authentication):
- **Auth**: `/api/auth/mock-login`, `/api/auth/guest-login`, `/api/auth/logout`, `/api/auth/me`
- **Conversations**: `/api/conversations`, `/api/conversation/create`, `/api/conversation/messages/{id}/{timestamp}/{count}`
- **Messages**: 
  - `/api/message/send` - Send a message
  - `/api/message/generate` - Generate AI response
  - `/api/message/send-and-generate` - Combined endpoint for better performance
  - `/api/message/patch` - Update message
  - `/api/message/delete/{conversation_id}/{message_id}` - Delete message
- **Settings**: `/api/settings` (GET/PUT)
- **LLMs**: `/api/llms` (list available models)
- **Files**: `/api/files/upload` (file upload endpoint - mock implementation)

## Database Schema

### Frontend (IndexedDB)
- **chatMessages**: Messages with indexes for conversationId and time
- **conversations**: Conversation metadata with userId index
- **user**: User information store

### Backend (SQLite)
- **users**: User accounts with email and name
- **conversations**: Chat conversations with participants
- **messages**: Chat messages with type field for discriminated content
- **sessions**: Active user sessions with expiration
- **guest_usage**: Rate limiting for guest users
- **user_settings**: User preferences and LLM settings

## Message System

The message system uses a discriminated union pattern with factory methods:
- **TextContent**: Regular text messages with optional file attachments
- **VoiceContent**: Audio messages with base64 data, duration, and optional transcript
- Create messages via `Message.createText()` or `Message.createVoice()`

## Offline Support

- File uploads queue when offline and auto-upload when connection restores
- Voice messages stored as base64 in IndexedDB for offline access
- Connection monitoring checks every 30 seconds for pending uploads
- Local-only conversations supported for offline usage

## Common Development Patterns

### Adding a New Feature
1. Create/update the data model in `src/app/data/objects/`
2. Update database schema if needed in `db-schema.ts`
3. Create/update repository in `src/app/repositories/`
4. Update relevant state service in `src/app/services/`
5. Create/update UI components
6. Add unit tests alongside implementation

### API Integration
1. Define request/response models in backend
2. Add endpoint to `ApiService`
3. Update repository to use new endpoint
4. Handle offline scenarios in state service

### State Management Flow
```typescript
Component -> State Service -> Repository -> API Service -> Backend
                    ↓              ↓
                    └──> DBService (IndexedDB)
```