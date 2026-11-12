"""
MCP server API endpoints (docs/mcp.md): users' own servers and their OAuth sign-ins under
/api/mcp, the admins' servers (the agents') under /api/admin/mcp-servers.

Guests get 403 everywhere except GET /api/mcp/config and the answers to servers' questions
(an admin server can be available to guests): their data ends with their session, and they
never use their own servers.
"""
import logging
from typing import List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from backend.config import (FRONTEND_URL, MCP_ALLOW_PRIVATE_URLS, MCP_ENABLED, MCP_OAUTH_REDIRECT_URI,
                            MCP_STDIO_ENABLED)
from backend.models.mcp import (McpAutoAccept, McpConfig, McpConnectResult, McpElicitationAnswer, McpServerCreate,
                                McpServerList, McpServerOut, McpServerUpdate, McpTestResult)
from backend.security.auth import get_current_user, get_current_user_optional, is_admin, require_admin
from backend.security.logging import crud_logger
from backend.security.secrets import encryption_available
from backend.services.mcp import elicitation, oauth, servers, store
from backend.services.mcp.pool import pool
from backend.services.mcp.servers import McpError, config_reason, server_out, user_servers_reason
from backend.services.mcp.tools import test_server

logger = logging.getLogger(__name__)
router = APIRouter(tags=["MCP servers"])


def _http_error(error: McpError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=str(error))


async def require_member(current_user: dict = Depends(get_current_user)) -> dict:
    """A signed-in user: guests have no MCP servers of their own and no sign-ins."""
    if current_user.get("is_guest"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sign in to use MCP servers")
    return current_user


def _redirect_uri(request: Request) -> str:
    return MCP_OAUTH_REDIRECT_URI or str(request.url_for("mcp_oauth_callback"))


def _connected(user: dict) -> set:
    return store.connected_server_ids(user["user_id"])


def _accessible(server_id: int, user: dict) -> dict:
    """
    A server the user may test or sign in to: their own, an enabled admin server with OAuth, or
    (for admins) any admin server. Raises 404 otherwise.
    """
    row = store.get_server(server_id)
    if row is not None:
        if row["user_id"] == user["user_id"]:
            return row
        if row["user_id"] is None:
            if is_admin(user):
                return row
            if row["auth"] == "oauth" and row.get("enabled") is not False:
                return row
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"MCP server {server_id} not found")


# =========================================================================
# For signed-in users
# =========================================================================

@router.get("/api/mcp/config", response_model=McpConfig, operation_id="getMcpConfig",
            summary="What the server allows for MCP servers")
async def get_config(current_user: dict = Depends(get_current_user)):
    return McpConfig(enabled=MCP_ENABLED, userServers=user_servers_reason() is None, stdio=MCP_STDIO_ENABLED,
                     encryption=encryption_available(), privateUrls=MCP_ALLOW_PRIVATE_URLS,
                     reason=config_reason() or user_servers_reason())


@router.get("/api/mcp/servers", response_model=McpServerList, operation_id="listMcpServers",
            summary="The user's own servers and the agents' servers to sign in to")
async def list_servers(user: dict = Depends(require_member)):
    connected = _connected(user)
    auto = store.auto_accept_server_ids(user["user_id"])
    own = [server_out(row, connected, auto_accept=auto) for row in store.user_servers(user["user_id"])]
    full = is_admin(user)
    admin_rows = store.admin_servers(enabled_only=True)
    shared = [server_out(row, connected, full=full, auto_accept=auto) for row in admin_rows if row["auth"] == "oauth"]
    # The other agents' servers the user accepts confirmations of without asking, to turn that off
    others = [server_out(row, connected, full=False, auto_accept=auto) for row in admin_rows
              if row["auth"] != "oauth" and row["id"] in auto]
    return McpServerList(own=own, shared=shared, autoAccepted=others)


@router.post("/api/mcp/servers", response_model=McpServerOut, status_code=201, operation_id="createMcpServer",
             summary="Add an own MCP server")
async def create_server(req: McpServerCreate, user: dict = Depends(require_member)):
    try:
        row = servers.create_user_server(user["user_id"], req)
    except McpError as e:
        raise _http_error(e)
    crud_logger.info(f"MCP server {row['id']} ({row['slug']}) added by user {user['user_id']}")
    return server_out(row, _connected(user))


@router.put("/api/mcp/servers/{server_id}", response_model=McpServerOut, operation_id="updateMcpServer",
            summary="Change an own MCP server")
async def update_server(server_id: int, req: McpServerUpdate, user: dict = Depends(require_member)):
    try:
        old, row = servers.update_user_server(user["user_id"], server_id, req)
    except McpError as e:
        raise _http_error(e)
    await _after_change(old, row)
    return server_out(row, _connected(user))


@router.delete("/api/mcp/servers/{server_id}", status_code=204, operation_id="deleteMcpServer",
               summary="Delete an own MCP server")
async def delete_server(server_id: int, user: dict = Depends(require_member)):
    try:
        servers.own_server(user["user_id"], server_id)
    except McpError as e:
        raise _http_error(e)
    store.delete_server(server_id)
    await pool.close(server_id)
    crud_logger.info(f"MCP server {server_id} deleted by user {user['user_id']}")
    return Response(status_code=204)


@router.post("/api/mcp/servers/{server_id}/test", response_model=McpTestResult, operation_id="testMcpServer",
             summary="Connect to a server as the current user and list its tools")
async def test(server_id: int, user: dict = Depends(require_member)):
    return await test_server(_accessible(server_id, user), user)


@router.post("/api/mcp/servers/{server_id}/connect", response_model=McpConnectResult, operation_id="connectMcpServer",
             summary="Start an OAuth sign-in to a server")
async def connect(server_id: int, request: Request, user: dict = Depends(require_member)):
    row = _accessible(server_id, user)
    try:
        url = await oauth.start_sign_in(row, user, _redirect_uri(request))
    except McpError as e:
        raise _http_error(e)
    return McpConnectResult(authorizationUrl=url)


@router.delete("/api/mcp/servers/{server_id}/connection", status_code=204, operation_id="disconnectMcpServer",
               summary="Sign out of a server (delete the user's tokens)")
async def disconnect(server_id: int, user: dict = Depends(require_member)):
    _accessible(server_id, user)
    await oauth.sign_out(server_id, user["user_id"])
    return Response(status_code=204)


@router.get("/api/mcp/oauth/callback", operation_id="mcpOauthCallback", name="mcp_oauth_callback",
            summary="Where OAuth providers send the browser back after an MCP sign-in")
async def mcp_oauth_callback(state: Optional[str] = None, code: Optional[str] = None, iss: Optional[str] = None,
                             error: Optional[str] = None, user: Optional[dict] = Depends(get_current_user_optional)):
    # The session cookie (SameSite=Lax) comes along with the provider's top-level redirect
    try:
        server_id = await oauth.finish_sign_in(state or "", code, iss, error, user)
    except oauth.SignInFailed as e:
        logger.warning(f"MCP sign-in failed ({e.code}): {e}")
        params = {"error": e.code}
        if e.server_id is not None:
            params["server"] = e.server_id
        return RedirectResponse(f"{FRONTEND_URL}/mcp?{urlencode(params)}", status_code=302)
    return RedirectResponse(f"{FRONTEND_URL}/mcp?{urlencode({'connected': server_id})}", status_code=302)


@router.post("/api/mcp/elicitations/{question_id}", status_code=204, operation_id="answerMcpElicitation",
             summary="Answer a server's question to the user (elicitation) while its tool runs")
async def answer_elicitation(question_id: str, req: McpElicitationAnswer, user: dict = Depends(get_current_user)):
    try:
        elicitation.answer(question_id, user["user_id"], req.action, req.content, req.remember)
    except elicitation.AnswerError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    return Response(status_code=204)


@router.put("/api/mcp/servers/{server_id}/auto-accept", status_code=204, operation_id="setMcpAutoAccept",
            summary="Accept a server's confirmations without asking, in every conversation (or stop)")
async def set_auto_accept(server_id: int, req: McpAutoAccept, user: dict = Depends(require_member)):
    row = store.get_server(server_id)
    if row is None or (row["user_id"] is not None and row["user_id"] != user["user_id"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"MCP server {server_id} not found")
    store.set_auto_accept(server_id, user["user_id"], req.enabled)
    crud_logger.info(f"MCP server {server_id}: user {user['user_id']} "
                     f"{'accepts' if req.enabled else 'no longer accepts'} its confirmations without asking")
    return Response(status_code=204)


async def _after_change(old: dict, row: dict) -> None:
    """
    Connections follow a changed definition (the pool also notices a new fingerprint); another
    URL or OAuth client ends everyone's sign-ins, since their tokens belong to the old one.
    """
    if any(old.get(key) != row.get(key) for key in ("url", "oauth_client_id", "transport", "auth", "enabled")):
        await pool.close(row["id"])
    if old.get("url") != row.get("url") or old.get("oauth_client_id") != row.get("oauth_client_id"):
        store.delete_all_tokens(row["id"])


# =========================================================================
# Admin: the agents' servers
# =========================================================================

@router.get("/api/admin/mcp-servers", response_model=List[McpServerOut], operation_id="adminListMcpServers",
            summary="The admins' MCP servers")
async def admin_list(admin: dict = Depends(require_admin)):
    connected = _connected(admin)
    return [server_out(row, connected) for row in store.admin_servers()]


@router.post("/api/admin/mcp-servers", response_model=McpServerOut, status_code=201,
             operation_id="adminCreateMcpServer", summary="Add an MCP server for the agents")
async def admin_create(req: McpServerCreate, admin: dict = Depends(require_admin)):
    try:
        row = servers.create_admin_server(req)
    except McpError as e:
        raise _http_error(e)
    crud_logger.info(f"Admin MCP server {row['id']} ({row['slug']}) added by user {admin['user_id']}")
    return server_out(row, _connected(admin))


@router.put("/api/admin/mcp-servers/{server_id}", response_model=McpServerOut, operation_id="adminUpdateMcpServer",
            summary="Change an MCP server of the agents")
async def admin_update(server_id: int, req: McpServerUpdate, admin: dict = Depends(require_admin)):
    try:
        old, row = servers.update_admin_server(server_id, req)
    except McpError as e:
        raise _http_error(e)
    await _after_change(old, row)
    return server_out(row, _connected(admin))


@router.delete("/api/admin/mcp-servers/{server_id}", status_code=204, operation_id="adminDeleteMcpServer",
               summary="Delete an MCP server of the agents (also from the agents that use it)")
async def admin_delete(server_id: int, admin: dict = Depends(require_admin)):
    row = store.get_server(server_id)
    if row is None or row["user_id"] is not None:
        raise HTTPException(status_code=404, detail=f"MCP server {server_id} not found")
    store.delete_server(server_id)
    await pool.close(server_id)
    crud_logger.info(f"Admin MCP server {server_id} ({row['slug']}) deleted by user {admin['user_id']}")
    return Response(status_code=204)
