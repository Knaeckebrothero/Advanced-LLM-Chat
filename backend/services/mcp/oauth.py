"""
OAuth sign-in to MCP servers and the tokens of a connection (docs/mcp.md, "OAuth sign-in").

The SDK's OAuthClientProvider runs the whole flow inside one request, waiting for the browser's
callback; a web app gets the callback in another request. So the flow is split here, with the
SDK's helpers for discovery, registration and token responses:

- start_sign_in(): discovery (protected resource metadata, authorization server metadata), the
  client (configured, registered earlier, or dynamic client registration), PKCE; the flow waits
  in mcp_oauth_flows and the browser goes to the authorization URL.
- finish_sign_in(): the callback swaps the code for tokens, stored encrypted per user.
- TokenAuth: sends a connection's access token and refreshes it when it expired or the server
  answers 401. A failed refresh deletes the tokens (the user signs in again).
"""
import asyncio
import base64
import logging
import os
import secrets
import time
from typing import Optional
from urllib.parse import quote, urlencode, urlparse

import httpx2
from mcp.client.auth import PKCEParameters
from mcp.client.auth.utils import (
    build_oauth_authorization_server_metadata_discovery_urls,
    build_protected_resource_metadata_discovery_urls,
    create_client_registration_request,
    create_oauth_metadata_request,
    extract_resource_metadata_from_www_auth,
    extract_scope_from_www_auth,
    get_client_metadata_scopes,
    handle_auth_metadata_response,
    handle_protected_resource_response,
    handle_registration_response,
    handle_token_response_scopes,
    issuers_match,
)
from mcp.shared.auth import OAuthClientMetadata, OAuthMetadata
from mcp.shared.auth_utils import check_resource_allowed, resource_url_from_server_url
from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS

from backend.config import MCP_ALLOW_PRIVATE_URLS, MCP_CONNECT_TIMEOUT, MCP_OAUTH_CLIENT_NAME
from backend.security.auth import is_admin
from backend.security.secrets import SecretUnavailable, decrypt_json, encryption_available, NO_KEY_REASON
from backend.services.mcp import store
from backend.services.mcp.pool import McpAuthRequired, describe_error, http_client, pool
from backend.services.mcp.servers import McpError, McpUnavailable, SECRET_ENV_PATTERN, resolve

log = logging.getLogger(__name__)

# Refresh a token this many seconds before it expires
EXPIRY_MARGIN = 60
_PROBE = {
    "jsonrpc": "2.0", "id": 0, "method": "initialize",
    "params": {"protocolVersion": HANDSHAKE_PROTOCOL_VERSIONS[-1], "capabilities": {},
               "clientInfo": {"name": "advanced-llm-chat", "version": "1.0"}},
}


class SignInFailed(Exception):
    """An OAuth callback that can't be finished; code is the error the frontend shows."""

    def __init__(self, code: str, message: str, server_id: Optional[int] = None):
        super().__init__(message)
        self.code = code
        self.server_id = server_id


def guarded(row: dict, user: Optional[dict]) -> bool:
    """Whether connections for this server may only reach public addresses (users' own servers)."""
    return row["user_id"] is not None and not MCP_ALLOW_PRIVATE_URLS and not is_admin(user)


def _timeout() -> httpx2.Timeout:
    return httpx2.Timeout(MCP_CONNECT_TIMEOUT)


def _client_secret(client: dict) -> Optional[str]:
    if client.get("client_secret"):
        return client["client_secret"]
    name = client.get("client_secret_env")
    if name and SECRET_ENV_PATTERN.match(name):
        return os.getenv(name) or None
    return None


def _client_auth(client: dict, data: dict) -> tuple[dict, dict]:
    """The form data and headers of a token request, with the client's authentication."""
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    data = {**data, "client_id": client["client_id"]}
    secret = _client_secret(client)
    if secret:
        if client.get("auth_method") == "client_secret_post":
            data["client_secret"] = secret
        else:
            credentials = f"{quote(client['client_id'], safe='')}:{quote(secret, safe='')}"
            headers["Authorization"] = f"Basic {base64.b64encode(credentials.encode()).decode()}"
    return data, headers


def _secret_method(asm: OAuthMetadata) -> str:
    supported = asm.token_endpoint_auth_methods_supported
    if supported and "client_secret_basic" not in supported and "client_secret_post" in supported:
        return "client_secret_post"
    return "client_secret_basic"


def _token_record(token, flow: dict, previous: Optional[dict] = None) -> dict:
    """What is stored of a token response: the tokens and what a refresh needs."""
    previous = previous or {}
    return {
        "access_token": token.access_token,
        # A refresh response may leave the refresh token out: the old one stays valid
        "refresh_token": token.refresh_token or previous.get("refresh_token"),
        "expires_at": time.time() + int(token.expires_in) if token.expires_in else None,
        "scope": token.scope or previous.get("scope") or flow.get("scope"),
        "token_endpoint": flow["token_endpoint"],
        "client": flow["client"],
        "resource": flow.get("resource"),
        "issuer": flow.get("issuer"),
    }


# =========================================================================
# Sign-in
# =========================================================================

async def _discover(http: httpx2.AsyncClient, url: str):
    """The server's protected resource metadata (or None), authorization server metadata and scope hint."""
    www_url = www_scope = None
    try:
        async with http.stream("POST", url, json=_PROBE,
                               headers={"Accept": "application/json, text/event-stream"}) as response:
            if response.status_code == 401:
                www_url = extract_resource_metadata_from_www_auth(response)
                www_scope = extract_scope_from_www_auth(response)
    except httpx2.HTTPError as e:
        raise McpError(f"Can't reach the server: {describe_error(e)}")

    prm = None
    for candidate in build_protected_resource_metadata_discovery_urls(www_url, url):
        try:
            prm = await handle_protected_resource_response(await http.send(create_oauth_metadata_request(candidate)))
        except httpx2.HTTPError as e:
            log.debug(f"Protected resource metadata at {candidate}: {e}")
        if prm:
            break
    auth_server = str(prm.authorization_servers[0]) if prm else None

    asm = None
    for candidate in build_oauth_authorization_server_metadata_discovery_urls(auth_server, url):
        try:
            ok, metadata = await handle_auth_metadata_response(await http.send(create_oauth_metadata_request(candidate)))
        except httpx2.HTTPError as e:
            log.debug(f"Authorization server metadata at {candidate}: {e}")
            continue
        if metadata:
            asm = metadata
            break
        if not ok:
            break
    if asm is None:
        raise McpError("The server offers no OAuth sign-in (no authorization server metadata found)")
    if auth_server and not issuers_match(str(asm.issuer), auth_server):
        raise McpError(f"The authorization server's metadata names another issuer ({asm.issuer})")
    return prm, asm, www_scope


async def _client_for(http: httpx2.AsyncClient, row: dict, asm: OAuthMetadata, redirect_uri: str,
                      scope: Optional[str]) -> dict:
    """The OAuth client to sign in with: configured, registered earlier, or registered now."""
    issuer = str(asm.issuer)
    if row.get("oauth_client_id"):
        client = {"client_id": row["oauth_client_id"], "auth_method": None}
        if row["user_id"] is None and row.get("oauth_client_secret_env"):
            client["client_secret_env"] = row["oauth_client_secret_env"]
            client["auth_method"] = _secret_method(asm)
        return client

    if row.get("oauth_client_encrypted"):
        try:
            stored = decrypt_json(row["oauth_client_encrypted"])
            if stored.get("redirect_uri") == redirect_uri and issuers_match(stored.get("issuer") or "", issuer):
                return stored
        except SecretUnavailable as e:
            log.warning(f"MCP server {row['id']}: the registered client can't be read ({e}); registering again")

    if not asm.registration_endpoint:
        raise McpError("The server's authorization server doesn't register clients itself: enter a client ID "
                       "(registered there with the redirect URI " + redirect_uri + ")")
    supported = asm.token_endpoint_auth_methods_supported
    method = "none" if not supported or "none" in supported else _secret_method(asm)
    metadata = OAuthClientMetadata(
        redirect_uris=[redirect_uri],
        client_name=MCP_OAUTH_CLIENT_NAME,
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method=method,
        application_type="web",
        scope=scope,
    )
    origin = f"{urlparse(str(asm.issuer)).scheme}://{urlparse(str(asm.issuer)).netloc}"
    try:
        info = await handle_registration_response(
            await http.send(create_client_registration_request(asm, metadata, origin)))
    except Exception as e:
        raise McpError(f"Registering with the server's authorization server failed: {describe_error(e)}")
    client = {
        "client_id": info.client_id,
        "client_secret": info.client_secret,
        "auth_method": info.token_endpoint_auth_method or ("client_secret_basic" if info.client_secret else "none"),
        "redirect_uri": redirect_uri,
        "issuer": issuer,
    }
    await asyncio.to_thread(store.save_oauth_client, row["id"], client)
    return client


async def start_sign_in(row: dict, user: dict, redirect_uri: str) -> str:
    """
    Start an OAuth sign-in of the user to the server.

    Returns:
        The authorization URL the browser goes to.

    Raises:
        McpUnavailable: No ENCRYPTION_KEY, or the server's variables aren't set.
        McpError: The server offers no usable sign-in.
    """
    if not encryption_available():
        raise McpUnavailable(f"Signing in needs encryption: {NO_KEY_REASON}")
    if row["auth"] != "oauth":
        raise McpError("This server doesn't use OAuth")
    spec = resolve(row)
    async with http_client(guarded=guarded(row, user), timeout=_timeout()) as http:
        prm, asm, www_scope = await _discover(http, spec.url)
        if asm.code_challenge_methods_supported and "S256" not in asm.code_challenge_methods_supported:
            raise McpError("The authorization server doesn't support PKCE (S256)")
        scope = row.get("oauth_scopes") or get_client_metadata_scopes(www_scope, prm, asm)
        client = await _client_for(http, row, asm, redirect_uri, scope)

    resource = resource_url_from_server_url(spec.url)
    if prm and prm.resource and check_resource_allowed(resource, str(prm.resource)):
        resource = str(prm.resource)
    pkce = PKCEParameters.generate()
    state = secrets.token_urlsafe(32)
    params = {
        "response_type": "code",
        "client_id": client["client_id"],
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": pkce.code_challenge,
        "code_challenge_method": "S256",
    }
    if prm is not None:
        params["resource"] = resource  # RFC 8707
    if scope:
        params["scope"] = scope
    flow = {
        "verifier": pkce.code_verifier,
        "redirect_uri": redirect_uri,
        "token_endpoint": str(asm.token_endpoint),
        "issuer": str(asm.issuer),
        "iss_supported": bool(getattr(asm, "authorization_response_iss_parameter_supported", False)),
        "client": {key: value for key, value in client.items() if key not in ("redirect_uri", "issuer")},
        "resource": resource if prm is not None else None,
        "scope": scope,
    }
    await asyncio.to_thread(store.save_flow, state, row["id"], user["user_id"], flow)
    endpoint = str(asm.authorization_endpoint)
    url = f"{endpoint}{'&' if '?' in endpoint else '?'}{urlencode(params)}"
    log.info(f"MCP sign-in started: server {row['id']} ({row['slug']}), user {user['user_id']}")
    return url


async def finish_sign_in(state: str, code: Optional[str], iss: Optional[str], error: Optional[str],
                         user: Optional[dict]) -> int:
    """
    Finish a sign-in from the provider's callback: swap the code for tokens and store them.

    Returns:
        The server's id.

    Raises:
        SignInFailed: with code "expired", "denied", "wrong_user" or "failed".
    """
    pending = await asyncio.to_thread(store.pop_flow, state) if state else None
    if pending is None:
        raise SignInFailed("expired", "The sign-in expired or was finished already")
    server_id = pending["server_id"]
    if user is None or user.get("user_id") != pending["user_id"]:
        raise SignInFailed("wrong_user", "The sign-in was started by another user", server_id)
    if error:
        raise SignInFailed("denied", f"The provider returned the error {error}", server_id)
    flow = pending["flow"]
    if iss is not None and not issuers_match(iss, flow.get("issuer") or ""):
        raise SignInFailed("failed", f"The callback came from another issuer ({iss})", server_id)
    if iss is None and flow.get("iss_supported"):
        raise SignInFailed("failed", "The callback is missing the issuer the provider announced", server_id)
    if not code:
        raise SignInFailed("failed", "The callback has no authorization code", server_id)

    row = await asyncio.to_thread(store.get_server, server_id)
    if row is None:
        raise SignInFailed("failed", "The server was deleted", server_id)
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": flow["redirect_uri"],
            "code_verifier": flow["verifier"]}
    if flow.get("resource"):
        data["resource"] = flow["resource"]
    data, headers = _client_auth(flow["client"], data)
    try:
        async with http_client(guarded=guarded(row, user), timeout=_timeout()) as http:
            response = await http.post(flow["token_endpoint"], data=data, headers=headers)
            if response.status_code != 200:
                body = (await response.aread()).decode(errors="replace")[:300]
                raise SignInFailed("failed", f"The token request failed ({response.status_code}): {body}", server_id)
            token = await handle_token_response_scopes(response)
    except SignInFailed:
        raise
    except Exception as e:
        raise SignInFailed("failed", f"The token request failed: {describe_error(e)}", server_id)

    await asyncio.to_thread(store.save_tokens, server_id, user["user_id"], _token_record(token, flow))
    await pool.close(server_id, user["user_id"])
    log.info(f"MCP sign-in finished: server {server_id}, user {user['user_id']}")
    return server_id


async def sign_out(server_id: int, user_id: int) -> bool:
    deleted = await asyncio.to_thread(store.delete_tokens, server_id, user_id)
    await pool.close(server_id, user_id)
    return deleted


def has_tokens(server_id: int, user_id: int) -> bool:
    try:
        return store.get_tokens(server_id, user_id) is not None
    except SecretUnavailable:
        return False


# =========================================================================
# Tokens of a connection
# =========================================================================

class TokenAuth(httpx2.Auth):
    """Bearer tokens of a user's sign-in to a server, refreshed when needed."""

    def __init__(self, server_id: int, user_id: int, server_name: str, guarded_client: bool):
        self.server_id = server_id
        self.user_id = user_id
        self.server_name = server_name
        self.guarded = guarded_client
        self._tokens: Optional[dict] = None
        self._lock = asyncio.Lock()
        # Why the sign-in failed; the transport may wrap the exception into its own errors
        self.failed: Optional[str] = None

    def _required(self, why: str) -> McpAuthRequired:
        self.failed = f"{why}: sign in to {self.server_name} on the MCP servers page"
        return McpAuthRequired(self.failed)

    async def _load(self) -> dict:
        if self._tokens is None:
            try:
                self._tokens = await asyncio.to_thread(store.get_tokens, self.server_id, self.user_id)
            except SecretUnavailable as e:
                raise self._required(str(e))
            if self._tokens is None:
                raise self._required("Not signed in")
        return self._tokens

    async def _refresh(self, used: dict) -> dict:
        async with self._lock:
            current = await self._load()
            if current.get("access_token") != used.get("access_token"):
                return current  # Another request refreshed it meanwhile
            if not current.get("refresh_token"):
                await asyncio.to_thread(store.delete_tokens, self.server_id, self.user_id)
                self._tokens = None
                raise self._required("The sign-in expired")
            data = {"grant_type": "refresh_token", "refresh_token": current["refresh_token"]}
            if current.get("resource"):
                data["resource"] = current["resource"]
            data, headers = _client_auth(current["client"], data)
            async with http_client(guarded=self.guarded, timeout=_timeout()) as http:
                response = await http.post(current["token_endpoint"], data=data, headers=headers)
                if response.status_code != 200:
                    log.info(f"MCP token refresh failed for server {self.server_id}, user {self.user_id}: "
                             f"{response.status_code}")
                    await asyncio.to_thread(store.delete_tokens, self.server_id, self.user_id)
                    self._tokens = None
                    raise self._required("The sign-in expired")
                token = await handle_token_response_scopes(response)
            record = _token_record(token, current, previous=current)
            await asyncio.to_thread(store.save_tokens, self.server_id, self.user_id, record)
            self._tokens = record
            return record

    async def async_auth_flow(self, request: httpx2.Request):
        tokens = await self._load()
        expires = tokens.get("expires_at")
        if expires and expires - EXPIRY_MARGIN < time.time() and tokens.get("refresh_token"):
            tokens = await self._refresh(tokens)
        request.headers["Authorization"] = f"Bearer {tokens['access_token']}"
        response = yield request
        if response.status_code == 401:
            tokens = await self._refresh(tokens)
            request.headers["Authorization"] = f"Bearer {tokens['access_token']}"
            yield request
