"""
CSRF (Cross-Site Request Forgery) protection.
"""
import logging
import secrets
from fastapi import Request
from backend.security.logging import log_security_event

log = logging.getLogger(__name__)


def generate_csrf_token() -> str:
    """
    Generates a secure random CSRF token.

    This function leverages the `secrets` module to generate a cryptographically
    secure, URL-safe token that can be used as a CSRF (Cross-Site Request Forgery)
    token in web applications. The generated token has high entropy and is suitable
    for security-sensitive contexts to protect against CSRF attacks.

    :return: A cryptographically secure, URL-safe token for CSRF protection
    :rtype: str
    """
    return secrets.token_urlsafe(32)


async def validate_csrf_token(request: Request) -> bool:
    """
    Validates the CSRF token submitted via the HTTP request. This function
    implements CSRF protection using the double-submit pattern, ensuring requests
    are authorized and preventing cross-site request forgery attacks. Specifically,
    it checks if the CSRF token provided in the request header matches the CSRF
    token stored in the cookie. Additionally, it bypasses CSRF validation for
    certain safe HTTP methods and specific authentication endpoints.

    :param request: The incoming HTTP request object containing data related to
        headers, method, URL, and cookies.
    :type request: Request
    :return: A boolean value indicating whether the CSRF token validation passed
        or failed. Returns True if validation bypass conditions are met or if
        tokens match; otherwise, returns False.
    :rtype: bool
    """
    # Skip CSRF validation for safe methods
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        log.debug(f"CSRF skipped for safe method: {request.method} {request.url.path}")
        return True

    # Skip CSRF validation for authentication endpoints
    if request.url.path in ["/api/auth/mock-login", "/api/auth/guest-login", "/api/auth/logout",
                            "/api/auth/refresh-session"]:
        log.debug(f"CSRF skipped for auth endpoint: {request.url.path}")
        return True

    # Get CSRF token from cookie
    csrf_token_cookie = request.cookies.get("csrf_token")
    if not csrf_token_cookie:
        log_security_event("csrf_validation_failed", {
            "reason": "missing_csrf_cookie",
            "session_cookie_present": "session" in request.cookies
        }, request)
        return False

    # Get CSRF token from header
    csrf_token_header = request.headers.get("X-CSRF-Token")
    if not csrf_token_header:
        log_security_event("csrf_validation_failed", {
            "reason": "missing_csrf_header",
            "session_cookie_present": "session" in request.cookies
        }, request)
        return False

    # Compare tokens (double-submit pattern)
    is_valid = csrf_token_cookie == csrf_token_header
    if not is_valid:
        log_security_event("csrf_validation_failed", {
            "reason": "token_mismatch",
            "cookie_token_length": len(csrf_token_cookie),
            "header_token_length": len(csrf_token_header),
            "session_cookie_present": "session" in request.cookies
        }, request)
    else:
        log.debug(f"CSRF validation passed: {request.method} {request.url.path}")

    return is_valid
