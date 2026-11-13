"""
CSRF (Cross-Site Request Forgery) protection.
"""
import logging
import secrets
from fastapi import Request
from backend.config import CORS_ORIGINS, FRONTEND_URL
from backend.security.logging import log_security_event

log = logging.getLogger(__name__)

# Logins, logout and the session refresh carry no CSRF token: a browser may have no session
# and so no token yet. They are checked by where the request comes from instead (from_own_page)
TOKENLESS_PATHS = {"/api/auth/mock-login", "/api/auth/guest-login", "/api/auth/logout",
                   "/api/auth/refresh-session"}


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


def from_own_page(request: Request) -> bool:
    """
    Whether a request comes from the app's own pages and not from a page of another site.

    Browsers name the page a request comes from in the Origin header of every POST across
    sites, also for a plain form. Another site's page could otherwise log a visitor out, or
    swap their session for a guest's, by posting a form to the logout or the guest login.
    Requests without the header come from scripts and tools, which have no visitor's
    cookies to abuse.

    :param request: The incoming HTTP request.
    :return: True without an Origin header or with the frontend's origin (FRONTEND_URL, CORS_ORIGINS).
    """
    origin = request.headers.get("origin")
    if origin is None:
        return True
    return origin.rstrip("/") in {FRONTEND_URL, *(allowed.rstrip("/") for allowed in CORS_ORIGINS)}


async def validate_csrf_token(request: Request) -> bool:
    """
    Validates the CSRF token submitted via the HTTP request. This function
    implements CSRF protection using the double-submit pattern, ensuring requests
    are authorized and preventing cross-site request forgery attacks. Specifically,
    it checks if the CSRF token provided in the request header matches the CSRF
    token stored in the cookie. Safe HTTP methods pass without a check. The
    authentication endpoints that can't carry a token (TOKENLESS_PATHS) are
    checked by the page the request comes from instead (from_own_page).

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

    # Authentication endpoints: no token, but only from the app's own pages
    if request.url.path in TOKENLESS_PATHS:
        if not from_own_page(request):
            log_security_event("csrf_validation_failed", {
                "reason": "foreign_origin",
                "origin": request.headers.get("origin", "")[:200]
            }, request)
            return False
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
