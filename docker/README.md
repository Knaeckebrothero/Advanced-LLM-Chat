# Docker Setup for Advanced LLM Chat

This directory contains the Docker configuration for containerizing the Angular application.

## Files

- **Dockerfile**: Multi-stage build configuration for the Angular app
- **nginx.conf**: Nginx configuration optimized for serving Angular SPA
- **docker-compose.yml**: Docker Compose configuration for easy deployment

## Building the Container

### Local Build

From the repository root:

```bash
# Build the image
docker build -f docker/Dockerfile -t advanced-llm-chat:latest .

# Run the container
docker run -d -p 8080:80 --name advanced-llm-chat advanced-llm-chat:latest
```

### Using Docker Compose

From the docker directory:

```bash
# Build and start
docker-compose up -d

# Stop
docker-compose down

# Rebuild after changes
docker-compose up -d --build
```

## Accessing the Application

Once running, the application will be available at:
- Local: http://localhost:8080

## GitHub Container Registry

The GitHub Actions workflow automatically builds and pushes images to GitHub Container Registry:

```bash
# Pull the latest develop image
docker pull ghcr.io/[your-username]/advanced-llm-chat:develop-latest

# Run it
docker run -d -p 8080:80 ghcr.io/[your-username]/advanced-llm-chat:develop-latest
```

## Environment Configuration

The container serves the production build of the Angular application. The API URL is configured in the Angular environment files before build time.

## Container Details

- **Base Image**: nginx:alpine (lightweight)
- **Exposed Port**: 80
- **Build Process**: Multi-stage (Node.js for building, Nginx for serving)
- **Optimizations**:
  - Gzip compression enabled
  - Static asset caching
  - Security headers configured
  - SPA routing handled correctly

## Backend Integration

This container only includes the Angular frontend. The backend team should:

1. Run this container alongside their backend service
2. Configure reverse proxy or CORS as needed
3. Update the API URL in the Angular environment configuration before building

## Deployment Example

For a complete deployment with backend:

```yaml
version: '3.8'

services:
  frontend:
    image: ghcr.io/knackebrothero/advanced-llm-chat:develop-latest
    ports:
      - "80:80"
    depends_on:
      - backend
    
  backend:
    image: your-backend-image
    ports:
      - "8443:8443"
    # ... other backend configuration
```
