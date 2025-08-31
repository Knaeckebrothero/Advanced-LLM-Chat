# Advanced LLM Chat

A sophisticated, Angular-based progressive web application for interacting with large language models (LLMs). Features voice recording, file uploads, offline-first architecture, internationalization, and a modern responsive interface with real-time updates and comprehensive state management.

## Table of Contents

- [Features](#features)
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
- [Troubleshooting](#troubleshooting)
  - [CORS Issues](#cors-issues)
  - [Certificate Issues](#certificate-issues)
  - [Database Connection Issues](#database-connection-issues)
  - [Backend Connection Issues](#backend-connection-issues)
  - [Docker Deployment Issues](#docker-deployment-issues)
- [Contributing](#contributing)
  - [Git Workflow](#git-workflow)
  - [Branch Structure](#branch-structure)
  - [Automated Docker Builds](#automated-docker-builds)
  - [Contribution Process](#contribution-process)
- [License](#license)
- [Contact](#contact)

## Features

### Core Chat Features
- Real-time chat interface with multiple LLM model support
- Message persistence with offline-first architecture via IndexedDB
- Streaming LLM responses with real-time updates
- Message editing, deletion, and regeneration capabilities
- Session-based authentication with guest login support

### Voice & Audio
- **Voice Recording**: Hold-to-record and tap-to-record modes
- **Audio Visualization**: Real-time waveform display during recording
- **Voice Messages**: Audio messages with duration tracking and optional transcripts
- **Offline Audio**: Base64 storage for offline voice message access

### File Management
- **Drag & Drop**: Direct file upload via drag and drop
- **Camera Integration**: Take photos directly from mobile/desktop cameras
- **Image Preview**: Full-screen image preview with popup dialogs
- **File Validation**: Type checking and 10MB size limit
- **Offline Queue**: Automatic file upload when connection restored
- **Multiple Formats**: Support for images, documents, and various file types

### User Interface
- **Responsive Design**: Adaptive layouts for desktop, tablet, and mobile
- **Dark/Light Theme**: System preference detection with manual override
- **Internationalization (i18n)**: English and German language support
- **Conversation Sidebar**: Smart grouping (Today, Last 7 Days, Older)
- **Notification System**: Animated toast notifications for user feedback
- **Progressive Web App (PWA)**: Installable with offline capabilities

### Technical Features
- **Microservices Architecture**: Dockerized frontend (Angular/nginx) and backend (FastAPI)
- **State Management**: Reactive state with RxJS observables
- **Repository Pattern**: Clean separation of data access layers
- **Offline-First**: IndexedDB with background synchronization
- **WebSocket Support**: Real-time streaming responses
- **Self-Signed SSL**: Automatic certificate generation for development

## Docker Deployment

The application is available as pre-built Docker containers from GitHub Container Registry. The application consists of two containers:
- **Frontend**: Angular application served by nginx
- **Backend**: Python FastAPI with SQLite database and LLM integration

### Prerequisites for Docker Deployment

1. Docker and Docker Compose installed
2. A Replicate API token (get one at https://replicate.com)

### Quick Start with Docker

```bash
# Create a .env file with your Replicate API token
echo "REPLICATE_API_TOKEN=your_replicate_api_token_here" > .env

# Pull and run the latest images
docker pull ghcr.io/Knaeckebrothero/Advanced-LLM-Chat-frontend:develop-latest
docker pull ghcr.io/Knaeckebrothero/Advanced-LLM-Chat-backend:develop-latest

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
git clone https://github.com/Knaeckebrothero/Advanced-LLM-Chat.git
cd Advanced-LLM-Chat/docker

# Create .env file
echo "REPLICATE_API_TOKEN=your_replicate_api_token_here" > .env

# Build and run locally
docker-compose up -d --build

# Or use pre-built images
docker-compose -f docker-compose.prod.yml up -d
```

### Available Image Tags

- `ghcr.io/Knaeckebrothero/Advanced-LLM-Chat-frontend:develop-latest` - Latest frontend from develop branch
- `ghcr.io/Knaeckebrothero/Advanced-LLM-Chat-backend:develop-latest` - Latest backend from develop branch
- `ghcr.io/Knaeckebrothero/Advanced-LLM-Chat-frontend:main-latest` - Latest frontend from main branch (production)
- `ghcr.io/Knaeckebrothero/Advanced-LLM-Chat-backend:main-latest` - Latest backend from main branch (production)
- `ghcr.io/Knaeckebrothero/Advanced-LLM-Chat-{frontend|backend}:sha-<commit>` - Specific commit builds

### Building Your Own Images

If you need to build the image locally with custom configurations:

```bash
# Clone the repository
git clone https://github.com/Knaeckebrothero/Advanced-LLM-Chat.git
cd Advanced-LLM-Chat

# Build the image
docker build -f docker/Dockerfile -t my-custom-llm-chat:latest .

# Run your custom build
docker run -d -p 8080:80 my-custom-llm-chat:latest
```

**Note**: The container serves the production-built Angular application on port 80. Make sure to configure your backend API URL in the Angular environment before building if you're creating a custom image.

## Prerequisites

Before you begin, ensure you have the following installed:

- Node.js (v16.x or higher recommended)
- npm (v8.x or higher)
- Python 3.8+ (for backend mockup)
- Angular CLI (`npm install -g @angular/cli`)
- A Replicate API token (for LLM functionality) - get one at https://replicate.com

## Installation

### Backend Setup

The project includes a Python FastAPI backend mockup for development purposes.

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

Create a `.env` file in the root directory with the following content:

```
USE_DEV_CERTS=True
REPLICATE_API_TOKEN=your_replicate_api_token_here
DB_DIR=./data
```
**Tip:** You can use the [.env.example](.env.example) file to do so.

#### 4. Run the Backend

The first time you run the backend, it will generate self-signed certificates for HTTPS:

```bash
# First run the script to generate the certificates
python backend_mockup.py
```

```bash
# Start the backend server
uvicorn backend_mockup:app --reload --host localhost --port 8443 --ssl-keyfile devcerts/server.key --ssl-certfile devcerts/server.pem
```

**Important:** You'll need to visit `https://localhost:8443` in your browser and accept the security exception for the self-signed certificate.

### Frontend Setup

#### 1. Install Dependencies

```bash
# Navigate to the project directory
cd Advanced-LLM-Chat

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

The build artifacts will be stored in the `dist/advanced-llm-chat/browser/` directory (Angular 17+ structure).

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
python backend_mockup.py    # First run generates SSL certificates
uvicorn backend_mockup:app --reload --host localhost --port 8443 \
  --ssl-keyfile devcerts/server.key --ssl-certfile devcerts/server.pem

# Docker
docker-compose up -d --build                        # Build and run locally
docker-compose -f docker-compose.prod.yml up -d     # Use pre-built images
```

## Usage

### Chat Interface

#### Text Messages
- Type messages in the input field and press Enter or click Send
- Messages are automatically saved to IndexedDB and synced with backend
- Edit or delete messages using the message menu
- Regenerate AI responses with the regenerate button

#### Voice Recording
- **Hold-to-Record**: Press and hold the microphone button
- **Tap-to-Record**: Single tap to start, tap again to stop
- Real-time audio waveform visualization during recording
- Voice messages include duration and optional transcripts
- Audio stored as base64 for offline playback

#### File Uploads
- **Drag & Drop**: Drop files directly onto the chat interface
- **File Button**: Click to select files from your device
- **Camera**: Take photos directly (mobile and desktop)
- **Image Preview**: Click images to view full-screen
- Files are queued when offline and uploaded when connected
- Maximum file size: 10MB

### Navigation

Use the bottom status bar to navigate between:
- **Chat**: Main conversation interface
- **Metrics**: Analytics and usage statistics
- **Settings**: User preferences and configuration

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

The application follows a modern microservices architecture with clean separation of concerns:

### System Architecture
```
┌─────────────────────────┐         ┌─────────────────────────┐
│   Angular PWA           │         │   FastAPI Backend       │
│   (Frontend)            │ <-----> │   (Python)              │
│                         │  HTTPS  │                         │
│  - Angular 19.2.2       │         │  - FastAPI              │
│  - TypeScript (strict)  │         │  - SQLite DB            │
│  - IndexedDB            │         │  - Replicate API        │
│  - Service Worker       │         │  - Session Auth         │
│  - NGX-Translate i18n   │         │  - WebSockets           │
│  - Angular Material     │         │  - File Handling        │
│  - nginx (Docker)       │         │  - UUID-based IDs       │
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
│   ├── chat-ui/           # Main chat interface
│   │   ├── chat-ui-inputfield/  # Text/voice input with visualization
│   │   └── chat-ui-message/     # Message rendering with markdown
│   ├── sidebar/           # Conversation list with search
│   ├── auth/              # Login components and guards
│   ├── settings/          # User configuration
│   ├── metrics/           # Analytics dashboard
│   └── status-bar/        # Connection status and navigation
├── services/              # Business logic and state management
├── repositories/          # Data access layer
├── data/objects/          # Data models and factories
└── interceptors/          # HTTP interceptors for auth

```

### Backend Architecture
```
backend_mockup.py
├── API Endpoints          # RESTful routes
├── WebSocket Handlers     # Streaming responses
├── Database Models        # SQLAlchemy models
├── Authentication         # Session management
├── File Storage           # Upload handling
└── LLM Integration        # Replicate API client
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
- **Factory Pattern**: Type-safe message creation (Message.createText, Message.createVoice)
- **Repository Pattern**: Abstraction of data access logic
- **Discriminated Unions**: Type-safe message content handling

### Docker Deployment
- **Frontend Container**: nginx:alpine serving production Angular build
- **Backend Container**: python:3.11-slim running FastAPI with uvicorn
- **Network**: Shared Docker network for inter-container communication
- **Volumes**: Persistent storage for SQLite database and uploaded files

## API Endpoints

The backend provides comprehensive REST API endpoints (all require session authentication except auth endpoints):

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

### Messages
- `POST /api/message/send` - Send a new message
- `POST /api/message/generate` - Generate AI response
- `POST /api/message/send-and-generate` - Combined endpoint for better performance
- `PATCH /api/message/patch` - Update existing message
- `DELETE /api/message/delete/{conversation_id}/{message_id}` - Delete message
- `POST /api/message/rate` - Rate message quality
- `POST /api/message/regenerate` - Regenerate AI response

### Settings & Configuration
- `GET /api/settings` - Get user settings
- `PUT /api/settings` - Update user settings
- `GET /api/llms` - List available LLM models

### File Management
- `POST /api/files/upload` - Upload files (images, documents)
- `GET /api/files/{file_id}` - Retrieve uploaded file

### WebSocket
- `WS /ws` - WebSocket connection for streaming responses

## Troubleshooting

### CORS Issues

If you encounter CORS errors:
1. Ensure the backend server is running
2. Check that the CORS origins in `backend_mockup.py` include your frontend URL
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

If you encounter database issues:
1. Check that the SQLite database file has been created
2. Ensure your user has permission to read/write to the file
3. Try deleting the file to start fresh (all data will be lost)

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
   - SQLite database is stored in `./docker/data/`
   - Ensure proper permissions: `chmod 755 ./docker/data`
   - Backup this directory to preserve chat history

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
   git clone https://github.com/Knaeckebrothero/Advanced-LLM-Chat.git
   cd Advanced-LLM-Chat
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

**Important Notes:**
- Never create branches directly from `main`
- Never merge the `develop` branch into `main` directly
- Always use a `release` branch for new releases
- For critical production bugs, create a `hotfix` branch from `main`

## License

This project is licensed under the terms of the MIT License. See the [LICENSE](LICENSE.txt) file for details.

## Contact

[Github](https://github.com/Knaeckebrothero) <br>
[Mail](mailto:OverlyGenericAddress@pm.me) <br>
