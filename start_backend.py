#!/usr/bin/env python3
"""
Entry point for running the backend server.

Usage:
    python start_backend.py

Or with custom options:
    python start_backend.py --host 0.0.0.0 --port 8443
"""
import argparse
import logging
import uvicorn

from backend.config import USE_DEV_CERTS, SSL_CERTFILE, SSL_KEYFILE, HOST, PORT
from backend.security.logging import get_uvicorn_log_config
from backend.utils.certificates import setup_development_certificates

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Start the Fessi backend server")
    parser.add_argument("--host", default=HOST, help=f"Host to bind to (default: {HOST})")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port to bind to (default: {PORT})")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument("--no-ssl", action="store_true", help="Disable SSL (not recommended)")
    args = parser.parse_args()

    ssl_config = {}
    protocol = "http"

    if not args.no_ssl:
        if SSL_CERTFILE and SSL_KEYFILE:
            # Use externally provided certificates
            logger.info(f"Using external SSL certificates: {SSL_CERTFILE}")
            ssl_config = {
                "ssl_keyfile": SSL_KEYFILE,
                "ssl_certfile": SSL_CERTFILE,
            }
            protocol = "https"
        elif USE_DEV_CERTS:
            # Auto-generate development certificates
            logger.info("Setting up development SSL certificates...")
            cert_file, key_file = setup_development_certificates()
            ssl_config = {
                "ssl_keyfile": key_file,
                "ssl_certfile": cert_file,
            }
            protocol = "https"

    logger.info(f"Starting server at {protocol}://{args.host}:{args.port}")
    logger.info(f"API docs available at {protocol}://{args.host}:{args.port}/api/docs")

    uvicorn.run(
        "backend.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_config=get_uvicorn_log_config(),
        **ssl_config
    )


if __name__ == "__main__":
    main()
