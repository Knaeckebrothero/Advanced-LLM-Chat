"""
Main FastAPI application setup.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import configuration
from backend.config import CORS_ORIGINS, USE_DEV_CERTS, SSL_CERTFILE, SSL_KEYFILE, HOST, PORT

# Import logging module to initialize centralized logging
# This must happen before other backend imports that use logging
import backend.security.logging  # noqa: F401

logger = logging.getLogger(__name__)

# Import database
from backend.database import db

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
    tasks such as cleanup of expired sessions and database initialization/shutdown.

    This function ensures that the application lifecycle includes running specific
    background tasks that are necessary for maintaining the application's state or
    resources.

    :param app: FastAPI application instance to attach the lifespan context to.
    :type app: FastAPI
    :return: Async generator for managing application lifespan.
    :rtype: AsyncGenerator
    """
    # Initialize database tables
    db.init_tables()

    # Start background cleanup task
    asyncio.create_task(cleanup_expired_sessions())

    yield

    # Shutdown: close database connections
    db.close_all()


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

# SSL/TLS certificate setup
ssl_config = {}
if SSL_CERTFILE and SSL_KEYFILE:
    # Use externally provided certificates (production or shared volume)
    logger.info(f"Using external SSL certificates: {SSL_CERTFILE}")
    ssl_config = {
        "ssl_keyfile": SSL_KEYFILE,
        "ssl_certfile": SSL_CERTFILE,
    }
elif USE_DEV_CERTS:
    # Auto-generate development certificates
    logger.info("Starting in development mode with auto-generated certificates...")
    cert_file, key_file = setup_development_certificates()

    logger.info("Development HTTPS certificates generated!")
    logger.info(f"CA file: devcerts/ca.pem (import into browser/system to trust)")
    logger.info(f"Server certificate: {cert_file}")
    logger.warning("Self-signed certificates for development only! Do not use in production.")

    ssl_config = {
        "ssl_keyfile": key_file,
        "ssl_certfile": cert_file,
    }

# Main entry point for running the Uvicorn server
if __name__ == "__main__":
    import uvicorn
    from backend.security.logging import get_uvicorn_log_config

    run_args = {
        "host": HOST,
        "port": PORT,
        "reload": True,
        "log_config": get_uvicorn_log_config(),
    }
    protocol = "https" if ssl_config else "http"
    if ssl_config:
        run_args.update(ssl_config)

    logger.info(f"Starting server at {protocol}://{HOST}:{PORT}")
    logger.info(f"OpenAPI schema available at: {protocol}://{HOST}:{PORT}{app.openapi_url}")
    logger.info(f"Swagger UI available at: {protocol}://{HOST}:{PORT}/api/docs")

    current_script_name = Path(__file__).stem
    uvicorn.run(f"{current_script_name}:app", **run_args)
