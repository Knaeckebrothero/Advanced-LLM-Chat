"""
Login through an OpenID Connect provider such as Keycloak (AUTH_MODE=oidc).

The backend is a confidential client and runs the authorization code flow with PKCE
itself, so the browser never sees a token: /api/auth/oidc/login sends the browser to
the provider, /api/auth/oidc/callback swaps the code for tokens, checks them and logs
the user in with the same session cookie as every other login (backend/api/auth.py).
Settings and the Keycloak setup: docs/authentication.md.
"""
import base64
import binascii
import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus, urlencode

import httpx
import jwt

from backend.config import (ADMIN_EMAILS, AUTH_MODE, FRONTEND_URL, OIDC_ADMIN_ROLE, OIDC_CLIENT_ID,
                            OIDC_CLIENT_SECRET, OIDC_DISCOVERY_URL, OIDC_ISSUER, OIDC_REQUIRED_ROLE,
                            OIDC_SCOPES)
from backend.database import db

log = logging.getLogger(__name__)

# How long the provider's metadata and signing keys are kept before they're read again
METADATA_MAX_AGE = 3600
# Signature algorithms accepted for tokens (never "none" or the HMAC ones)
ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512"]
# Allowed clock difference between the backend and the provider, in seconds
LEEWAY = 60
# Timeout of the backend's requests to the provider, in seconds
TIMEOUT = 10.0
# How long a started login may take, in seconds (the lifetime of its cookie)
LOGIN_MAX_AGE = 600

_metadata: Optional[dict] = None
_metadata_at = 0.0
_keys: Optional[jwt.PyJWKSet] = None
_keys_at = 0.0


class LoginRefused(Exception):
    """A login the provider accepted but the app refuses; the reason is shown on the login page."""

    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason


@dataclass
class OidcLogin:
    """A finished login: who the user is, their roles, and the ID token for logging out."""
    sub: str
    email: Optional[str]
    email_verified: bool
    name: Optional[str]
    roles: set[str]
    id_token: str


def check_config() -> None:
    """
    Checks the authentication settings at startup.

    :raises ValueError: If AUTH_MODE is unknown, or AUTH_MODE=oidc lacks a required setting.
    """
    if AUTH_MODE not in ("oidc", "mock", "none"):
        raise ValueError(f"AUTH_MODE must be oidc, mock or none, not {AUTH_MODE!r}")
    if AUTH_MODE == "oidc":
        missing = [name for name, value in (("OIDC_ISSUER", OIDC_ISSUER), ("OIDC_CLIENT_ID", OIDC_CLIENT_ID),
                                            ("OIDC_CLIENT_SECRET", OIDC_CLIENT_SECRET)) if not value]
        if missing:
            raise ValueError(f"AUTH_MODE=oidc needs {', '.join(missing)}")


async def metadata() -> dict:
    """
    The provider's metadata (OIDC discovery), read from OIDC_DISCOVERY_URL and cached.

    :raises ValueError: If the provider's issuer isn't OIDC_ISSUER.
    :raises httpx.HTTPError: If the provider can't be reached.
    """
    global _metadata, _metadata_at
    if _metadata and time.monotonic() - _metadata_at < METADATA_MAX_AGE:
        return _metadata
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(OIDC_DISCOVERY_URL)
        response.raise_for_status()
        data = response.json()
    if str(data.get("issuer", "")).rstrip("/") != OIDC_ISSUER:
        raise ValueError(f"The provider's issuer is {data.get('issuer')!r}, OIDC_ISSUER is {OIDC_ISSUER!r}")
    _metadata, _metadata_at = data, time.monotonic()
    return data


async def _load_keys() -> None:
    """Reads the provider's signing keys (its JWKS)."""
    global _keys, _keys_at
    meta = await metadata()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(meta["jwks_uri"])
        response.raise_for_status()
    _keys, _keys_at = jwt.PyJWKSet.from_dict(response.json()), time.monotonic()


def _find_key(kid: Optional[str]) -> Optional[jwt.PyJWK]:
    for key in _keys.keys if _keys else []:
        if key.public_key_use in (None, "sig") and (kid is None or key.key_id == kid):
            return key
    return None


async def _signing_key(token: str) -> jwt.PyJWK:
    """The provider's key that signed the token; the keys are read again for an unknown key id."""
    kid = jwt.get_unverified_header(token).get("kid")
    if _keys is None or time.monotonic() - _keys_at > METADATA_MAX_AGE:
        await _load_keys()
    key = _find_key(kid)
    if key is None:
        # The provider may have rotated its keys
        await _load_keys()
        key = _find_key(kid)
    if key is None:
        raise ValueError(f"The provider has no signing key {kid!r}")
    return key


async def _verify(token: str, audience: Optional[str]) -> dict:
    """Checks a token's signature, issuer, lifetime and (if given) audience, and returns its claims."""
    key = await _signing_key(token)
    meta = await metadata()
    options = {"require": ["exp", "iat", "iss", "sub"]}
    if audience is None:
        options["verify_aud"] = False
    return jwt.decode(token, key=key, algorithms=ALGORITHMS, audience=audience, issuer=meta["issuer"],
                      leeway=LEEWAY, options=options)


def _strings(value) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _roles(claims: dict) -> set[str]:
    """Keycloak's realm and client roles, and the roles and groups claims other providers use."""
    realm_access = claims.get("realm_access")
    client_access = claims.get("resource_access")
    client_access = client_access.get(OIDC_CLIENT_ID) if isinstance(client_access, dict) else None
    roles = set(_strings(realm_access.get("roles"))) if isinstance(realm_access, dict) else set()
    if isinstance(client_access, dict):
        roles |= set(_strings(client_access.get("roles")))
    for name in ("roles", "groups"):
        values = _strings(claims.get(name))
        # Keycloak's group claim has paths like /family
        roles |= set(values) | {value.lstrip("/") for value in values}
    return roles


def _pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


async def authorization_url(redirect_uri: str) -> tuple[str, dict]:
    """
    Starts a login: the provider's login page to send the browser to, and what the callback
    needs to finish the login (state, nonce, PKCE verifier), kept in a cookie meanwhile.

    :param redirect_uri: The backend's callback address, as the provider redirects to it.
    :return: The authorization URL and the pending login.
    """
    meta = await metadata()
    pending = {
        "state": secrets.token_urlsafe(32),
        "nonce": secrets.token_urlsafe(32),
        "verifier": secrets.token_urlsafe(64),
        "redirect_uri": redirect_uri,
    }
    params = {
        "response_type": "code",
        "client_id": OIDC_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": OIDC_SCOPES,
        "state": pending["state"],
        "nonce": pending["nonce"],
        "code_challenge": _pkce_challenge(pending["verifier"]),
        "code_challenge_method": "S256",
    }
    endpoint = meta["authorization_endpoint"]
    return f"{endpoint}{'&' if '?' in endpoint else '?'}{urlencode(params)}", pending


def encode_pending(pending: dict) -> str:
    """The pending login as a cookie value (base64url without padding, so it needs no quoting)."""
    return base64.urlsafe_b64encode(json.dumps(pending).encode()).decode().rstrip("=")


def decode_pending(value: Optional[str]) -> Optional[dict]:
    """The pending login from its cookie, or None if the cookie is missing or broken."""
    if not value:
        return None
    try:
        pending = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
    except (ValueError, binascii.Error):
        return None
    keys = ("state", "nonce", "verifier", "redirect_uri")
    if not isinstance(pending, dict) or not all(isinstance(pending.get(key), str) for key in keys):
        return None
    return pending


async def finish_login(code: str, pending: dict) -> OidcLogin:
    """
    Swaps the authorization code for tokens and checks them.

    :param code: The code from the provider's redirect.
    :param pending: The login started by authorization_url (its state is already checked).
    :return: The login.
    :raises ValueError: If the provider refuses the code or a token is invalid.
    """
    meta = await metadata()
    # client_secret_basic, with the form encoding RFC 6749 asks for
    auth = httpx.BasicAuth(quote_plus(OIDC_CLIENT_ID), quote_plus(OIDC_CLIENT_SECRET))
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(meta["token_endpoint"], auth=auth, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": pending["redirect_uri"],
            "code_verifier": pending["verifier"],
        })
    if response.status_code != 200:
        raise ValueError(f"The provider refused the code: {response.status_code} {response.text[:200]}")
    tokens = response.json()
    id_token = tokens.get("id_token")
    if not id_token:
        raise ValueError("The provider sent no ID token (is 'openid' in OIDC_SCOPES?)")

    claims = await _verify(id_token, audience=OIDC_CLIENT_ID)
    if not secrets.compare_digest(str(claims.get("nonce", "")), pending["nonce"]):
        raise ValueError("The ID token's nonce doesn't match the login")
    audiences = claims.get("aud")
    if isinstance(audiences, list) and len(audiences) > 1 and claims.get("azp") != OIDC_CLIENT_ID:
        raise ValueError("The ID token was issued to another client")

    # Keycloak puts the realm and client roles into the access token
    roles = _roles(claims)
    access_token = tokens.get("access_token")
    if access_token:
        try:
            access_claims = await _verify(access_token, audience=None)
        except (jwt.PyJWTError, ValueError):
            access_claims = {}  # Not a JWT (other providers), or not one we can check
        if access_claims.get("sub") == claims["sub"]:
            roles |= _roles(access_claims)

    email = claims.get("email") if isinstance(claims.get("email"), str) else None
    name = claims.get("name") or claims.get("preferred_username")
    return OidcLogin(
        sub=str(claims["sub"]),
        email=email.strip() if email else None,
        email_verified=claims.get("email_verified") in (True, "true"),
        name=name if isinstance(name, str) else None,
        roles=roles,
        id_token=id_token,
    )


def user_for_login(login: OidcLogin) -> dict:
    """
    The user a login belongs to: the one linked to its subject id; else an existing user
    with the same verified email, linked now so its chats are kept; else a new user.

    :raises LoginRefused: If the user lacks OIDC_REQUIRED_ROLE ("forbidden"), or the email
        belongs to another user and can't be linked ("email_in_use").
    """
    if OIDC_REQUIRED_ROLE and OIDC_REQUIRED_ROLE not in login.roles:
        raise LoginRefused("forbidden", f"The user lacks the role {OIDC_REQUIRED_ROLE}")

    user = db.get_user_by_oidc_sub(login.sub)
    if user:
        # Follow name and email changes at the provider (unless another user has the email)
        name = login.name if login.name and login.name != user.get("name") else None
        email = login.email if login.email and login.email.lower() != user["email"].lower() else None
        if email and db.get_user_by_email(email):
            email = None
        if name or email:
            user = db.update_user(user["id"], name=name, email=email)
        return user

    # Users need an email; a provider may not share one
    email = login.email or f"oidc_{hashlib.sha256(login.sub.encode()).hexdigest()[:16]}@oidc.invalid"
    existing = db.get_user_by_email(email)
    if existing:
        if existing.get("is_guest") or existing.get("oidc_sub") or not login.email_verified:
            raise LoginRefused("email_in_use", f"User {existing['id']} has the email and can't be linked")
        log.info(f"Linking user {existing['id']} to its OIDC login by its verified email")
        return db.link_oidc_user(existing["id"], login.sub)
    return db.create_user(email, login.name or email.split("@")[0], oidc_sub=login.sub)


def grants_admin(login: OidcLogin) -> bool:
    """Whether the login makes the user an admin: OIDC_ADMIN_ROLE, or a verified email in ADMIN_EMAILS."""
    if OIDC_ADMIN_ROLE and OIDC_ADMIN_ROLE in login.roles:
        return True
    return login.email_verified and bool(login.email) and login.email.lower() in ADMIN_EMAILS


async def logout_url(id_token: Optional[str]) -> Optional[str]:
    """
    Where the browser ends the provider's session after the app's logout (RP-initiated
    logout), returning to FRONTEND_URL; None if the provider doesn't offer that.
    """
    try:
        endpoint = (await metadata()).get("end_session_endpoint")
    except (httpx.HTTPError, ValueError) as e:
        log.warning(f"Can't reach the OIDC provider for the logout: {e}")
        return None
    if not endpoint:
        return None
    params = {"client_id": OIDC_CLIENT_ID, "post_logout_redirect_uri": FRONTEND_URL}
    if id_token:
        params["id_token_hint"] = id_token
    return f"{endpoint}{'&' if '?' in endpoint else '?'}{urlencode(params)}"
