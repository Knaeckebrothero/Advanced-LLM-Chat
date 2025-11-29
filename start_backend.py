#!/usr/bin/env python3
"""
Entry point for running the backend server.

Usage:
    python start_backend.py

Or with custom options:
    python start_backend.py --host 0.0.0.0 --port 8443
"""
import argparse
import uvicorn

from backend.config import USE_DEV_CERTS, HOST, PORT
from backend.utils.certificates import setup_development_certificates


def main():
    parser = argparse.ArgumentParser(description="Start the Fessi backend server")
    parser.add_argument("--host", default=HOST, help=f"Host to bind to (default: {HOST})")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port to bind to (default: {PORT})")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument("--no-ssl", action="store_true", help="Disable SSL (not recommended)")
    args = parser.parse_args()

    ssl_config = {}
    protocol = "http"

    if USE_DEV_CERTS and not args.no_ssl:
        print("Setting up development SSL certificates...")
        cert_file, key_file = setup_development_certificates()
        ssl_config = {
            "ssl_keyfile": key_file,
            "ssl_certfile": cert_file,
        }
        protocol = "https"

    print(f"Starting server at {protocol}://{args.host}:{args.port}")
    print(f"API docs available at {protocol}://{args.host}:{args.port}/api/docs")

    uvicorn.run(
        "backend.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        **ssl_config
    )


if __name__ == "__main__":
    main()
