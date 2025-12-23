# Docker Setup for Fessi

This directory contains the Docker configuration for containerizing both the Angular frontend and Python backend applications.

## Files

- **Dockerfile**: Multi-stage build configuration for the Angular frontend app
- **backend.Dockerfile**: Python FastAPI backend with SQLite database
- **nginx.conf**: Nginx configuration optimized for serving Angular SPA
- **docker-compose.yml**: Docker Compose configuration for running both services

## Prerequisites

1. Docker and Docker Compose installed
2. A Replicate API token for the LLM functionality (get one at https://replicate.com)

## Quick Start

### 1. Set up environment variables

Create a `.env` file in the docker directory:

```bash
# Required: At least one LLM provider
OPENAI_API_KEY=your_openai_api_key_here
# Or use Replicate
# REPLICATE_API_TOKEN=your_replicate_api_token_here

# Optional: Set API_URL if backend is on a different host
# API_URL=https://192.168.1.50:8443
```

### 2. Build and run with Docker Compose

From the docker directory:

```bash
# Build and start both services
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Building Individual Containers

### Frontend Only

From the repository root:

```bash
# Build the frontend image
docker build -f docker/Dockerfile -t fessi-frontend:latest .

# Run the frontend container
docker run -d -p 8080:80 --name fessi-frontend fessi-frontend:latest
```

### Backend Only

From the repository root:

```bash
# Build the backend image
docker build -f docker/backend.Dockerfile -t fessi-backend:latest .

# Run the backend container
docker run -d \
  -p 8443:8443 \
  -v $(pwd)/docker/data:/app/data \
  -e REPLICATE_API_TOKEN=your_token_here \
  --name fessi-backend \
  fessi-backend:latest
```

## Accessing the Application

Once running, the application will be available at:
- Frontend: http://localhost:8080
- Backend API: https://localhost:8443/api/docs (Swagger UI)

**Note**: The backend uses self-signed certificates. You'll need to:
1. Visit https://localhost:8443 and accept the certificate warning
2. Then the frontend at http://localhost:8080 will be able to communicate with the backend

## GitHub Container Registry

The GitHub Actions workflow automatically builds and pushes both images:

```bash
# Pull the latest images
docker pull ghcr.io/Knaeckebrothero/fessi-frontend:develop-latest
docker pull ghcr.io/Knaeckebrothero/fessi-backend:develop-latest

# Run with docker-compose using remote images
docker-compose -f docker-compose.prod.yml up -d
```

## Runtime Configuration

The frontend container supports runtime environment variable injection. This allows you to configure the API URL without rebuilding the image.

### How it works

1. At container startup, `envsubst` substitutes `${API_URL}` in `/assets/env.template.js`
2. The result is written to `/assets/env.js`
3. Angular loads this config before bootstrapping

### Deploying to a remote server

```bash
# Set the API_URL to your backend's address
API_URL=https://my-server.example.com:8443 docker-compose up -d

# Or add to .env file
echo "API_URL=https://my-server.example.com:8443" >> .env
docker-compose up -d
```

## Container Details

### Frontend Container
- **Base Image**: nginx:alpine (lightweight)
- **Exposed Port**: 80
- **Build Process**: Multi-stage (Node.js for building, Nginx for serving)
- **Features**:
  - Gzip compression enabled
  - Static asset caching
  - Security headers configured
  - SPA routing handled correctly
  - Runtime environment variable injection via `envsubst`

### Backend Container
- **Base Image**: python:3.11-slim
- **Exposed Port**: 8443 (HTTPS)
- **Database**: SQLite (persisted in volume)
- **Features**:
  - Auto-generated SSL certificates
  - FastAPI with automatic API documentation
  - Session-based authentication
  - Replicate AI integration

## Data Persistence

- SQLite database is stored in `./data` directory (mounted as volume)
- Sessions and messages are persisted across container restarts
- Backup the `./data` directory to preserve chat history

## Environment Variables

### Backend
- `REPLICATE_API_TOKEN`: Your Replicate API token (required for AI responses)
- `USE_DEV_CERTS`: Set to "True" to auto-generate SSL certificates
- `HOST`: Host to bind to (default: 0.0.0.0)
- `PORT`: Port to run on (default: 8443)

### Frontend
- `NODE_ENV`: Set to "production" for production builds
- `API_URL`: Backend API endpoint (default: `https://localhost:8443`). Set this to the backend's address when deploying to a remote server.

## Production Deployment

For production deployment:

1. Use proper SSL certificates instead of self-signed ones
2. Set up a reverse proxy (nginx/traefik) for both services
3. Use environment-specific configuration files
4. Consider using a more robust database than SQLite for high traffic
5. Implement proper backup strategies for the database

## Troubleshooting

### Certificate Issues
If you get SSL errors:
1. Clear browser cache and cookies
2. Restart the backend container to regenerate certificates
3. Ensure you've accepted the certificate at https://localhost:8443

### Database Issues
If the database isn't persisting:
1. Check that the `./data` directory exists and has proper permissions
2. Ensure the volume mount is correct in docker-compose.yml
3. Check container logs for any SQLite errors

### API Connection Issues
If frontend can't reach backend:
1. Ensure both containers are on the same network
2. Check that backend is running on https://localhost:8443
3. Verify CORS settings in the backend allow frontend origin
