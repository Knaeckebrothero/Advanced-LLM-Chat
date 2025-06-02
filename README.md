# Advanced LLM Chat

A modern, Angular-based chat application for interacting with large language models (LLMs). This project provides a responsive interface with real-time message updates, conversation persistence, and convenient navigation between chat, metrics, and settings.

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

- Real-time chat interface with LLM integration
- Message persistence and offline support via IndexedDB
- Responsive design that works on both desktop and mobile
- Analytics dashboard for tracking conversation metrics
- Settings panel for customization
- Progressive Web App (PWA) support
- Dockerized frontend (Angular/nginx) and backend (Python/FastAPI) for easy deployment
- LLM integration via Replicate API with streaming responses
- Session-based authentication with persistent login state

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
docker pull ghcr.io/knaeckebrothero/advanced-llm-chat-frontend:develop-latest
docker pull ghcr.io/knaeckebrothero/advanced-llm-chat-backend:develop-latest

# Run with docker-compose (recommended)
wget https://raw.githubusercontent.com/knaeckebrothero/advanced-llm-chat/develop/docker/docker-compose.prod.yml
docker-compose -f docker-compose.prod.yml up -d
```

Access the application:
- Frontend: `http://localhost:8080`
- Backend API: `https://localhost:8443/api/docs`

**Important**: You'll need to accept the self-signed certificate warning at `https://localhost:8443` first.

### Using Docker Compose

For easier container management, clone the repository and use Docker Compose:

```bash
git clone https://github.com/knaeckebrothero/advanced-llm-chat.git
cd advanced-llm-chat/docker

# Create .env file
echo "REPLICATE_API_TOKEN=your_replicate_api_token_here" > .env

# Build and run locally
docker-compose up -d --build

# Or use pre-built images
docker-compose -f docker-compose.prod.yml up -d
```

### Available Image Tags

- `ghcr.io/knaeckebrothero/advanced-llm-chat-frontend:develop-latest` - Latest frontend from develop branch
- `ghcr.io/knaeckebrothero/advanced-llm-chat-backend:develop-latest` - Latest backend from develop branch
- `ghcr.io/knaeckebrothero/advanced-llm-chat-frontend:main-latest` - Latest frontend from main branch (production)
- `ghcr.io/knaeckebrothero/advanced-llm-chat-backend:main-latest` - Latest backend from main branch (production)
- `ghcr.io/knaeckebrothero/advanced-llm-chat-{frontend|backend}:sha-<commit>` - Specific commit builds

### Building Your Own Images

If you need to build the image locally with custom configurations:

```bash
# Clone the repository
git clone https://github.com/knaeckebrothero/advanced-llm-chat.git
cd advanced-llm-chat

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
cd advanced-llm-chat

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

The build artifacts will be stored in the `dist/advanced-llm-chat` directory.

### Running Tests

```bash
ng test
```

## Usage

### Chat Interface

- Type a message in the input box and press Enter or click the "SND" button to send
- Click the "GEN" button to generate a response from the LLM
- Messages are automatically saved to both the local database and the backend

### Navigation

Use the status bar to navigate between:
- Chat interface (main view)
- Metrics dashboard
- Settings panel

## Architecture

The application follows a modern microservices architecture:

```
┌─────────────────────┐         ┌─────────────────────┐
│                     │         │                     │
│   Angular PWA       │ <-----> │   FastAPI Backend   │
│   (Frontend)        │  HTTPS  │   (Python)          │
│                     │         │                     │
│  - Angular 19       │         │  - FastAPI          │
│  - TypeScript       │         │  - SQLite DB        │
│  - IndexedDB        │         │  - Replicate API    │
│  - Service Worker   │         │  - Session Auth     │
│  - nginx (Docker)   │         │  - WebSockets       │
│                     │         │                     │
└─────────────────────┘         └─────────────────────┘
      Port 8080                      Port 8443

Docker Containers:
- Frontend: nginx:alpine serving production Angular build
- Backend: python:3.11-slim running FastAPI with uvicorn
```

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
   git clone https://github.com/yourusername/advanced-llm-chat.git
   cd advanced-llm-chat
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
