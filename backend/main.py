"""
Main FastAPI application setup.
"""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import configuration
from backend.config import CORS_ORIGINS, USE_DEV_CERTS, HOST, PORT

# Import database initialization
from backend.database.db import init_db

# Import security and utilities
from backend.security.auth import cleanup_expired_sessions
from backend.utils.certificates import setup_development_certificates

# Import API routers
from backend.api import auth, docs, conversations, settings, files, messages

# Import middleware
from backend.middleware.middleware import (
    logging_middleware,
    csrf_protection_middleware,
    add_security_headers
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the lifespan of the application by performing necessary asynchronous
    tasks such as cleanup of expired sessions.

    This function ensures that the application lifecycle includes running specific
    background tasks that are necessary for maintaining the application's state or
    resources.

    :param app: FastAPI application instance to attach the lifespan context to.
    :type app: FastAPI
    :return: Async generator for managing application lifespan.
    :rtype: AsyncGenerator
    """
    asyncio.create_task(cleanup_expired_sessions())
    yield


# Setup FastAPI app
app = FastAPI(
    title="Chat API",
    version="2.0.0",
    description="This is a backend server for a chat application.",
    docs_url=None,
    redoc_url=None,
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# Initialize the database on startup
init_db()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "X-Requested-With", "Accept", "Origin"],
    expose_headers=["X-CSRF-Token", "X-Has-More-Messages", "Content-Type", "Authorization", "X-CSP-Nonce"]
)

# Add custom middleware (order matters - these run in reverse order)
app.middleware("http")(logging_middleware)
app.middleware("http")(csrf_protection_middleware)
app.middleware("http")(add_security_headers)

# Register API routers
app.include_router(auth.router)
app.include_router(conversations.router)
app.include_router(messages.router)
app.include_router(settings.router)
app.include_router(files.router)

# Register documentation routes (these need to be registered last as they use the app directly)
docs.create_docs_routes(app)

# Development certificate setup
ssl_config = {}
if USE_DEV_CERTS:
    print("Starting in development mode with auto-generated certificates...")
    cert_file, key_file = setup_development_certificates()

    print(f"""
    [SSL] Development HTTPS certificates generated!

    To trust these certificates in development:
    1. Certificate Authority (CA) file: devcerts/ca.pem (import this into your browser/system)
    2. Server certificate file: {cert_file}
    3. You might need to add an exception in your browser for localhost.
    4. For Angular development, you might need to set NODE_TLS_REJECT_UNAUTHORIZED='0' in your environment.

    [WARNING] These are self-signed certificates for development only! Do not use in production.
    """)

    ssl_config = {
        "ssl_keyfile": key_file,
        "ssl_certfile": cert_file,
    }

# Main entry point for running the Uvicorn server
if __name__ == "__main__":
    import uvicorn

    run_args = {"host": HOST, "port": PORT, "reload": True}
    if ssl_config:
        run_args.update(ssl_config)
        print(f"[SERVER] Starting server at https://{HOST}:{PORT}")
        print(f"[API] OpenAPI schema available at: https://{HOST}:{PORT}{app.openapi_url}")
        print(f"[DOCS] Swagger UI available at: https://{HOST}:{PORT}/api/docs")
    else:
        print(f"[SERVER] Starting server at http://{HOST}:{PORT}")
        print(f"[API] OpenAPI schema available at: http://{HOST}:{PORT}{app.openapi_url}")
        print(f"[DOCS] Swagger UI available at: http://{HOST}:{PORT}/api/docs")

    current_script_name = Path(__file__).stem
    uvicorn.run(f"{current_script_name}:app", **run_args)
