# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an Angular 19.2.2 application with a FastAPI backend for an advanced LLM chat interface. The project uses a microservices architecture with separate frontend and backend containers, supports multiple LLM models, and includes offline-first capabilities with IndexedDB.

## Essential Commands

### Frontend Development
```bash
npm start          # Start development server with SSL (https://localhost:4200)
npm run build      # Production build (outputs to dist/advanced-llm-chat/browser/)
npm test           # Run unit tests with Karma/Jasmine
npm run watch      # Build with watch mode for development
ng test --include='**/specific.spec.ts'  # Run specific test file
```

### Backend Development
```bash
# First run generates SSL certificates
python backend_mockup.py

# Start backend server
uvicorn backend_mockup:app --reload --host localhost --port 8443 --ssl-keyfile devcerts/server.key --ssl-certfile devcerts/server.pem
```

### Docker Development
```bash
docker-compose up -d --build              # Build and run locally
docker-compose -f docker-compose.prod.yml up -d  # Use pre-built images from ghcr.io
```

## Architecture Overview

### Frontend Structure
The Angular app follows a service-oriented architecture with clear separation of concerns:

- **Services** handle business logic and data management:
  - `ApiService`: Backend communication with retry logic
  - `AuthService`: Authentication state and session management
  - `ChatService`: Message handling and LLM interactions
  - `DbService`: IndexedDB operations for offline storage
  - `SettingsService`: User preferences and configuration

- **Components** are organized by feature:
  - `chat-ui/`: Main chat interface with input field and message display
  - `sidebar/`: Conversation list management
  - `auth/`: Login and authentication guards
  - `settings/`: User configuration interface

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

1. **TypeScript Strict Mode**: All code must pass strict TypeScript checks
2. **Angular Material**: Use existing Material components for UI consistency
3. **IndexedDB Schema**: Database operations go through `DbService` - never access IndexedDB directly
4. **Authentication**: All API calls require session authentication via `AuthInterceptor`
5. **Environment Variables**: Use Angular environments for configuration, not process.env
6. **SSL Required**: Both frontend and backend require HTTPS - certificates auto-generated in development
7. **Build Output**: Production builds output to `dist/advanced-llm-chat/browser/` (Angular 17+ pattern)
8. **No Linting**: Project relies on TypeScript strict mode only - no ESLint/TSLint configured

## Testing Approach

- Unit tests use Karma/Jasmine framework
- Test files are co-located with components (`.spec.ts`)
- Run specific tests: `ng test --include='**/specific-component.spec.ts'`
- Backend tests would use pytest (not currently implemented)

## API Endpoints

The backend provides these main endpoints (all require session authentication):
- **Auth**: `/api/auth/mock-login`, `/api/auth/guest-login`, `/api/auth/logout`, `/api/auth/me`
- **Conversations**: `/api/conversations`, `/api/conversation/create`, `/api/conversation/messages/{id}/{timestamp}/{count}`
- **Messages**: `/api/message/send`, `/api/message/generate`, `/api/message/patch`, `/api/message/delete/{conversation_id}/{message_id}`
- **Settings**: `/api/settings` (GET/PUT)
- **LLMs**: `/api/llms` (list available models)