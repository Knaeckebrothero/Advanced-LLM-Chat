# Docker Setup

This directory contains the Docker configuration for containerizing both the Angular frontend and Python backend applications.

## Files

- **Dockerfile**: Multi-stage build configuration for the Angular frontend app
- **backend.Dockerfile**: Python FastAPI backend (the database is the Postgres container of the compose files)
- **backend-entrypoint.sh**: The backend image's entrypoint: gives the data directories to the user `app` and drops root (see [The backend's user](#the-backends-user))
- **nginx.conf**: Nginx configuration optimized for serving Angular SPA
- **docker-compose.yml**: Docker Compose configuration that builds the images and runs Postgres, the database setup (`db-init`), the backend and the frontend
- **docker-compose.prod.yml**: The same with the published images from ghcr.io
- **docker-compose.keycloak.yml**: Optional Keycloak for logging in, added to either compose file (see [Login](#login))
  (the realm it imports on its first start is shared with the Helm chart: `helm/advanced-llm-chat/files/llm-chat-realm.json`)

## Prerequisites

1. Docker and Docker Compose installed
2. A key for at least one model provider (e.g. `CORTECS_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`; the providers are in `catalog/models.json`)

## Quick Start

### 1. Set up environment variables

Copy `.env.example` to `.env` in the docker directory and fill it in (at least `POSTGRES_PASSWORD` for the prod file, and a model provider key).

Every release (a merge into `main`) also publishes a ready bundle on the GitHub releases page: `docker-compose.yml` with the release's image tag, the Keycloak file, its realm and `.env.example`. A Helm chart for Kubernetes is in `helm/advanced-llm-chat`.

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
docker build -f docker/Dockerfile -t llm-chat-frontend:latest .

# Run the frontend container
docker run -d -p 8080:80 --name llm-chat-frontend llm-chat-frontend:latest
```

### Backend Only

From the repository root:

```bash
# Build the backend image
docker build -f docker/backend.Dockerfile -t llm-chat-backend:latest .

# Run the backend container (it needs a Postgres: POSTGRES_HOST and the other POSTGRES_* settings)
docker run -d \
  -p 8443:8443 \
  -v llm-chat-files:/app/.filesystem \
  -e POSTGRES_HOST=... -e POSTGRES_PASSWORD=... \
  -e CORTECS_API_KEY=your_key_here \
  --name llm-chat-backend \
  llm-chat-backend:latest
```

The compose files are the easier way: they also create the database (`db-init`, `app_init --seed`).

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
docker pull ghcr.io/knaeckebrothero/advanced-llm-chat-frontend:develop-latest
docker pull ghcr.io/knaeckebrothero/advanced-llm-chat-backend:develop-latest

# Run with docker-compose using remote images
docker-compose -f docker-compose.prod.yml up -d
```

## Runtime Configuration

The frontend container supports runtime environment variable injection. This allows you to configure the API URL without rebuilding the image.

### How it works

1. At container startup, `envsubst` substitutes `${API_URL}` in `/assets/env.template.js`
2. The result is written to `/assets/env.js`
3. Angular loads this config before bootstrapping

nginx serves `env.js` with `Cache-Control: no-cache`, so browsers (and a CDN in front) always ask for the current address; images before 0.1.210 let them keep it for a year. The app also remembers the address in the browser, for starts without a connection.

### Deploying to a remote server

```bash
# Set the API_URL to your backend's address
API_URL=https://my-server.example.com:8443 docker-compose up -d

# Or add to .env file
echo "API_URL=https://my-server.example.com:8443" >> .env
docker-compose up -d
```

## Login

Guests can always chat. How everyone else logs in is `AUTH_MODE` (details in
[docs/authentication.md](../docs/authentication.md)):

- **No login** (the default, `AUTH_MODE=none`): guests only.
- **Your own OpenID Connect provider**, e.g. an existing Keycloak: set `AUTH_MODE=oidc` and the
  `OIDC_*` settings in `docker/.env`, and register the client there as the doc describes.
- **The bundled Keycloak**: set `KEYCLOAK_ADMIN_PASSWORD` and `OIDC_CLIENT_SECRET` in `docker/.env`
  (e.g. `openssl rand -hex 24`), then add the Keycloak compose file:

  ```bash
  docker compose -f docker-compose.yml -f docker-compose.keycloak.yml up -d
  ```

  Open the Keycloak console at http://localhost:8180 (user `admin`), switch to the realm
  `llm-chat`, create users (with "Email verified" on and a password), and give admins the
  realm role `admin`. The realm is imported on the first start only; change it in the
  console afterwards. Behind a reverse proxy, set `KEYCLOAK_URL`, `API_URL` and
  `FRONTEND_URL` to the addresses the browser uses.

`AUTH_MODE=mock` (log in with any email, no password) is for development only.

## The backend's user

The backend runs as the user `app` (uid and gid 10001), not as root. The container's first process is `tini`, which collects the processes that others leave behind (the renderer of a PDF that took too long). The container still starts as root: its entrypoint (`backend-entrypoint.sh`) gives `app` the directories the backend writes to (`/app/.filesystem` with the uploaded files, the TTS cache and logs, and `/app/devcerts`), then drops root for good and starts the backend. The image sets `FILESYSTEM_PATH=/app/.filesystem` and `FILES_DIR=/app/.filesystem/files` itself, as the compose files do.

**Upgrading from an image that ran as root** needs no manual step: on the first start the entrypoint changes the owner of the files already in the volume (or in `./data`, where they then belong to uid 10001 on the host). Later starts leave the volume alone.

- Don't set `user:` for the backend while a volume still holds root's files: started as another user, the entrypoint can't change their owner. With a new volume, `user: "10001:10001"` works.
- `docker compose exec backend ...` runs as root. Add `-u app` to commands that write files, e.g. `docker compose exec -u app backend python -m backend.services.memory_dream`; what root leaves in the volume is given to `app` at the next start.

## Container Details

### Frontend Container
- **Base Image**: nginx:alpine (lightweight)
- **Exposed Port**: 80
- **Build Process**: Multi-stage (Node.js for building, Nginx for serving)
- **Features**:
  - Gzip compression enabled
  - Static asset caching (the hashed bundles for a year; `assets/env.js`, `assets/theme-init.js` and `ngsw-worker.js` with `no-cache`)
  - Security headers, with a Content-Security-Policy that runs scripts only from the app's own files (`script-src 'self'`: no inline script, no eval)
  - SPA routing handled correctly
  - Runtime environment variable injection via `envsubst`

### Backend Container
- **Base Image**: python:3.11-slim
- **User**: `app` (uid 10001); starts as root only to hand over the data directories
- **Exposed Port**: 8443 (HTTPS)
- **Database**: Postgres (the `postgres` container, image `pgvector/pgvector:pg16`)
- **Features**:
  - Auto-generated SSL certificates
  - FastAPI with automatic API documentation
  - Session-based authentication (guests, and logins through an OIDC provider)
  - Models of OpenAI-compatible providers and Anthropic (`catalog/models.json`)

## Data Persistence

- Conversations, users, settings and the knowledge base are in Postgres, on the volume `postgres_data`. Back it up with `docker compose exec postgres pg_dump -U llm_chat -Fc llm_chat > backup.dump`.
- Uploaded files, the TTS cache and logs are on `/app/.filesystem`: `./data` with `docker-compose.yml`, the volume `filesystem_data` with `docker-compose.prod.yml`.

## Environment Variables

### Backend
All settings are described in `.env.example` (here) and the repository's `.env.example`. The main ones:
- The model providers' keys, e.g. `CORTECS_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
- `POSTGRES_PASSWORD` and the other `POSTGRES_*` settings
- `AUTH_MODE` and the `OIDC_*` settings (see [Login](#login))
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
4. Back up the Postgres volume and the files volume
5. On a server anyone can reach, set `FORWARDED_ALLOW_IPS` to the reverse proxy's address (never `*`), check the guests' limits (`GUEST_MAX_*`, `docs/authentication.md`, "Guests"), set `WHISPER_LOCAL_FALLBACK=false`, and give the model keys spending limits at the providers

## Troubleshooting

### Certificate Issues
If you get SSL errors:
1. Clear browser cache and cookies
2. Restart the backend container to regenerate certificates
3. Ensure you've accepted the certificate at https://localhost:8443

### Database Issues
If the backend can't reach the database or data isn't kept:
1. Check that the `postgres` container is healthy (`docker compose ps`) and `POSTGRES_PASSWORD` is the same for it and the backend
2. Check the logs of `db-init`, which creates the tables (`docker compose logs db-init`)
3. Uploads missing after a restart: check that `/app/.filesystem` is on a volume (see [Data Persistence](#data-persistence))

### API Connection Issues
If frontend can't reach backend:
1. Ensure both containers are on the same network
2. Check that backend is running on https://localhost:8443
3. Verify CORS settings in the backend allow frontend origin
