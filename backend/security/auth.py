"""
Authentication and session management.
"""
import asyncio
import logging
import secrets
from datetime import datetime, timedelta, UTC
from typing import Optional, Dict
from fastapi import Request, HTTPException, Depends
from backend.config import ADMIN_EMAILS, AUTH_MODE, SESSION_TIMEOUT_HOURS, GUEST_SESSION_TIMEOUT_HOURS
from backend.database import db
from backend.security.csrf import generate_csrf_token

log = logging.getLogger(__name__)

# Session storage (in-memory cache for tracking active sessions)
sessions: Dict[str, dict] = {}


def generate_session_key(length=32) -> str:
    """
    Generates a securely random session key.

    This function creates a session key using a cryptographic random
    number generator. The key is returned in a URL-safe format and is
    suitable for use in session management and other scenarios where a
    secure, non-guessable token is required.

    :param length: The desired length of the generated session key, where
                   the length refers to the number of characters in the
                   resulting string. Defaults to 32.
    :type length: int

    :return: A URL-safe, randomly generated session key.
    :rtype: str
    """
    return secrets.token_urlsafe(length)


def create_session(user_id: int, user_email: str, session_duration_hours=SESSION_TIMEOUT_HOURS, is_guest=False,
                   regenerate_from=None, auth_method: Optional[str] = None, is_admin: bool = False,
                   id_token: Optional[str] = None) -> tuple[str, str]:
    """
    Creates and stores a new user session in the database. Optionally regenerates a session
    from an existing one by deleting the old session before creation.

    :param user_id: The unique identifier of the user for whom the session is being created.
    :type user_id: int
    :param user_email: The email address associated with the user's account.
    :type user_email: str
    :param session_duration_hours: The duration in hours for which the session remains valid.
        Defaults to SESSION_TIMEOUT_HOURS (guests: GUEST_SESSION_TIMEOUT_HOURS, passed by guest_login).
    :type session_duration_hours: int
    :param is_guest: Flag indicating whether the session is for a guest user. Defaults to False.
    :type is_guest: bool
    :param regenerate_from: The session key of an existing session to be regenerated. If provided,
        the existing session will be deleted.
    :type regenerate_from: str or None
    :param auth_method: How the user logged in: guest, mock or oidc (default: guest or mock).
    :type auth_method: str or None
    :param is_admin: Whether the login granted admin rights (OIDC_ADMIN_ROLE, see is_admin).
    :type is_admin: bool
    :param id_token: The OIDC ID token, for logging out at the provider.
    :type id_token: str or None
    :return: A tuple containing the new session key and the CSRF token associated with the session.
    :rtype: tuple[str, str]
    """
    if regenerate_from:
        log.debug(f"Regenerating session for user_id={user_id}")
        delete_session(regenerate_from)

    session_key = generate_session_key()
    csrf_token = generate_csrf_token()
    expires_at = datetime.now(UTC) + timedelta(hours=session_duration_hours)

    # Save session to database using the new Database class
    db.create_session(
        session_key=session_key,
        user_id=user_id,
        email=user_email,
        expires_at=expires_at,
        is_guest=is_guest,
        csrf_token=csrf_token,
        auth_method=auth_method or ("guest" if is_guest else "mock"),
        is_admin=is_admin,
        id_token=id_token
    )

    user_type = "guest" if is_guest else "user"
    log.info(f"Session created for {user_type} user_id={user_id}, expires_in={session_duration_hours}h")

    return session_key, csrf_token


def validate_session(session_key: str) -> Optional[dict]:
    """
    Validates the session using the provided session key by checking its existence and expiration status
    in the database. If validation succeeds, updates the last activity timestamp and calculates the
    remaining time until expiry.

    :param session_key: The session key used to identify the session in the database.
    :type session_key: str

    :return: A dictionary with session details if the session is valid, or None if the session does
             not exist or is expired.
    :rtype: Optional[dict]
    """
    if not session_key:
        log.debug("Session validation failed: no session key provided")
        return None

    # Get session from database (already filters expired sessions)
    session = db.get_session(session_key)

    if not session:
        log.debug("Session validation failed: session not found or expired")
        return None

    # Mock logins only count while mock login is on (sessions from before auth_method
    # existed are guest or mock sessions)
    auth_method = session.get("auth_method") or ("guest" if session["is_guest"] else "mock")
    if auth_method == "mock" and AUTH_MODE != "mock":
        log.info(f"Mock login session of user_id={session['user_id']} ended, AUTH_MODE is {AUTH_MODE}")
        db.delete_session(session_key)
        return None

    # Update last activity timestamp
    db.update_session_activity(session_key)
    log.debug(f"Session validated for user_id={session['user_id']}")

    # Calculate time until expiry
    expires_at = session['expires_at']
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)

    # Ensure expires_at is timezone-aware
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    current_time = datetime.now(UTC)
    time_until_expiry = expires_at - current_time
    expires_in_seconds = int(time_until_expiry.total_seconds())

    return {
        "user_id": session["user_id"],
        "email": session["email"],
        "is_guest": session["is_guest"],
        "csrf_token": session["csrf_token"],
        "expires_at": expires_at.isoformat(),
        "expires_in": expires_in_seconds,
        "auth_method": auth_method,
        "is_admin": bool(session.get("is_admin")),
        "id_token": session.get("id_token")
    }


def delete_session(session_key: str):
    """
    Deletes a session from the database matching the supplied session key.

    This function is used to remove a specific session record from the sessions table
    in the database. It performs a deletion query using the provided session key and
    commits the changes to ensure the session is successfully removed.

    :param session_key: The key identifying the session to be deleted from the database.
    :type session_key: str
    :return: None
    """
    log.debug("Session deleted")
    db.delete_session(session_key)


async def get_current_user(request: Request) -> dict:
    """
    Retrieves the current user's information based on the session cookie in the supplied request.
    If the session cookie is missing or invalid, an HTTP 401 error is raised. This is typically
    used for authentication purposes.

    :param request: An instance of `Request` containing the client's HTTP request. This includes
        necessary information like cookies for identifying the user's session.
    :return: A dictionary containing user information retrieved from the validated session.
    :rtype: dict
    :raises HTTPException: If the session cookie is missing or the session is invalid/expired,
        the function raises an HTTP error with status code 401 (Unauthorized).
    """
    session_key = request.cookies.get("session")
    if not session_key:
        log.debug(f"Authentication failed: no session cookie for {request.url.path}")
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_info = validate_session(session_key)
    if not user_info:
        log.debug(f"Authentication failed: invalid session for {request.url.path}")
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return user_info


async def get_current_user_optional(request: Request) -> Optional[dict]:
    """
    Asynchronously retrieves the currently authenticated user from the provided request object.
    In case the user is not authenticated or an HTTP exception occurs, it returns None.

    :param request: The request object used to fetch the current authenticated user.
    :type request: Request
    :return: A dictionary containing the current user's information if available, otherwise None.
    :rtype: Optional[dict]
    """
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


def is_admin(user: Optional[dict]) -> bool:
    """
    Checks whether a user may manage the model catalog.

    An OIDC login grants admin rights when the user has OIDC_ADMIN_ROLE or a verified
    email in ADMIN_EMAILS (stored on the session, see backend/security/oidc.py). For mock
    logins, admins are the users whose email is listed in ADMIN_EMAILS (case-insensitive).
    Guests are never admins.

    :param user: The user dictionary from get_current_user (with `email`, `is_guest`,
        `auth_method` and `is_admin`).
    :type user: Optional[dict]
    :return: True if the user is an admin, otherwise False.
    :rtype: bool
    """
    if not user or user.get("is_guest"):
        return False
    if user.get("is_admin"):
        return True
    email = (user.get("email") or "").strip().lower()
    return user.get("auth_method") == "mock" and bool(email) and email in ADMIN_EMAILS


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    FastAPI dependency for admin-only endpoints (the model catalog management).

    :param current_user: The authenticated user, injected via get_current_user.
    :type current_user: dict
    :return: The current user if they are an admin.
    :rtype: dict
    :raises HTTPException: 401 if not authenticated (from get_current_user), 403 if not an admin.
    """
    if not is_admin(current_user):
        log.warning(f"Admin access denied for user_id={current_user.get('user_id')} "
                    f"(guest={current_user.get('is_guest', False)})")
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


async def cleanup_expired_sessions():
    """
    Periodically cleans up expired sessions from the database. This function runs in
    an infinite loop, purging sessions with expiration dates earlier than the
    current time, and the guest users (with their conversations) that no session
    reaches any more. It executes this cleanup process every hour.

    :return: None
    """
    while True:
        try:
            # Clean expired sessions using the new Database method
            db.delete_expired_sessions()
            # Guest users whose sessions are gone, with their conversations
            db.delete_stale_guest_users(datetime.utcnow() - timedelta(hours=GUEST_SESSION_TIMEOUT_HOURS))
            log.debug("Expired sessions cleanup completed")

        except Exception as e:
            log.error(f"Error cleaning up sessions: {e}")

        # Run every hour
        await asyncio.sleep(3600)


def verify_conversation_ownership(conversation_id: str, user_id: int) -> bool:
    """
    Verifies whether the given user ID owns the specified conversation. Guests are
    no exception: every guest login has its own user (see guest_login).

    :param conversation_id: The unique identifier of the conversation
    :type conversation_id: str
    :param user_id: The unique identifier of the user
    :type user_id: int
    :return: True if the specified user owns the conversation, otherwise False
    :rtype: bool
    """
    owner_id = db.get_conversation_owner(conversation_id)

    if owner_id is None:
        log.debug(f"Conversation {conversation_id} not found")
        return False

    is_owner = owner_id == user_id
    if not is_owner:
        log.warning(f"Access denied: user_id={user_id} attempted to access conversation {conversation_id} owned by {owner_id}")
    return is_owner


def verify_file_ownership(file_id: str, user_id: Optional[int]) -> bool:
    """
    Verifies whether the given user uploaded the specified file. Only the uploader
    can read a file, through the files API and through the agent's file tool.
    Files without an owner (see db.get_file_owner) are nobody's.

    :param file_id: The file ID (the stored filename without extension)
    :type file_id: str
    :param user_id: The unique identifier of the user; None is nobody
    :type user_id: Optional[int]
    :return: True if the user uploaded the file, otherwise False
    :rtype: bool
    """
    owner_id = db.get_file_owner(file_id)

    if owner_id is None:
        log.debug(f"File {file_id} has no owner")
        return False

    is_owner = owner_id == user_id
    if not is_owner:
        log.warning(f"Access denied: user_id={user_id} attempted to access file {file_id} owned by {owner_id}")
    return is_owner


def client_ip(request: Request) -> Optional[str]:
    """
    The client's IP address, taken from the connection, never from the request body.

    Behind a reverse proxy this is the proxy's address, unless uvicorn trusts the
    proxy's X-Forwarded-For header (FORWARDED_ALLOW_IPS, default 127.0.0.1).

    :param request: The HTTP request.
    :return: The address, or None if the server doesn't know it.
    """
    return request.client.host if request.client else None


async def rate_limit_guest(request: Request, current_user: Optional[dict] = Depends(get_current_user_optional)):
    """
    Apply a rate limit mechanism for guest users based on their IP addresses. The function allows a
    maximum number of requests for guest users within a specified time frame. If the limit is exceeded,
    a 429 HTTP status is returned with details about when the user can retry.

    :param request: The HTTP request object containing the request data and client information.
    :type request: Request
    :param current_user: An optional dictionary containing information about the current authenticated
        user. Defaults to None if the user is not authenticated.
    :type current_user: Optional[dict]
    :return: None if no rate limit is applied or the user is not a guest.

    :raises HTTPException: If the guest user exceeds the rate limit, a 429 Too Many Requests error is
        raised, including a Retry-After header with the recommended wait time.
    """
    if current_user and not current_user.get("is_guest"):
        return  # Not a guest, no rate limit

    ip_address = client_ip(request) or "unknown"
    now = datetime.now(UTC)
    limit_duration = timedelta(hours=3)
    max_requests = 5

    usage = db.get_guest_usage(ip_address)

    if usage:
        last_request_at = usage["last_request_at"]
        if isinstance(last_request_at, str):
            last_request_at = datetime.fromisoformat(last_request_at)

        # Ensure timezone awareness
        if last_request_at.tzinfo is None:
            last_request_at = last_request_at.replace(tzinfo=UTC)

        if now - last_request_at > limit_duration:
            # Reset counter
            log.debug(f"Rate limit counter reset for guest IP {ip_address}")
            db.reset_guest_usage(ip_address)
        elif usage["request_count"] >= max_requests:
            reset_time = last_request_at + limit_duration
            retry_after_seconds = (reset_time - now).total_seconds()
            headers = {"Retry-After": str(int(retry_after_seconds))}
            log.warning(f"Rate limit exceeded for guest IP {ip_address}: {usage['request_count']}/{max_requests}")
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests. Please try again after {reset_time.isoformat()}",
                headers=headers
            )
        else:
            db.increment_guest_usage(ip_address)
            log.debug(f"Guest request count: {usage['request_count'] + 1}/{max_requests} for IP {ip_address}")
    else:
        db.increment_guest_usage(ip_address)
        log.debug(f"First guest request tracked for IP {ip_address}")
