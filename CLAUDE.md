# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Angular 19.2.2 application with a FastAPI backend for an advanced LLM chat interface. The project uses a microservices architecture with separate frontend and backend containers, supports multiple LLM models, and includes offline-first capabilities with IndexedDB.

## Essential Commands

### Frontend Development
```bash
npm start          # Start development server (http://localhost:4200)
npm run build      # Production build (outputs to dist/advanced-llm-chat/browser/)
npm test           # Run unit tests with Karma/Jasmine
npm run watch      # Build with watch mode for development
ng test --include='**/specific.spec.ts'  # Run specific test file

# TypeScript compilation (no ESLint/TSLint configured)
npx tsc --noEmit   # Type-check without building
```

### Backend Development
```bash
# First run generates SSL certificates
python backend_mockup.py

# Start backend server with SSL
uvicorn backend_mockup:app --reload --host localhost --port 8443 --ssl-keyfile devcerts/server.key --ssl-certfile devcerts/server.pem

# Required environment variables (.env file):
# USE_DEV_CERTS=True
# REPLICATE_API_TOKEN=your_token_here
# DB_DIR=./data

# Backend testing (when implemented)
pytest                      # Run all tests
pytest -v                   # Verbose output
pytest tests/test_api.py    # Run specific test file
```

### Docker Development
```bash
# Using docker-compose (recommended)
cd docker
docker-compose up -d --build              # Build and run locally
docker-compose -f docker-compose.prod.yml up -d  # Use pre-built images from ghcr.io

# Manual Docker commands
docker build -f docker/Dockerfile -t advanced-llm-chat:latest .
docker run -d -p 8080:80 -p 8443:443 advanced-llm-chat:latest
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
The FastAPI backend (`backend_mockup.py`) provides:
- RESTful API endpoints for chat operations
- WebSocket support for streaming responses
- Session-based authentication with mock provider
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

1. **TypeScript Strict Mode**: All code must pass strict TypeScript checks (`"strict": true` in tsconfig.json)
2. **Angular Material**: Use existing Material components for UI consistency
3. **IndexedDB Schema**: Database operations go through `DbService` - never access IndexedDB directly
4. **Authentication**: All API calls require session authentication via `AuthInterceptor`
5. **Environment Variables**: Use Angular environments for configuration, not process.env
6. **SSL Required**: Both frontend and backend require HTTPS - certificates auto-generated in development
7. **Build Output**: Production builds output to `dist/advanced-llm-chat/browser/` (Angular 17+ pattern)
8. **No Linting**: Project relies on TypeScript strict mode only - no ESLint/TSLint configured
9. **Message Type Safety**: Use Message factory methods (createText, createVoice) for type-safe message creation
10. **Offline Support**: ChatService handles offline scenarios with local-only conversations and pending file uploads
11. **UUID Conversation IDs**: New conversations use UUIDs; frontend accepts both string and number types
12. **Serialization**: Use `toJSON()`/`fromJSON()` methods when storing/retrieving objects from IndexedDB
13. **HTTP Options**: Use `ApiService.getHttpOptions()` for consistent headers with credentials
14. **Error Handling**: API errors return `ErrorResponse` model with error message
15. **State Services**: Prefer injecting state services over direct repository access

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

## Recent Architecture Changes

### UUID Implementation
- Conversation IDs now use UUIDs (v4) instead of integers
- Backend generates UUIDs using Python's `uuid.uuid4()`
- Frontend supports both string and number IDs for backward compatibility
- Existing conversations are migrated to UUIDs on backend startup

### Message System Refactoring
The message system now uses a discriminated union pattern:
- **TextContent**: Regular text messages with optional file attachments
- **VoiceContent**: Audio messages with base64 data, duration, and optional transcript
- Messages are created using factory methods: `Message.createText()`, `Message.createVoice()`
- Backend stores type field and handles content appropriately

### State Management Refactoring (Phase 4)
- Replaced legacy services with new state management pattern
- Introduced `ChatStateService`, `UIStateService`, and `SettingsStateService`
- Removed old DisplayService, SyncService, and legacy SettingsService
- Implemented comprehensive unit tests for all state services

### Offline Support Enhancements
- File uploads are queued when offline and automatically uploaded when connection is restored
- Voice messages are stored as base64 in IndexedDB for offline access
- Connection monitoring checks every 30 seconds for pending uploads
- Local-only conversations supported for offline usage

### Audio Features
- Voice recording with real-time audio visualization
- WebAudio API integration for processing
- Time-based bar visualizer for recording feedback
- Audio level smoothing for better UX

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