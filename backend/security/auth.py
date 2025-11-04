"""
Authentication and session management.
"""
import asyncio
import os
import secrets
from datetime import datetime, timedelta, UTC
from typing import Optional, Dict
from fastapi import Request, HTTPException, Depends
from backend.database.db import get_db
from backend.security.csrf import generate_csrf_token

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
        delete_session(regenerate_from)

    session_key = generate_session_key()
    csrf_token = generate_csrf_token()

    # Use environment variable for session timeout if available
    session_timeout = int(os.getenv('SESSION_TIMEOUT_HOURS', str(session_duration_hours)))
    expires_at = datetime.now(UTC) + timedelta(hours=session_timeout)

    # Save session to database
    with get_db() as db:
        db.execute(
            """
            INSERT INTO sessions (session_key, user_id, email, expires_at, is_guest, csrf_token)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (session_key, user_id, user_email, expires_at.isoformat(), is_guest, csrf_token))

        db.commit()

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
        return None

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT user_id, email, expires_at, last_activity, is_guest, csrf_token
            FROM sessions
            WHERE session_key = ?
            """, (session_key,))
        result = cur.fetchone()

        if not result:
            return None

        expires_at = datetime.fromisoformat(result["expires_at"])
        current_time = datetime.now(UTC)

        if current_time > expires_at:
            # Session expired, clean up
            cur.execute("DELETE FROM sessions WHERE session_key = ?", (session_key,))
            conn.commit()
            return None

        # Update last activity timestamp
        cur.execute("""
                    UPDATE sessions
                    SET last_activity = ?
                    WHERE session_key = ?
                    """, (current_time.isoformat(), session_key))
        conn.commit()

        # Calculate time until expiry
        time_until_expiry = expires_at - current_time
        expires_in_seconds = int(time_until_expiry.total_seconds())

        return {
            "user_id": result["user_id"],
            "email": result["email"],
            "is_guest": result["is_guest"],
            "csrf_token": result["csrf_token"],
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
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM sessions WHERE session_key = ?", (session_key,))
        conn.commit()


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
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_info = validate_session(session_key)
    if not user_info:
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
            # Clean database sessions
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("""
                            DELETE FROM sessions
                            WHERE datetime(expires_at) < datetime('now')
                            """)
                conn.commit()

        except Exception as e:
            print(f"Error cleaning up sessions: {e}")

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
        return True

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT userId FROM conversations WHERE id = ?",
            (conversation_id,)
        )
        result = cur.fetchone()

        if not result:
            return False

        return result['userId'] == user_id


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
    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT request_count, last_request_at FROM guest_usage WHERE ip_address = ?", (ip_address,))
        usage = cur.fetchone()

        now = datetime.now(UTC)
        limit_duration = timedelta(hours=3)
        max_requests = 5

        if usage:
            last_request_at = datetime.fromisoformat(usage["last_request_at"])
            if now - last_request_at > limit_duration:
                # Reset counter
                cur.execute("UPDATE guest_usage SET request_count = 1, last_request_at = ? WHERE ip_address = ?",
                            (now.isoformat(), ip_address))
            elif usage["request_count"] >= max_requests:
                reset_time = last_request_at + limit_duration
                retry_after_seconds = (reset_time - now).total_seconds()
                headers = {"Retry-After": str(int(retry_after_seconds))}
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many requests. Please try again after {reset_time.isoformat()}",
                    headers=headers
                )
            else:
                cur.execute(
                    "UPDATE guest_usage SET request_count = request_count + 1, last_request_at = ? WHERE ip_address = ?",
                    (now.isoformat(), ip_address))
        else:
            cur.execute("INSERT INTO guest_usage (ip_address, request_count, last_request_at) VALUES (?, 1, ?)",
                        (ip_address, now.isoformat()))
        db.commit()
