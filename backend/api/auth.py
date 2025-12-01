"""
Authentication API endpoints.
"""
import os
import secrets
from datetime import datetime, timedelta, UTC
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from backend.models.auth import MockLoginRequest, GuestLoginRequest, LoginResponse
from backend.security.auth import (
    create_session, validate_session, delete_session, get_current_user
)
from backend.security.logging import log_security_event
from backend.database import db

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/guest-login",
             response_model=LoginResponse,
             summary="Guest Login",
             description="Creates a guest session for anonymous users with rate limiting based on IP address",
             operation_id="guestLogin")
async def guest_login(request: GuestLoginRequest, req: Request, response: Response):
    """
    Handles guest login by verifying IP address rate limits, creating a guest session,
    and managing cookies and headers for client authentication and CSRF protection.

    :param request: The request object containing the guest's login details.
    :type request: GuestLoginRequest
    :param req: The incoming HTTP request object used to access request-related data.
    :type req: Request
    :param response: The HTTP response object for setting cookies and headers.
    :type response: Response
    :return: An object containing guest user information, a success message, and the session token.
    :rtype: LoginResponse
    :raises HTTPException: If the rate limit is exceeded based on the guest's IP address.
    """
    ip_address = request.ip_address

    # If IP address is 'unknown', use a fallback
    if ip_address == 'unknown':
        ip_address = f"guest_{secrets.token_hex(4)}"

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
            db.reset_guest_usage(ip_address)
        elif usage["request_count"] >= max_requests:
            reset_time = last_request_at + limit_duration
            raise HTTPException(status_code=429,
                                detail=f"Rate limit exceeded. Please try again after {reset_time.isoformat()}.")
    else:
        db.increment_guest_usage(ip_address)

    # Get existing session to regenerate from
    old_session_key = req.cookies.get("session")

    guest_email = f"guest_{secrets.token_hex(4)}@guest.com"
    guest_user = {"id": 0, "email": guest_email, "name": "Guest"}

    # Use shorter timeout for guest sessions
    guest_timeout_hours = int(os.getenv('GUEST_SESSION_TIMEOUT_HOURS', '6'))

    # Create new guest session with custom timeout, regenerating old session
    session_key, csrf_token = create_session(0, guest_email, session_duration_hours=guest_timeout_hours, is_guest=True,
                                              regenerate_from=old_session_key)

    max_age = guest_timeout_hours * 3600

    response.set_cookie(
        key="session",
        value=session_key,
        max_age=max_age,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/"
    )

    # Set CSRF token as cookie for double-submit pattern
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        max_age=max_age,
        httponly=False,  # JS needs to read this
        secure=True,
        samesite="lax",  # Lax allows cross-site requests from different ports
        path="/"
    )

    # Also set CSRF token in response header for backward compatibility
    response.headers["X-CSRF-Token"] = csrf_token

    # Log successful guest login
    log_security_event("guest_login_success", {
        "user_id": guest_user["id"],
        "ip_address": ip_address,
        "guest_timeout_hours": guest_timeout_hours
    }, req)

    return LoginResponse(
        user=guest_user,
        message="Guest login successful",
        token=session_key
    )


@router.post("/mock-login",
             response_model=LoginResponse,
             summary="Mock Login",
             description="Mock authentication for testing purposes - creates or retrieves a test user",
             operation_id="mockLogin")
async def mock_login(request: MockLoginRequest, req: Request, response: Response):
    """
    Handles the mock login process for a user by creating or retrieving a user in the database,
    generating a session, and setting appropriate cookies and headers for the client. This
    endpoint is typically used for testing authentication workflows.

    :param request: A validated request object containing mock login details, including the
        user's email.
    :type request: MockLoginRequest
    :param req: The incoming HTTP request object that includes session cookies, if any.
    :type req: Request
    :param response: The outgoing response object to set cookies and headers for the client.
    :type response: Response
    :return: A response object containing user data and a success message.
    :rtype: LoginResponse
    """
    print(f"Login attempt for: {request.email}")

    # Get existing session to regenerate from
    old_session_key = req.cookies.get("session")

    # Check if user exists
    user = db.get_user_by_email(request.email)

    if not user:
        # User doesn't exist, create a new one
        user_name = request.email.split('@')[0].title()
        user = db.create_user(email=request.email, name=user_name)
        new_user = True
    else:
        new_user = False

    user_id = user['id']
    user_name = user['name']

    # Create session with is_guest=False for regular users, regenerating old session
    session_key, csrf_token = create_session(user_id, request.email, is_guest=False, regenerate_from=old_session_key)

    # Calculate max_age based on session timeout
    session_timeout_hours = int(os.getenv('SESSION_TIMEOUT_HOURS', '24'))
    max_age = session_timeout_hours * 3600

    # Set session cookie
    response.set_cookie(
        key="session",
        value=session_key,
        max_age=max_age,
        httponly=True,  # Prevents JS access
        secure=True,  # HTTPS only
        samesite="lax",
        path="/"
    )

    # Set CSRF token as cookie for double-submit pattern
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        max_age=max_age,
        httponly=False,  # JS needs to read this
        secure=True,
        samesite="lax",  # Lax allows cross-site requests from different ports
        path="/"
    )

    # Also set CSRF token in response header for backward compatibility
    response.headers["X-CSRF-Token"] = csrf_token

    # Log successful login
    log_security_event("user_login_success", {
        "user_id": user_id,
        "email": request.email,
        "new_user": new_user
    }, req)

    return LoginResponse(
        user={
            "id": user_id,
            "email": request.email,
            "name": user_name
        },
        message="Mock login successful"
    )


@router.post("/logout",
             summary="Logout",
             description="Invalidates the current session and clears authentication cookies",
             operation_id="logout")
async def logout(request: Request, response: Response):
    """
    Logs out a user by invalidating the current session key, deleting associated
    cookies, and logging a security event if a valid session exists.

    The function retrieves the session key from the `request` cookies. If a valid
    session is found, it logs the logout event before deleting the session. After
    that, it deletes the `session` and `csrf_token` cookies from the response.

    :param request: The incoming HTTP request containing user session cookies
    :type request: Request
    :param response: The HTTP response object to modify and send back to the client
    :type response: Response
    :return: A confirmation message indicating the successful logout
    :rtype: dict
    """
    session_key = request.cookies.get("session")
    if session_key:
        # Log logout event before deleting session
        session_data = validate_session(session_key)
        if session_data:
            log_security_event("user_logout", {
                "user_id": session_data["user_id"],
                "email": session_data["email"]
            }, request)

        delete_session(session_key)

    # Delete cookies
    response.delete_cookie(
        key="session",
        path="/",
        secure=True,
        httponly=True,
        samesite="lax"
    )
    response.delete_cookie(
        key="csrf_token",
        path="/",
        secure=True,
        httponly=False,
        samesite="lax"
    )
    return {"message": "Logged out successfully"}


@router.post("/refresh-session",
             summary="Refresh Session",
             description="Refreshes the user session if it's close to expiry (within 1 hour)",
             operation_id="refreshSession")
async def refresh_session(request: Request, response: Response, current_user: dict = Depends(get_current_user)):
    """
    Refreshes the user session and updates session cookies and CSRF tokens. If the
    session is far from expiry (greater than 1 hour), it does not create a new
    session but instead provides a message indicating no refresh is required. If the
    session is close to expiring or expired, a new session is created with a duration
    that depends on the user's type (guest or regular user), and updated session
    details are returned.

    :param request: FastAPI Request object used to retrieve cookies from the client.
    :type request: Request
    :param response: FastAPI Response object used to set cookies and response headers.
    :type response: Response
    :param current_user: Dictionary containing information about the currently
                         authenticated user, such as user ID, email, and session expiration.
                         Passed as a dependency.
    :type current_user: dict
    :return: A dictionary containing a message about whether the session was refreshed and
             the new session expiration time in seconds.
    :rtype: dict
    """
    session_key = request.cookies.get("session")
    if not session_key:
        raise HTTPException(status_code=401, detail="No session to refresh")

    # Check if session is close to expiring (less than 1 hour)
    expires_in = current_user.get("expires_in", 0)
    if expires_in > 3600:  # More than 1 hour remaining
        return {
            "message": "Session does not need refresh yet",
            "expires_in": expires_in
        }

    # Create new session with same user info
    user_id = current_user["user_id"]
    email = current_user["email"]
    is_guest = current_user.get("is_guest", False)

    # Determine session duration based on user type
    if is_guest:
        session_hours = int(os.getenv('GUEST_SESSION_TIMEOUT_HOURS', '6'))
    else:
        session_hours = int(os.getenv('SESSION_TIMEOUT_HOURS', '24'))

    # Create new session, regenerating the old one
    new_session_key, new_csrf_token = create_session(
        user_id, email, session_hours, is_guest, regenerate_from=session_key
    )

    # Set new session cookie
    max_age = session_hours * 3600
    response.set_cookie(
        key="session",
        value=new_session_key,
        max_age=max_age,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/"
    )

    # Set CSRF token as cookie for double-submit pattern
    response.set_cookie(
        key="csrf_token",
        value=new_csrf_token,
        max_age=max_age,
        httponly=False,  # JS needs to read this
        secure=True,
        samesite="lax",  # Lax allows cross-site requests from different ports
        path="/"
    )

    # Also set new CSRF token in response header for backward compatibility
    response.headers["X-CSRF-Token"] = new_csrf_token

    return {
        "message": "Session refreshed successfully",
        "expires_in": max_age
    }


@router.get("/me",
            summary="Get Current User",
            description="Returns information about the currently authenticated user",
            operation_id="getCurrentUser")
async def get_me(request: Request, response: Response, current_user: dict = Depends(get_current_user)):
    """
    Handles the retrieval of the current authenticated user information along with session
    and CSRF token management. Ensures that a proper csrf_token cookie is set and includes
    the CSRF token as a custom header in the response. The endpoint returns user-specific
    information such as user ID, email, and session expiry details.

    :param request: FastAPI Request object; used to gather request-related data such as cookies.
    :type request: Request
    :param response: FastAPI Response object; used to customize HTTP response attributes like
                     headers and cookies.
    :type response: Response
    :param current_user: Dictionary containing information about the currently authenticated user;
                         includes user details and session attributes.
    :type current_user: dict, retrieved via dependency injection
    :return: JSON response with user information, including user ID, email, guest session
             status, and session expiry details.
    :rtype: dict
    """
    # Check if CSRF cookie exists
    csrf_cookie = request.cookies.get("csrf_token")
    csrf_token = current_user.get("csrf_token")

    # If we have a CSRF token in session but no cookie, set the cookie
    if csrf_token and not csrf_cookie:
        # Calculate max age based on remaining session time
        expires_in = current_user.get("expires_in", 86400)  # Default to 24 hours
        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            max_age=expires_in,
            httponly=False,  # JS needs to read this
            secure=True,
            samesite="lax",  # Lax allows cross-site requests from different ports
            path="/"
        )

    # Include CSRF token in response header
    if csrf_token:
        response.headers["X-CSRF-Token"] = csrf_token

    # Prepare user data with session info
    user_data = {
        "user_id": current_user["user_id"],
        "email": current_user["email"],
        "is_guest": current_user.get("is_guest", False),
        "session_expires_at": current_user.get("expires_at"),
        "session_expires_in": current_user.get("expires_in")
    }

    return {"user": user_data}
