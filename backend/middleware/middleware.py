"""
HTTP middleware for logging, CSRF protection, and security headers.
"""
import os
import time
import secrets
from fastapi import Request
from fastapi.responses import JSONResponse, Response
from backend.security.csrf import validate_csrf_token
from backend.security.logging import crud_logger
from backend.config import CORS_ORIGINS


async def logging_middleware(request: Request, call_next):
    """
    Logging middleware for detailed request and response monitoring. This middleware logs the HTTP request
    and response details for specified CRUD endpoints. It skips logging for OPTIONS requests and non-CRUD
    endpoints. Additionally, it calculates and logs request body size for POST, PATCH, and PUT methods,
    and measures the time taken to process each request.

    :param request: The incoming HTTP request object.
    :type request: Request
    :param call_next: The function that receives the request and produces a response.
    :type call_next: Callable
    :return: The HTTP response object after processing the request.
    :rtype: Response
    """
    # Skip logging for OPTIONS requests and non-CRUD endpoints
    if request.method == "OPTIONS" or (
            not request.url.path.startswith("/api/message") and not request.url.path.startswith("/api/conversation")):
        return await call_next(request)

    # Log request
    start_time = time.time()

    # Log request body size for POST/PATCH/PUT
    body_size = 0
    if request.method in ["POST", "PATCH", "PUT"]:
        # Don't read the body here as it interferes with the request processing
        # Just get the content-length header if available
        body_size = int(request.headers.get("content-length", 0))

    # Log request details
    crud_logger.info(f"Request: {request.method} {request.url.path} - Body size: {body_size} bytes")

    # Process request
    response = await call_next(request)

    # Log response
    duration = time.time() - start_time
    crud_logger.info(
        f"Response: {request.method} {request.url.path} - Status: {response.status_code} - Duration: {duration:.3f}s")

    return response


async def csrf_protection_middleware(request: Request, call_next):
    """
    Middleware to ensure CSRF protection for HTTP requests.

    This middleware validates the presence and correctness of a CSRF token for
    incoming requests, ensuring that requests requiring CSRF protection are
    rejected with an appropriate error if the validation fails. It bypasses CSRF
    checks for OPTIONS requests, which serve as CORS preflight requests. Additionally,
    on failure, necessary CORS headers are added to the error response to comply
    with cross-origin resource sharing policies.

    :param request: The incoming HTTP request to process.
    :type request: Request
    :param call_next: The next function in the middleware chain to execute.
    :type call_next: Callable[[Request], Awaitable[Response]]
    :return: The HTTP response after processing the request, with CSRF
             validation checks applied.
    :rtype: Response
    """
    # Skip CSRF for OPTIONS requests (CORS preflight)
    if request.method == "OPTIONS":
        response = await call_next(request)
        return response

    # Validate CSRF token
    if not await validate_csrf_token(request):
        response = JSONResponse(
            content={"error": "CSRF validation failed"},
            status_code=403
        )
        # Add CORS headers to error response
        origin = request.headers.get("origin")
        if origin in CORS_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    response = await call_next(request)
    return response


async def add_security_headers(request: Request, call_next):
    """
    Middleware to enhance security by adding various HTTP security headers to the response.

    This middleware dynamically generates a Content Security Policy (CSP) header with
    a nonce for each request and adjusts the CSP policy based on whether the environment
    is in development or production mode. Additionally, it sets headers to prevent MIME
    type sniffing, enable XSS protection, enforce HTTPS in production, prevent clickjacking,
    and configure permissions policies.

    :param request: The incoming HTTP request object.
    :type request: Request
    :param call_next: The next middleware or route handler in the chain.
    :type call_next: Callable
    :return: The modified HTTP response with added security headers.
    :rtype: Response
    """
    # Generate nonce for this request
    csp_nonce = secrets.token_urlsafe(16)
    request.state.csp_nonce = csp_nonce

    response = await call_next(request)

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # Enable XSS filter (legacy but still useful for older browsers)
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Force HTTPS (only in production - not when using dev certs)
    if not os.getenv("USE_DEV_CERTS", "False").lower() == "true":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # Content Security Policy
    # For Angular compatibility, we need a more permissive policy in development
    # In production, consider migrating away from unsafe-inline and unsafe-eval
    is_dev = os.getenv("USE_DEV_CERTS", "False").lower() == "true"

    # Check if this is a Swagger UI request
    is_swagger_ui = request.url.path == "/api/docs"

    if is_swagger_ui:
        # Special CSP for Swagger UI to allow CDN resources
        csp_directives = [
            "default-src 'self' https://cdn.jsdelivr.net https://fastapi.tiangolo.com",
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            "img-src 'self' data: blob: https://fastapi.tiangolo.com",
            "font-src 'self' data: https://cdn.jsdelivr.net",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'"
        ]
    elif is_dev:
        # Development CSP - more permissive for Angular CLI
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # Required for Angular dev mode
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: blob:",
            "connect-src 'self' wss: https: ws://localhost:* http://localhost:*",  # Allow dev server websockets
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'"
        ]
    else:
        # Production CSP - stricter but still Angular-compatible
        # Note: Moving to nonce-based CSP requires Angular build configuration changes
        csp_directives = [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{csp_nonce}' 'strict-dynamic'",  # Nonce-based with strict-dynamic
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",  # Styles still need unsafe-inline
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: blob:",
            "connect-src 'self' wss: https:",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "require-trusted-types-for 'script'"  # Additional XSS protection
        ]

    response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

    # Send nonce in header for Angular to use
    response.headers["X-CSP-Nonce"] = csp_nonce

    # Referrer Policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Permissions Policy (formerly Feature Policy)
    # Disable access to sensitive browser features
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    return response
