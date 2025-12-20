"""
Authentication and session management.
"""
import asyncio
import logging
import os
import secrets
from datetime import datetime, timedelta, UTC
from typing import Optional, Dict
from fastapi import Request, HTTPException, Depends
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


def create_session(user_id: int, user_email: str, session_duration_hours=24, is_guest=False, regenerate_from=None) -> tuple[str, str]:
    """
    Creates and stores a new user session in the database. Optionally regenerates a session
    from an existing one by deleting the old session before creation.

    :param user_id: The unique identifier of the user for whom the session is being created.
    :type user_id: int
    :param user_email: The email address associated with the user's account.
    :type user_email: str
    :param session_duration_hours: The duration in hours for which the session remains valid.
        Defaults to 24 hours.
    :type session_duration_hours: int
    :param is_guest: Flag indicating whether the session is for a guest user. Defaults to False.
    :type is_guest: bool
    :param regenerate_from: The session key of an existing session to be regenerated. If provided,
        the existing session will be deleted.
    :type regenerate_from: str or None
    :return: A tuple containing the new session key and the CSRF token associated with the session.
    :rtype: tuple[str, str]
    """
    if regenerate_from:
        log.debug(f"Regenerating session for user_id={user_id}")
        delete_session(regenerate_from)

    session_key = generate_session_key()
    csrf_token = generate_csrf_token()

    # Use environment variable for session timeout if available
    session_timeout = int(os.getenv('SESSION_TIMEOUT_HOURS', str(session_duration_hours)))
    expires_at = datetime.now(UTC) + timedelta(hours=session_timeout)

    # Save session to database using the new Database class
    db.create_session(
        session_key=session_key,
        user_id=user_id,
        email=user_email,
        expires_at=expires_at,
        is_guest=is_guest,
        csrf_token=csrf_token
    )

    user_type = "guest" if is_guest else "user"
    log.info(f"Session created for {user_type} user_id={user_id}, expires_in={session_timeout}h")

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
        "expires_in": expires_in_seconds
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


async def cleanup_expired_sessions():
    """
    Periodically cleans up expired sessions from the database. This function runs in
    an infinite loop, purging sessions with expiration dates earlier than the
    current time. It executes this cleanup process every hour.

    :return: None
    """
    while True:
        try:
            # Clean expired sessions using the new Database method
            db.delete_expired_sessions()
            log.debug("Expired sessions cleanup completed")

        except Exception as e:
            log.error(f"Error cleaning up sessions: {e}")

        # Run every hour
        await asyncio.sleep(3600)


def verify_conversation_ownership(conversation_id: str, user_id: int, is_guest: bool = False) -> bool:
    """
    Verifies whether the given user ID owns the specified conversation. This function allows guest users
    to access any conversation, typically for offline mode functionality. For non-guest users, it checks
    in the database if the user ID corresponds to the conversation's owner.

    :param conversation_id: The unique identifier of the conversation
    :type conversation_id: str
    :param user_id: The unique identifier of the user
    :type user_id: int
    :param is_guest: Specifies if the user is a guest. Defaults to False.
    :type is_guest: bool, optional
    :return: True if the specified user owns the conversation or if user
        is a guest, otherwise False
    :rtype: bool
    """
    # Guest users can access any conversation (for offline mode)
    if is_guest:
        log.debug(f"Guest access granted to conversation {conversation_id}")
        return True

    owner_id = db.get_conversation_owner(conversation_id)

    if owner_id is None:
        log.debug(f"Conversation {conversation_id} not found")
        return False

    is_owner = owner_id == user_id
    if not is_owner:
        log.warning(f"Access denied: user_id={user_id} attempted to access conversation {conversation_id} owned by {owner_id}")
    return is_owner


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

    ip_address = request.client.host
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
