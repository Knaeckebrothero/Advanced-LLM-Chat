"""
Authentication API endpoints.
"""
import logging
import secrets
from datetime import datetime, timedelta, UTC
from typing import Optional
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from fastapi.responses import RedirectResponse
from backend.config import (AUTH_MODE, FRONTEND_URL, GUEST_SESSION_TIMEOUT_HOURS, OIDC_DISPLAY_NAME,
                            OIDC_REDIRECT_URI, SESSION_TIMEOUT_HOURS)
from backend.models.auth import MockLoginRequest, LoginResponse
from backend.security import oidc
from backend.security.auth import (
    client_ip, create_session, validate_session, delete_session, get_current_user, is_admin
)
from backend.security.logging import log_security_event
from backend.database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Auth"])

# The cookie that keeps a started OIDC login until the provider redirects back
OIDC_LOGIN_COOKIE = "oidc_login"
OIDC_COOKIE_PATH = "/api/auth/oidc"


def set_session_cookies(response: Response, session_key: str, csrf_token: str, max_age: int) -> None:
    """
    Sets the session cookie, the CSRF cookie (double-submit pattern, readable by JS) and
    the CSRF header after a login or session refresh.
    """
    response.set_cookie(
        key="session",
        value=session_key,
        max_age=max_age,
        httponly=True,  # Prevents JS access
        secure=True,  # HTTPS only
        samesite="lax",
        path="/"
    )
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


@router.get("/config",
            summary="Login Options",
            description="How users log in on this server (AUTH_MODE: oidc, mock or none); guests can always chat",
            operation_id="getAuthConfig")
async def auth_config():
    """
    Tells the login page how users log in: through the OIDC provider (`providerName` is
    shown on its button), with the development mock login, or not at all.

    :return: The mode and, for oidc, the provider's display name.
    :rtype: dict
    """
    return {"mode": AUTH_MODE, "providerName": OIDC_DISPLAY_NAME if AUTH_MODE == "oidc" else None}


@router.post("/guest-login",
             response_model=LoginResponse,
             summary="Guest Login",
             description="Creates a guest session for anonymous users with rate limiting based on IP address",
             operation_id="guestLogin")
async def guest_login(req: Request, response: Response):
    """
    Handles guest login by verifying IP address rate limits, creating a guest session,
    and managing cookies and headers for client authentication and CSRF protection.

    The IP address comes from the connection (client_ip); a body sent by older
    clients ({"ip_address": ...}) is ignored, so it can't be used to dodge the limit.

    :param req: The incoming HTTP request object used to access request-related data.
    :type req: Request
    :param response: The HTTP response object for setting cookies and headers.
    :type response: Response
    :return: An object containing guest user information, a success message, and the session token.
    :rtype: LoginResponse
    :raises HTTPException: If the rate limit is exceeded based on the guest's IP address.
    """
    ip_address = client_ip(req)
    logger.debug(f"Guest login attempt from IP: {ip_address}")

    # If the server doesn't know the address, use a fallback
    if not ip_address:
        ip_address = f"guest_{secrets.token_hex(4)}"
        logger.debug(f"Unknown IP, generated fallback identifier: {ip_address}")

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
            logger.debug(f"Rate limit window expired for {ip_address}, resetting counter")
            db.reset_guest_usage(ip_address)
        elif usage["request_count"] >= max_requests:
            reset_time = last_request_at + limit_duration
            logger.warning(f"Rate limit exceeded for guest IP {ip_address}, count: {usage['request_count']}")
            raise HTTPException(status_code=429,
                                detail=f"Rate limit exceeded. Please try again after {reset_time.isoformat()}.")
    else:
        db.increment_guest_usage(ip_address)

    # Get existing session to regenerate from
    old_session_key = req.cookies.get("session")

    # Every guest gets its own user, so guests only reach their own conversations.
    # It's deleted with its data once its sessions have expired (cleanup_expired_sessions).
    guest_email = f"guest_{secrets.token_hex(8)}@guest.invalid"
    guest = db.create_user(guest_email, "Guest", is_guest=True)
    guest_user = {"id": guest["id"], "email": guest_email, "name": "Guest"}

    # Use shorter timeout for guest sessions
    guest_timeout_hours = GUEST_SESSION_TIMEOUT_HOURS

    # Create new guest session with custom timeout, regenerating old session
    session_key, csrf_token = create_session(guest["id"], guest_email, session_duration_hours=guest_timeout_hours,
                                              is_guest=True, regenerate_from=old_session_key, auth_method="guest")

    set_session_cookies(response, session_key, csrf_token, guest_timeout_hours * 3600)

    # Log successful guest login
    log_security_event("guest_login_success", {
        "user_id": guest_user["id"],
        "ip_address": ip_address,
        "guest_timeout_hours": guest_timeout_hours
    }, req)

    logger.info(f"Guest login successful - email: {guest_email}, timeout: {guest_timeout_hours}h")

    return LoginResponse(
        user=guest_user,
        message="Guest login successful",
        token=session_key
    )


@router.post("/mock-login",
             response_model=LoginResponse,
             summary="Mock Login",
             description="Login with any email and no password, for development (only with AUTH_MODE=mock)",
             operation_id="mockLogin")
async def mock_login(request: MockLoginRequest, req: Request, response: Response):
    """
    Handles the mock login process for a user by creating or retrieving a user in the database,
    generating a session, and setting appropriate cookies and headers for the client. This
    endpoint is typically used for testing authentication workflows. It only exists with
    AUTH_MODE=mock: anyone could log in as anyone with it.

    :param request: A validated request object containing mock login details, including the
        user's email.
    :type request: MockLoginRequest
    :param req: The incoming HTTP request object that includes session cookies, if any.
    :type req: Request
    :param response: The outgoing response object to set cookies and headers for the client.
    :type response: Response
    :return: A response object containing user data and a success message.
    :rtype: LoginResponse
    :raises HTTPException: 404 unless AUTH_MODE is mock.
    """
    if AUTH_MODE != "mock":
        raise HTTPException(status_code=404, detail="Mock login is turned off (AUTH_MODE)")
    logger.debug(f"Mock login attempt for: {request.email}")

    # Get existing session to regenerate from
    old_session_key = req.cookies.get("session")

    # Check if user exists
    user = db.get_user_by_email(request.email)

    if not user:
        # User doesn't exist, create a new one
        user_name = request.email.split('@')[0].title()
        user = db.create_user(email=request.email, name=user_name)
        new_user = True
        logger.info(f"Created new user: {request.email}")
    else:
        new_user = False
        logger.debug(f"Existing user found: {request.email}")

    user_id = user['id']
    user_name = user['name']

    # Create session with is_guest=False for regular users, regenerating old session
    session_key, csrf_token = create_session(user_id, request.email, is_guest=False, regenerate_from=old_session_key,
                                              auth_method="mock")

    set_session_cookies(response, session_key, csrf_token, SESSION_TIMEOUT_HOURS * 3600)

    # Log successful login
    log_security_event("user_login_success", {
        "user_id": user_id,
        "email": request.email,
        "new_user": new_user
    }, req)

    logger.info(f"Mock login successful - user_id: {user_id}, email: {request.email}, new_user: {new_user}")

    return LoginResponse(
        user={
            "id": user_id,
            "email": request.email,
            "name": user_name,
            "isAdmin": is_admin({"email": request.email, "is_guest": False, "auth_method": "mock"})
        },
        message="Mock login successful"
    )


def _login_failed(reason: str) -> RedirectResponse:
    return RedirectResponse(f"{FRONTEND_URL}/login?error={reason}", status_code=302)


@router.get("/oidc/login",
            summary="Log In Through the OIDC Provider",
            description="Redirects the browser to the OIDC provider's login page (only with AUTH_MODE=oidc)",
            operation_id="oidcLogin")
async def oidc_login(req: Request):
    """
    Starts a login through the OIDC provider (authorization code flow with PKCE). The state,
    nonce and PKCE verifier wait in a short-lived cookie for the provider's redirect to
    oidc_callback.

    :param req: The incoming HTTP request (its address gives the callback URL without OIDC_REDIRECT_URI).
    :type req: Request
    :return: A redirect to the provider, or to the login page if the provider can't be reached.
    :rtype: RedirectResponse
    :raises HTTPException: 404 unless AUTH_MODE is oidc.
    """
    if AUTH_MODE != "oidc":
        raise HTTPException(status_code=404, detail="Login through an OIDC provider is turned off (AUTH_MODE)")
    redirect_uri = OIDC_REDIRECT_URI or str(req.url_for("oidc_callback"))
    try:
        url, pending = await oidc.authorization_url(redirect_uri)
    except Exception as e:
        logger.error(f"Can't start an OIDC login, the provider isn't reachable or misconfigured: {e}")
        return _login_failed("provider_unavailable")

    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        key=OIDC_LOGIN_COOKIE,
        value=oidc.encode_pending(pending),
        max_age=oidc.LOGIN_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",  # Sent along when the provider redirects the browser back
        path=OIDC_COOKIE_PATH
    )
    return response


@router.get("/oidc/callback",
            summary="OIDC Login Callback",
            description="Where the OIDC provider redirects the browser after a login; ends on the frontend",
            operation_id="oidcCallback")
async def oidc_callback(req: Request, code: Optional[str] = None, state: Optional[str] = None,
                        error: Optional[str] = None):
    """
    Finishes a login through the OIDC provider: checks the state, swaps the code for tokens,
    finds or creates the user (oidc.user_for_login), creates a session like every other
    login and redirects to the frontend's /auth/callback. A failed or refused login ends on
    the login page with an error (auth_failed, forbidden or email_in_use).

    :param req: The incoming HTTP request with the pending login's cookie.
    :type req: Request
    :param code: The authorization code.
    :param state: The state from oidc_login.
    :param error: The provider's error, e.g. access_denied.
    :return: A redirect to the frontend.
    :rtype: RedirectResponse
    :raises HTTPException: 404 unless AUTH_MODE is oidc.
    """
    if AUTH_MODE != "oidc":
        raise HTTPException(status_code=404, detail="Login through an OIDC provider is turned off (AUTH_MODE)")
    pending = oidc.decode_pending(req.cookies.get(OIDC_LOGIN_COOKIE))
    try:
        if error:
            raise ValueError(f"The provider returned the error {error}")
        if not pending or not code or not state or not secrets.compare_digest(state, pending["state"]):
            raise ValueError("The login's state doesn't match (expired, or started in another browser)")
        login = await oidc.finish_login(code, pending)
        user = oidc.user_for_login(login)
    except oidc.LoginRefused as e:
        logger.warning(f"OIDC login refused ({e.reason}): {e}")
        log_security_event("oidc_login_refused", {"reason": e.reason, "detail": str(e)}, req)
        response = _login_failed(e.reason)
    except Exception as e:
        logger.warning(f"OIDC login failed: {e}")
        log_security_event("oidc_login_failed", {"error": str(e)[:300]}, req)
        response = _login_failed("auth_failed")
    else:
        admin = oidc.grants_admin(login)
        session_key, csrf_token = create_session(
            user["id"], user["email"], is_guest=False, regenerate_from=req.cookies.get("session"),
            auth_method="oidc", is_admin=admin, id_token=login.id_token
        )
        response = RedirectResponse(f"{FRONTEND_URL}/auth/callback", status_code=302)
        set_session_cookies(response, session_key, csrf_token, SESSION_TIMEOUT_HOURS * 3600)
        log_security_event("user_login_success", {
            "user_id": user["id"],
            "email": user["email"],
            "method": "oidc",
            "is_admin": admin
        }, req)
        logger.info(f"OIDC login successful - user_id: {user['id']}, admin: {admin}")

    response.delete_cookie(key=OIDC_LOGIN_COOKIE, path=OIDC_COOKIE_PATH, secure=True, httponly=True,
                           samesite="lax")
    return response


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
    After an OIDC login, `logoutUrl` is where the browser ends the provider's session too
    (otherwise the next login would go through without asking for a password).

    :param request: The incoming HTTP request containing user session cookies
    :type request: Request
    :param response: The HTTP response object to modify and send back to the client
    :type response: Response
    :return: A confirmation message, and the provider's logout URL or None
    :rtype: dict
    """
    logout_url = None
    session_key = request.cookies.get("session")
    if session_key:
        # Log logout event before deleting session
        session_data = validate_session(session_key)
        if session_data and session_data.get("auth_method") == "oidc" and AUTH_MODE == "oidc":
            logout_url = await oidc.logout_url(session_data.get("id_token"))
        if session_data:
            log_security_event("user_logout", {
                "user_id": session_data["user_id"],
                "email": session_data["email"]
            }, request)
            logger.info(f"User logout - user_id: {session_data['user_id']}, email: {session_data['email']}")

        delete_session(session_key)
        logger.debug("Session deleted")
    else:
        logger.debug("Logout called but no session cookie found")

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
    return {"message": "Logged out successfully", "logoutUrl": logout_url}


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
        logger.debug("Session refresh attempted without session cookie")
        raise HTTPException(status_code=401, detail="No session to refresh")

    # Check if session is close to expiring (less than 1 hour)
    expires_in = current_user.get("expires_in", 0)
    if expires_in > 3600:  # More than 1 hour remaining
        logger.debug(f"Session refresh not needed - expires in {expires_in}s")
        return {
            "message": "Session does not need refresh yet",
            "expires_in": expires_in
        }

    # Create new session with same user info
    user_id = current_user["user_id"]
    email = current_user["email"]
    is_guest = current_user.get("is_guest", False)

    # Determine session duration based on user type
    session_hours = GUEST_SESSION_TIMEOUT_HOURS if is_guest else SESSION_TIMEOUT_HOURS

    # Create new session, regenerating the old one; it keeps how the user logged in
    new_session_key, new_csrf_token = create_session(
        user_id, email, session_hours, is_guest, regenerate_from=session_key,
        auth_method=current_user.get("auth_method"), is_admin=current_user.get("is_admin", False),
        id_token=current_user.get("id_token")
    )

    max_age = session_hours * 3600
    set_session_cookies(response, new_session_key, new_csrf_token, max_age)

    logger.info(f"Session refreshed for user_id: {user_id}, expires in {max_age}s")

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
    :return: JSON response with user information, including user ID, email, name, guest
             session status, session expiry details and whether the user may manage the model
             catalog (`isAdmin`, in `user` and at the top level).
    :rtype: dict
    """
    logger.debug(f"Get current user - user_id: {current_user['user_id']}")

    # Check if CSRF cookie exists
    csrf_cookie = request.cookies.get("csrf_token")
    csrf_token = current_user.get("csrf_token")

    # If we have a CSRF token in session but no cookie, set the cookie
    if csrf_token and not csrf_cookie:
        logger.debug("CSRF cookie missing, setting from session")
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
    user = db.get_user_by_id(current_user["user_id"])
    user_data = {
        "id": current_user["user_id"],
        "user_id": current_user["user_id"],
        "email": current_user["email"],
        "name": user.get("name") if user else None,
        "is_guest": current_user.get("is_guest", False),
        "session_expires_at": current_user.get("expires_at"),
        "session_expires_in": current_user.get("expires_in"),
        "isAdmin": is_admin(current_user)
    }

    return {"user": user_data, "isAdmin": user_data["isAdmin"]}
