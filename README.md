# Fessi Chat Bot

**An intelligent waste disposal assistant for university campuses**

Fessi is a Progressive Web Application (PWA) designed to help campus users identify appropriate disposal methods and locations for various types of waste. Built with Angular 19.2.2 and FastAPI, this chatbot uses a LangGraph agent with Neo4j knowledge graph tools to provide accurate, context-aware responses to waste disposal queries.

## Table of Contents

- [Project Background](#project-background)
- [Features](#features)
  - [Waste Disposal Assistance](#waste-disposal-assistance)
  - [Core Chat Features](#core-chat-features)
  - [Technical Features](#technical-features)
- [Use Cases](#use-cases)
- [Docker Deployment](#docker-deployment)
  - [Prerequisites for Docker Deployment](#prerequisites-for-docker-deployment)
  - [Quick Start with Docker](#quick-start-with-docker)
  - [Using Docker Compose](#using-docker-compose)
  - [Available Image Tags](#available-image-tags)
  - [Building Your Own Images](#building-your-own-images)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
- [Development](#development)
- [Usage](#usage)
- [Architecture](#architecture)
- [API Endpoints](#api-endpoints)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
  - [Git Workflow](#git-workflow)
  - [Branch Structure](#branch-structure)
  - [Future Development Roadmap](#future-development-roadmap)
- [Development Team](#development-team)
- [License](#license)
- [Acknowledgments](#acknowledgments)

## Project Background

The effective management of waste disposal on university campuses presents significant operational challenges. With diverse waste categories ranging from everyday recyclables to hazardous laboratory materials, proper segregation requires accessible and accurate information. Fessi addresses this challenge by providing an intelligent assistant that helps users identify appropriate disposal methods and locations.

This project represents a continuation of work initiated in the previous semester with "Müll-Meister," which faced significant limitations including 58-second initialization times and monolithic backend structure. The Fessi frontend was completely redesigned from scratch using modern web development practices, implementing a microservices architecture with containerized deployment.

## Features

### Waste Disposal Assistance
- **Intelligent Query Processing**: LangGraph agent with knowledge graph tools for accurate responses
- **Multi-category Support**: Guidance for recyclables, hazardous materials, electronics, and general waste
- **Location Guidance**: Information about nearest appropriate disposal locations on campus
- **Visual Identification**: Upload images of waste items for classification assistance
- **Voice Queries**: Ask disposal questions using voice input with automatic transcription
- **Offline Functionality**: Access previous queries and basic guidance without internet

### Core Chat Features
- Real-time chat interface optimized for waste disposal queries
- Message persistence with offline-first architecture via IndexedDB
- Streaming LLM responses with contextually appropriate disposal information
- Message editing, deletion, and regeneration capabilities
- Session-based authentication with guest login support

### Voice & Audio
- **Voice Recording**: Ask waste disposal questions via voice input
- **Audio Visualization**: Real-time waveform display during recording
- **Voice Messages**: Record disposal queries with automatic transcription
- **Offline Audio**: Access recorded queries even without internet connection

### File Management
- **Waste Item Photography**: Take photos of unknown waste items for identification
- **Camera Integration**: Direct camera access for immediate waste classification
- **Image Preview**: Review uploaded waste item images
- **Drag & Drop**: Easy upload of waste item photos
- **Offline Queue**: Photos saved locally and processed when connection restored
- **Multiple Formats**: Support for various image formats for waste identification

### User Interface
- **Responsive Design**: Adaptive layouts for desktop, tablet, and mobile
- **Dark/Light Theme**: System preference detection with manual override
- **Internationalization (i18n)**: English and German language support
- **Conversation Sidebar**: Smart grouping (Today, Last 7 Days, Older)
- **Notification System**: Animated toast notifications for user feedback
- **Progressive Web App (PWA)**: Installable with offline capabilities

### Technical Features
- **Progressive Web App (PWA)**: Installable on mobile devices for on-the-go waste queries
- **Microservices Architecture**: Dockerized frontend (Angular/nginx) and backend (FastAPI)
- **LangGraph Agent**: Multi-step reasoning with Neo4j knowledge graph tools
- **Multi-Provider LLM**: Support for Replicate, OpenAI, Anthropic, and compatible endpoints
- **Neo4j Knowledge Graph**: Structured waste disposal data (categories, items, locations, FAQs)
- **State Management**: Reactive state with RxJS observables
- **Repository Pattern**: Clean separation of data access layers
- **Offline-First**: IndexedDB with background synchronization
- **Vision Support**: Image analysis via multimodal models or separate vision helper
- **Audio Transcription**: Whisper API or local model for voice queries

## Use Cases

### Campus Scenarios
- **Laboratory Waste**: Identify proper disposal for chemical containers and lab equipment
- **Electronic Waste**: Find e-waste collection points for old devices
- **Cafeteria Waste**: Sort food packaging and organic waste correctly
- **Office Materials**: Dispose of paper, batteries, and office supplies appropriately
- **Special Events**: Handle event-specific waste during campus activities
- **Visitor Assistance**: Help campus visitors understand waste disposal rules

## Docker Deployment

Fessi is deployed as containerized microservices for easy campus-wide deployment. The application consists of two containers:
- **Frontend**: Angular-based Fessi interface served by nginx
- **Backend**: Python FastAPI with waste disposal knowledge base and LLM integration

### Prerequisites for Docker Deployment

1. Docker and Docker Compose installed
2. An LLM API token (one of the following):
   - Replicate API token (https://replicate.com) - default provider
   - OpenAI API key (https://platform.openai.com) - or compatible endpoint (llama.cpp, Ollama, etc.)
   - Anthropic API key (https://console.anthropic.com)

### Quick Start with Docker

```bash
# Create a .env file with your Replicate API token
echo "REPLICATE_API_TOKEN=your_replicate_api_token_here" > .env

# Pull and run the latest Fessi images
docker pull ghcr.io/fra-uas/fessi-chatbot-frontend:develop-latest
docker pull ghcr.io/fra-uas/fessi-chatbot-backend:develop-latest

# Run with docker-compose (recommended)
wget https://raw.githubusercontent.com/Knaeckebrothero/Advanced-LLM-Chat/develop/docker/docker-compose.prod.yml
docker-compose -f docker-compose.prod.yml up -d
```

Access the application:
- Frontend: `http://localhost:8080`
- Backend API: `https://localhost:8443/api/docs`

**Important**: You'll need to accept the self-signed certificate warning at `https://localhost:8443` first.

### Using Docker Compose

For easier container management, clone the repository and use Docker Compose:

```bash
git clone https://github.com/fra-uas/fessi-chatbot.git
cd fessi-chatbot/docker

# Create .env file
echo "REPLICATE_API_TOKEN=your_replicate_api_token_here" > .env

# Build and run locally
docker-compose up -d --build

# Or use pre-built images
docker-compose -f docker-compose.prod.yml up -d
```

### Available Image Tags

- `ghcr.io/fra-uas/fessi-chatbot-frontend:develop-latest` - Latest Fessi frontend from develop branch
- `ghcr.io/fra-uas/fessi-chatbot-backend:develop-latest` - Latest Fessi backend from develop branch
- `ghcr.io/fra-uas/fessi-chatbot-frontend:main-latest` - Latest Fessi frontend from main branch (production)
- `ghcr.io/fra-uas/fessi-chatbot-backend:main-latest` - Latest Fessi backend from main branch (production)
- `ghcr.io/fra-uas/fessi-chatbot-{frontend|backend}:sha-<commit>` - Specific commit builds

### Building Your Own Images

If you need to build the image locally with custom configurations:

```bash
# Clone the Fessi repository
git clone https://github.com/fra-uas/fessi-chatbot.git
cd fessi-chatbot

# Build the Fessi image
docker build -f docker/Dockerfile -t fessi-custom:latest .

# Run your custom build
docker run -d -p 8080:80 my-custom-llm-chat:latest
```

**Note**: The container serves the production-built Angular application on port 80. Make sure to configure your backend API URL in the Angular environment before building if you're creating a custom image.

## Prerequisites

Before you begin, ensure you have the following installed:

- Node.js (v16.x or higher recommended)
- npm (v8.x or higher)
- Python 3.8+ (for backend)
- Angular CLI (`npm install -g @angular/cli`)
- Docker and Docker Compose (for PostgreSQL and Neo4j databases)
- An LLM API token (Replicate, OpenAI, or Anthropic) - see `.env.example` for options

## Local Development Setup

### Quick Start (Recommended)

1. **Clone and setup environment**
   ```bash
   git clone https://github.com/fra-uas/fessi-chatbot.git
   cd fessi-chatbot
   cp .env.example .env
   # Edit .env and add your REPLICATE_API_TOKEN
   ```

2. **Start PostgreSQL database**
   ```bash
   cd docker
   docker-compose up -d postgres
   cd ..
   ```

3. **Initialize the backend**
   ```bash
   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # Windows: .\venv\Scripts\activate

   # Install dependencies
   pip install -r requirements.txt

   # Initialize database and filesystem
   python backend/app_init.py --seed
   ```

4. **Start the backend**
   ```bash
   python start_backend.py --reload
   ```

5. **Start the frontend** (in a new terminal)
   ```bash
   npm install
   npm start
   ```

6. **Access the application**
   - Frontend: `https://localhost:4200`
   - Backend API: `https://localhost:8443/api/docs`
   - Accept the self-signed certificate warning at `https://localhost:8443` first

### Database Commands

```bash
# Start PostgreSQL only
cd docker && docker-compose up -d postgres

# Stop PostgreSQL
cd docker && docker-compose stop postgres

# View PostgreSQL logs
docker logs fessi-postgres

# Reset database (deletes all data)
cd docker && docker-compose down -v postgres
docker-compose up -d postgres
python backend/app_init.py --force-reset --seed

# Production migration (update schema without losing data)
python backend/app_init.py --prod
```

#### Production Migration (`--prod`)

The `--prod` flag performs a safe, additive-only schema migration:

- **Creates** missing tables (via `CREATE TABLE IF NOT EXISTS`)
- **Adds** missing columns to existing tables (via `ALTER TABLE ADD COLUMN IF NOT EXISTS`)
- **Never deletes** tables, columns, or data
- **Skips Neo4j** automatically (Neo4j is managed separately in production)
- **Warns** about orphaned columns or changes requiring manual migration

This is ideal for production deployments where you need to update the schema without losing existing data:

```bash
# Safe production upgrade
python backend/app_init.py --prod

# Flags can be combined (execute in order: --prod -> --force-reset -> --seed)
python backend/app_init.py --prod --seed  # Migrate schema, then add test data
```

## Installation

### Backend Setup

The project uses a modular Python FastAPI backend with a clean architecture.

#### 1. Create a Virtual Environment

**Windows:**
```bash
python -m venv venv
.\venv\Scripts\activate
```

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

#### 2. Install Dependencies

Install the dependencies listed in `requirements.txt`

```bash
pip install -r requirements.txt
```

#### 3. Create .env File

Copy `.env.example` to `.env` and configure your settings:

```bash
cp .env.example .env
```

Required settings:
```
USE_DEV_CERTS=True

# PostgreSQL Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=fessi_chat
POSTGRES_USER=fessi
POSTGRES_PASSWORD=fessi_dev_password

# LLM Provider - choose one:
REPLICATE_API_TOKEN=your_token    # Default provider
# OR
OPENAI_API_KEY=your_key           # For OpenAI or compatible endpoints
# OPENAI_BASE_URL=http://localhost:8080/v1  # For llama.cpp, Ollama, etc.
```

Optional settings (see `.env.example` for full list):
- **Tavily**: Web search tool for the agent (`TAVILY_API_KEY`)
- **Neo4j**: Knowledge graph for waste disposal data
- **Vision**: Image analysis configuration
- **Whisper**: Audio transcription (API or local model)

#### 4. Run the Backend

Use the `start_backend.py` entry point script to run the backend server:

```bash
# Start the backend server (auto-generates SSL certificates on first run)
python start_backend.py

# With auto-reload for development
python start_backend.py --reload

# Custom host/port
python start_backend.py --host 0.0.0.0 --port 8443

# Disable SSL (not recommended)
python start_backend.py --no-ssl
```

**Important:** You'll need to visit `https://localhost:8443` in your browser and accept the security exception for the self-signed certificate.

### Frontend Setup

#### 1. Install Dependencies

```bash
# Navigate to the Fessi project directory
cd fessi-chatbot

# Install required packages
npm install
```

#### 2. Configure Environment

Ensure the API URL in `src/app/environments/environment.ts` points to your running backend:

```typescript
export const environment = {
    production: false,
    apiUrl: 'https://localhost:8443'
};
```

#### 3. Start the Development Server

```bash
ng serve
```

The application will be available at `http://localhost:4200`.

## Development

### Working with Angular Components

The project is structured with the following key components:

- `ChatUiComponent` - Main chat interface
- `MetricsComponent` - Analytics dashboard
- `SettingsComponent` - User settings
- `StatusBarComponent` - Navigation between views

### Building for Production

```bash
ng build --configuration production
```

The build artifacts will be stored in the `dist/fessi/browser/` directory (Angular 19+ structure).

### Running Tests

```bash
# Run all unit tests with Karma/Jasmine
ng test

# Run specific test file
ng test --include='**/specific.spec.ts'

# Type checking (no ESLint configured, uses TypeScript strict mode)
npx tsc --noEmit
```

### Development Commands

```bash
# Frontend
npm start              # Start dev server (http://localhost:4200)
npm run build          # Production build
npm run watch          # Build with watch mode
ng serve               # Alternative dev server command

# Backend (Python)
python start_backend.py           # Start backend server with SSL
python start_backend.py --reload  # With auto-reload for development

# Docker
docker-compose up -d --build                        # Build and run locally
docker-compose -f docker-compose.prod.yml up -d     # Use pre-built images
```

## Usage

### Waste Disposal Queries

#### Text Queries
- Type your waste disposal question (e.g., "Where do I dispose of batteries?")
- Receive immediate guidance on proper disposal methods and locations
- All queries are saved for offline reference
- Edit or refine your questions for better responses

#### Voice Queries
- **Ask Verbally**: "How do I dispose of chemical waste from the lab?"
- **Hold-to-Record**: Press and hold the microphone button
- **Tap-to-Record**: Single tap to start, tap again to stop
- Voice queries are transcribed and processed for waste guidance
- Previous voice queries available offline

#### Visual Waste Identification
- **Take Photo**: Capture unknown waste items with your camera
- **Upload Image**: Select existing photos of waste items
- **Drag & Drop**: Drop waste item images for quick identification
- **Get Classification**: Receive disposal guidance based on visual analysis
- Images are processed when connection is available
- Maximum file size: 10MB

### Navigation

Use the bottom status bar to navigate between:
- **Chat**: Main waste disposal query interface
- **Metrics**: Campus waste disposal statistics and trends
- **Settings**: Language preferences and notification settings

### Conversation Management
- **Sidebar**: Access all conversations, grouped by date
- **Search**: Find conversations by content
- **Create New**: Start fresh conversations
- **Delete**: Remove conversations (with confirmation)

### Internationalization
- Switch between English and German in Settings
- Language preference is saved per user
- All UI elements support translation

## Architecture

Fessi follows a modern microservices architecture optimized for campus-wide deployment and offline functionality:

### System Architecture
```
┌─────────────────────────┐         ┌─────────────────────────┐
│   Fessi Frontend        │         │   Waste Backend         │
│   (Angular PWA)         │ <-----> │   (FastAPI + LangGraph) │
│                         │  HTTPS  │                         │
│  - Angular 19.2.2       │         │  - FastAPI              │
│  - TypeScript (strict)  │         │  - PostgreSQL DB        │
│  - IndexedDB            │         │  - Neo4j Knowledge Graph│
│  - Service Worker       │         │  - LangGraph Agent      │
│  - NGX-Translate i18n   │         │  - Multi-Provider LLM   │
│  - Angular Material     │         │  - Session Auth         │
└─────────────────────────┘         └─────────────────────────┘
        Port 8080                         Port 8443
```

### Frontend Architecture

#### Service Layers
- **State Management Services**: Reactive state with RxJS
  - `ChatStateService`: Manages conversations, messages, and chat operations
  - `UIStateService`: Handles UI state (sidebar, responsive behavior)
  - `SettingsStateService`: User preferences with theme integration

- **Core Services**: Business logic and data management
  - `ApiService`: Backend communication with retry logic and interceptors
  - `AuthService`: Authentication state and session management
  - `DbService`: IndexedDB operations for offline storage
  - `ThemeService`: Theme management and system preference detection
  - `VoiceRecordingService`: WebAudio API integration for voice messages
  - `FileHandlingService`: File upload, validation, and offline queue
  - `NotificationService`: User feedback with toast notifications

- **Repository Pattern**: Clean data access layer
  - `ConversationRepository`: Conversation CRUD with caching
  - `MessageRepository`: Message operations with offline queue
  - `SettingsRepository`: Settings persistence
  - `SyncEngineService`: Data synchronization between IndexedDB and backend

#### Component Organization
```
src/app/
├── components/
│   ├── chat-ui/           # Waste query interface
│   │   ├── chat-ui-inputfield/  # Text/voice/image input for waste queries
│   │   └── chat-ui-message/     # Disposal guidance rendering
│   ├── sidebar/           # Query history and categories
│   ├── auth/              # Campus user authentication
│   ├── settings/          # Language and preferences
│   ├── metrics/           # Waste disposal analytics
│   └── status-bar/        # Connection status and navigation
├── services/              # Waste query processing and state
├── repositories/          # Data access layer
├── data/objects/          # Waste category models
└── interceptors/          # HTTP interceptors for auth

```

### Backend Architecture

The backend follows a modular architecture for maintainability and scalability:

```
backend/
├── main.py                # FastAPI application entry point
├── config.py              # Configuration constants and settings
├── app_init.py            # Application initialization script (filesystem, SSL, DB)
├── api/                   # API route handlers
│   ├── auth.py            # Authentication endpoints
│   ├── conversations.py   # Conversation CRUD operations
│   ├── messages.py        # Message handling and SSE streaming
│   ├── settings.py        # User settings endpoints
│   ├── files.py           # File upload handling
│   └── docs.py            # API documentation routes
├── database/
│   ├── db.py              # SQLAlchemy engine and connection pool setup
│   ├── db_init.py         # Database initialization and migration script
│   ├── tables.py          # SQLAlchemy Core table definitions
│   ├── neo4j_db.py        # Neo4j knowledge graph manager
│   ├── neo4j_init.py      # Neo4j initialization script
│   └── queries/           # SQL query files
├── models/                # Pydantic request/response models
├── services/
│   ├── llm.py             # Replicate API integration
│   ├── llm_provider.py    # Multi-provider LLM abstraction (OpenAI, Anthropic, Replicate)
│   ├── agent.py           # LangGraph agent with multi-step reasoning
│   ├── neo4j_service.py   # Neo4j graph database operations
│   ├── image_handler.py   # Image/document processing for vision models
│   └── tools/             # LangChain tools for knowledge graph queries
├── security/              # Auth, CSRF, logging
├── middleware/            # Request/response middleware
└── utils/                 # Certificates, hashing

start_backend.py           # Entry point script for running the server
```

### Data Flow
```
Component → State Service → Repository → API Service → Backend
                 ↓              ↓
                 └──→ DBService (IndexedDB)
```

### Key Design Patterns
- **Offline-First**: All data stored in IndexedDB, synced when online
- **Observable Pattern**: RxJS for async operations and state management
- **Guard Pattern**: Route protection via AuthGuard
- **Interceptor Pattern**: Automatic auth header injection
- **Factory Pattern**: Type-safe message creation (Message.createText, Message.createAgent)
- **Repository Pattern**: Abstraction of data access logic
- **Discriminated Unions**: Type-safe message content handling

### Docker Deployment
- **Frontend Container**: nginx:alpine serving production Angular build
- **Backend Container**: python:3.11-slim running FastAPI with uvicorn
- **PostgreSQL Container**: PostgreSQL 15 for persistent data storage
- **Neo4j Container**: Neo4j for knowledge graph (waste categories, disposal methods, locations)
- **Network**: Shared Docker network for inter-container communication
- **Volumes**: Persistent storage for database data and uploaded files

## API Endpoints

The Fessi backend provides REST API endpoints optimized for waste disposal queries (all require session authentication except auth endpoints):

### Authentication
- `POST /api/auth/mock-login` - Mock login for development
- `POST /api/auth/guest-login` - Guest access without credentials
- `POST /api/auth/logout` - End current session
- `GET /api/auth/me` - Get current user information

### Conversations
- `GET /api/conversations` - List all user conversations
- `POST /api/conversation/create` - Create new conversation
- `GET /api/conversation/messages/{id}/{timestamp}/{count}` - Get paginated messages
- `DELETE /api/conversation/{id}` - Delete conversation

### Waste Queries
- `POST /api/message/send` - Submit waste disposal query
- `POST /api/message/generate` - Generate disposal guidance via LangGraph agent
- `GET /api/message/stream-generate` - SSE endpoint for streaming agent responses with reasoning steps
- `POST /api/message/send-and-generate` - Combined query and response
- `PATCH /api/message/patch` - Update/refine query
- `DELETE /api/message/delete/{conversation_id}/{message_id}` - Delete query
- `POST /api/message/rate` - Rate guidance quality
- `POST /api/message/regenerate` - Get alternative disposal guidance

### Settings & Configuration
- `GET /api/settings` - Get user settings
- `PUT /api/settings` - Update user settings
- `GET /api/llms` - List available LLM models

### Waste Image Processing
- `POST /api/files/upload` - Upload waste item images for identification
- `GET /api/files/{file_id}` - Retrieve uploaded waste images

### Agent Streaming (SSE)
The `/api/message/stream-generate` endpoint uses Server-Sent Events with these event types:
- `message_start` - Message metadata (messageId, conversationId, roleName, time, type)
- `step` - Agent reasoning step (thought, tool_call, tool_result, observation)
- `token` - Individual text tokens for the final response
- `done` - Signals completion
- `error` - Error information

## Troubleshooting

### CORS Issues

If you encounter CORS errors:
1. Ensure the backend server is running
2. Check that the CORS origins in `backend/config.py` include your frontend URL
3. Make sure you're using HTTPS for both frontend and backend

### Certificate Issues

For development with self-signed certificates:

**Windows:**
```bash
# Set environment variable to bypass certificate validation (DEVELOPMENT ONLY)
set NODE_TLS_REJECT_UNAUTHORIZED=0
```

**macOS/Linux:**
```bash
export NODE_TLS_REJECT_UNAUTHORIZED=0
```

**Important:** Only use this setting in development, never in production.

### Database Connection Issues

1. **Check PostgreSQL is running**:
   ```bash
   cd docker && docker-compose ps postgres
   ```

2. **Check logs**:
   ```bash
   docker logs fessi-postgres
   ```

3. **Verify connection**:
   ```bash
   docker exec -it fessi-postgres psql -U fessi -d fessi_chat -c "SELECT 1"
   ```

4. **Reset database**:
   ```bash
   cd docker && docker-compose down -v postgres
   docker-compose up -d postgres
   python backend/app_init.py --force-reset --seed
   ```

### Backend Connection Issues

If the frontend cannot connect to the backend:
1. Ensure both Docker containers are running: `docker ps`
2. Accept the self-signed certificate by visiting `https://localhost:8443` directly
3. Check that both containers are on the same network: `docker network inspect docker_app-network`
4. Verify the backend logs: `docker logs advanced-llm-chat-backend`

### Docker Deployment Issues

1. **Replicate API errors**:
   - Ensure your `REPLICATE_API_TOKEN` is set correctly in the `.env` file
   - Check backend logs for API errors: `docker logs advanced-llm-chat-backend`

2. **Database persistence**:
   - PostgreSQL data is stored in a Docker volume (`postgres_data`)
   - Backup with: `docker exec fessi-postgres pg_dump -U fessi fessi_chat > backup.sql`
   - Restore with: `docker exec -i fessi-postgres psql -U fessi fessi_chat < backup.sql`

3. **Port conflicts**:
   - Frontend runs on port 8080, backend on 8443
   - Change ports in `docker-compose.yml` if needed

## Contributing

This project follows the Git Flow workflow. For detailed information about our branching strategy, please refer to the [Git Flow](GitFlow.pdf) documentation included in the repository.

### Git Workflow

The project implements a strict Git Flow workflow with automated deployment through GitHub Actions.

### Branch Structure

* **`main`**: Production branch
  * Protected branch - direct pushes not allowed
  * When changes are merged into `main`, a GitHub Actions workflow automatically:
    * Builds the Angular application
    * Pushes the build artifacts to the `gh-pages` branch
    * Triggers redeployment of the application
  * Always contains stable, production-ready code

* **`develop`**: Primary development branch
  * Protected branch - requires pull request approval
  * All feature development is integrated here first
  * Pull requests require at least one approval from someone other than the author
  * Used for testing features together before release

* **`feature/*`**: Feature development branches
  * Created from and merged back into `develop`
  * No protection rules - developers can push directly
  * Used for implementing new features or fixing non-critical bugs
  * Example: `feature/user-authentication`, `feature/chat-ui-improvements`

* **`release/*`**: Release preparation branches
  * Created from `develop` when preparing for a release
  * Used for final testing and bug fixes before production
  * Merged into both `main` (to release) and `develop` (to incorporate fixes)
  * Example: `release/v1.2.0`

* **`hotfix/*`**: Production emergency fix branches
  * Created from `main` when critical bugs are found in production
  * Merged back into both `main` and `develop`
  * Example: `hotfix/critical-auth-issue`

* **`gh-pages`**: Deployment branch
  * Protected branch - only updated by the GitHub Actions workflow
  * Contains the built application that is deployed to GitHub Pages
  * Automatically updated when changes are merged to `main`

### Automated Docker Builds

When changes are pushed to `develop` or `main` branches, GitHub Actions automatically:
- Builds both frontend and backend Docker images
- Pushes them to GitHub Container Registry
- Tags them appropriately (develop-latest, main-latest, or sha-<commit>)
- Creates deployment artifacts for easy server deployment

### Contribution Process

1. **Clone the repository**
   ```bash
   git clone https://github.com/fra-uas/fessi-chatbot.git
   cd fessi-chatbot
   ```

2. **Set up your development environment**
   ```bash
   # Make sure you have the develop branch
   git checkout develop
   git pull origin develop

   # Install dependencies
   npm install
   ```

3. **Create a feature branch**
   ```bash
   # Always branch from develop, NOT main
   git checkout -b feature/your-feature-name develop
   ```

4. **Develop your feature**
  - Make your changes, following the project's coding standards
  - Commit frequently with clear, descriptive messages
   ```bash
   git commit -m "Add feature: detailed description of changes"
   ```

5. **Keep your branch updated**
   ```bash
   # Regularly sync with develop to minimize merge conflicts
   git checkout develop
   git pull origin develop
   git checkout feature/your-feature-name
   git merge develop
   # Resolve any conflicts that arise
   ```

6. **Push your feature branch**
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Create a pull request**
  - Go to the repository on GitHub
  - Create a pull request from your feature branch to the `develop` branch
  - Provide a clear description of your changes
  - Request reviews from team members
  - Address any feedback or issues raised during review

8. **After approval and merge**
  - Once your PR is approved and merged into `develop`
  - Delete your feature branch (can be done through GitHub or locally)
   ```bash
   git checkout develop
   git pull origin develop
   git branch -d feature/your-feature-name
   ```

### Future Development Roadmap

#### Immediate Enhancements
- Backend integration with campus waste management systems
- GPS implementation for nearest waste bin navigation
- QR code scanning for bin identification
- Enhanced multi-language support beyond English and German

#### Long-term Goals
- Integration with university facility management
- Real-time waste bin capacity monitoring
- Gamification of proper waste disposal
- Campus-wide waste reduction analytics

**Important Notes:**
- This is an ongoing university project with planned semester updates
- New teams should refer to the comprehensive handover documentation
- Always coordinate with the FRA UAS IT department for deployment

## Development Team

### 2025 Summer Semester Team
Fessi was developed as a collaborative effort across multiple specialized teams:

- **Frontend Team**: Angular PWA development and UI implementation
- **Backend Team**: API development and system integration
- **Design Team**: User interface and experience design
- **Data Preparation Team**: Waste categorization and knowledge base
- **Pipeline Team**: RAG architecture and LLM integration

### Project Context
Developed at Frankfurt University of Applied Sciences (FRA UAS) as part of the campus sustainability initiative. The project demonstrates the application of modern web technologies to solve real-world environmental challenges.

## License

This project is licensed under the terms of the MIT License. See the [LICENSE](LICENSE.txt) file for details.

## Acknowledgments

- **Frankfurt University of Applied Sciences** for supporting this sustainability initiative
- **Previous Semester Team** for the foundational "Müll-Meister" work
- **Design Team** for creating an intuitive user interface
- **All Team Members** who contributed to making campus waste disposal more accessible
- **Campus Community** for providing feedback and use cases

### Documentation
For detailed technical documentation and handover materials, refer to:
- [Frontend Documentation](Documentation_Project_DS.pdf)
- [Project Handover Guide](CLAUDE.md)
- [Git Flow Documentation](GitFlow.pdf)

### Contact
For questions about the Fessi project or campus deployment:
- **Project Repository**: [GitHub - Fessi Chatbot](https://github.com/fra-uas/fessi-chatbot)
- **University**: Frankfurt University of Applied Sciences
- **Department**: Computer Science and Engineering
