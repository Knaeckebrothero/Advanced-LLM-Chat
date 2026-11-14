"""
Storage of MCP servers, OAuth tokens and OAuth sign-ins in progress (docs/mcp.md, "Data").

Secrets (users' header values, tokens, dynamically registered clients, PKCE verifiers) are
encrypted with backend.security.secrets; this module stores and reads them as they are given.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, insert, null, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database import db
from backend.database.tables import mcp_auto_accept, mcp_oauth_flows, mcp_servers, mcp_tokens, personas
from backend.security.secrets import decrypt_json, encrypt_json

log = logging.getLogger(__name__)

# How long an OAuth sign-in may take from the redirect to the callback
FLOW_MAX_AGE = timedelta(minutes=15)

_JSONB_COLUMNS = {"args", "env", "headers", "tools"}
_WRITABLE = set(mcp_servers.c.keys()) - {"id", "created_at", "updated_at"}


def _utcnow() -> datetime:
    """Naive UTC, like the TIMESTAMP columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _values(values: dict) -> dict:
    unknown = set(values) - _WRITABLE
    if unknown:
        raise ValueError(f"Unknown column(s) for mcp_servers: {', '.join(sorted(unknown))}")
    return {key: (null() if value is None and key in _JSONB_COLUMNS else value) for key, value in values.items()}


def _order():
    """Higher sort order first, then name."""
    return (func.coalesce(mcp_servers.c.sort_order, 0).desc(), func.lower(mcp_servers.c.name), mcp_servers.c.id)


# ----- Servers -----

def get_server(server_id: int) -> Optional[dict]:
    with db.connection() as conn:
        row = conn.execute(select(mcp_servers).where(mcp_servers.c.id == server_id)).first()
        return dict(row._mapping) if row else None


def admin_servers(enabled_only: bool = False) -> list[dict]:
    """The admins' servers, by sort order and name."""
    query = select(mcp_servers).where(mcp_servers.c.user_id.is_(None))
    if enabled_only:
        query = query.where(mcp_servers.c.enabled.is_not(False))
    with db.connection() as conn:
        return [dict(row._mapping) for row in conn.execute(query.order_by(*_order()))]


def admin_servers_by_slug(slugs: list[str]) -> list[dict]:
    """The admin servers with these slugs, in the order of slugs (unknown ones are left out)."""
    if not slugs:
        return []
    with db.connection() as conn:
        rows = {row.slug: dict(row._mapping) for row in conn.execute(
            select(mcp_servers).where(mcp_servers.c.user_id.is_(None), mcp_servers.c.slug.in_(list(slugs))))}
    return [rows[slug] for slug in slugs if slug in rows]


def admin_server_by_slug(slug: str) -> Optional[dict]:
    found = admin_servers_by_slug([slug])
    return found[0] if found else None


def user_servers(user_id: int, enabled_only: bool = False) -> list[dict]:
    """A user's own servers, by name."""
    query = select(mcp_servers).where(mcp_servers.c.user_id == user_id)
    if enabled_only:
        query = query.where(mcp_servers.c.enabled.is_not(False))
    with db.connection() as conn:
        return [dict(row._mapping) for row in conn.execute(query.order_by(*_order()))]


def count_user_servers(user_id: int) -> int:
    with db.connection() as conn:
        return conn.execute(select(func.count()).select_from(mcp_servers)
                            .where(mcp_servers.c.user_id == user_id)).scalar_one()


def create_server(values: dict) -> dict:
    """Insert a server. Raises IntegrityError for a slug the owner uses already."""
    with db.connection() as conn:
        row = conn.execute(insert(mcp_servers).values(**_values(values)).returning(mcp_servers)).first()
        return dict(row._mapping)


def update_server(server_id: int, values: dict) -> Optional[dict]:
    with db.connection() as conn:
        if not values:
            row = conn.execute(select(mcp_servers).where(mcp_servers.c.id == server_id)).first()
        else:
            row = conn.execute(update(mcp_servers).where(mcp_servers.c.id == server_id)
                               .values(**_values(values)).returning(mcp_servers)).first()
        return dict(row._mapping) if row else None


def delete_server(server_id: int) -> Optional[dict]:
    """
    Delete a server (its tokens and sign-ins go with it). An admin server's slug is also removed
    from the agents that use it. Returns the deleted row, or None.
    """
    with db.connection() as conn:
        row = conn.execute(delete(mcp_servers).where(mcp_servers.c.id == server_id)
                           .returning(mcp_servers)).first()
        if row is None:
            return None
        if row.user_id is None:
            conn.execute(
                text("UPDATE personas SET mcp_servers = (SELECT coalesce(jsonb_agg(s), '[]'::jsonb) "
                     "FROM jsonb_array_elements_text(mcp_servers) s WHERE s <> :slug) "
                     "WHERE mcp_servers ? :slug"),
                {"slug": row.slug})
        return dict(row._mapping)


def save_oauth_client(server_id: int, client: dict) -> None:
    """Keep a dynamically registered client (encrypted) for the next sign-ins."""
    with db.connection() as conn:
        conn.execute(update(mcp_servers).where(mcp_servers.c.id == server_id)
                     .values(oauth_client_encrypted=encrypt_json(client)))


def personas_using(slug: str) -> list[dict]:
    """The agents (id, name) that use an admin server."""
    with db.connection() as conn:
        rows = conn.execute(select(personas.c.id, personas.c.name)
                            .where(text("personas.mcp_servers ? :slug")).params(slug=slug))
        return [dict(row._mapping) for row in rows]


# ----- OAuth tokens -----

def get_tokens(server_id: int, user_id: int) -> Optional[dict]:
    """A user's tokens for a server (decrypted), or None."""
    with db.connection() as conn:
        row = conn.execute(select(mcp_tokens.c.tokens_encrypted).where(
            mcp_tokens.c.server_id == server_id, mcp_tokens.c.user_id == user_id)).first()
    return decrypt_json(row.tokens_encrypted) if row else None


def save_tokens(server_id: int, user_id: int, tokens: dict) -> None:
    """Store a user's tokens for a server (tokens["expires_at"]: epoch seconds or None)."""
    expires = tokens.get("expires_at")
    expires_at = datetime.fromtimestamp(expires, timezone.utc).replace(tzinfo=None) if expires else None
    values = {"tokens_encrypted": encrypt_json(tokens), "expires_at": expires_at}
    with db.connection() as conn:
        conn.execute(pg_insert(mcp_tokens).values(server_id=server_id, user_id=user_id, **values)
                     .on_conflict_do_update(index_elements=["server_id", "user_id"], set_=values))


def delete_tokens(server_id: int, user_id: int) -> bool:
    with db.connection() as conn:
        return conn.execute(delete(mcp_tokens).where(
            mcp_tokens.c.server_id == server_id, mcp_tokens.c.user_id == user_id)).rowcount > 0


def delete_all_tokens(server_id: int) -> None:
    """Everyone's sign-ins to a server."""
    with db.connection() as conn:
        conn.execute(delete(mcp_tokens).where(mcp_tokens.c.server_id == server_id))


def connected_server_ids(user_id: int) -> set[int]:
    """The servers a user has signed in to."""
    with db.connection() as conn:
        return {row.server_id for row in conn.execute(
            select(mcp_tokens.c.server_id).where(mcp_tokens.c.user_id == user_id))}


# ----- Confirmations accepted without asking (elicitation) -----

def auto_accept_scope(server_id: int, user_id: int, conversation_id: Optional[str]) -> Optional[str]:
    """Whether the user accepts the server's confirmations without being asked: "always", "conversation" or None."""
    with db.connection() as conn:
        rows = conn.execute(select(mcp_auto_accept.c.conversation_id).where(
            mcp_auto_accept.c.server_id == server_id, mcp_auto_accept.c.user_id == user_id)).all()
    scopes = {row.conversation_id for row in rows}
    if None in scopes:
        return "always"
    if conversation_id is not None and conversation_id in scopes:
        return "conversation"
    return None


def set_auto_accept(server_id: int, user_id: int, enabled: bool, conversation_id: Optional[str] = None) -> None:
    """Accept the server's confirmations without asking, in one conversation or (None) in every one; or stop."""
    where = [mcp_auto_accept.c.server_id == server_id, mcp_auto_accept.c.user_id == user_id,
             mcp_auto_accept.c.conversation_id.is_(None) if conversation_id is None
             else mcp_auto_accept.c.conversation_id == conversation_id]
    with db.connection() as conn:
        exists = conn.execute(select(mcp_auto_accept.c.id).where(*where)).first() is not None
        if enabled and not exists:
            conn.execute(insert(mcp_auto_accept).values(server_id=server_id, user_id=user_id,
                                                        conversation_id=conversation_id))
        elif not enabled and exists:
            conn.execute(delete(mcp_auto_accept).where(*where))


def auto_accept_server_ids(user_id: int) -> set[int]:
    """The servers whose confirmations the user accepts in every conversation."""
    with db.connection() as conn:
        return {row.server_id for row in conn.execute(select(mcp_auto_accept.c.server_id).where(
            mcp_auto_accept.c.user_id == user_id, mcp_auto_accept.c.conversation_id.is_(None)))}


# ----- OAuth sign-ins in progress -----

def save_flow(state: str, server_id: int, user_id: int, flow: dict) -> None:
    with db.connection() as conn:
        conn.execute(delete(mcp_oauth_flows).where(mcp_oauth_flows.c.created_at < _utcnow() - FLOW_MAX_AGE))
        conn.execute(insert(mcp_oauth_flows).values(state=state, server_id=server_id, user_id=user_id,
                                                    flow_encrypted=encrypt_json(flow), created_at=_utcnow()))


def pop_flow(state: str) -> Optional[dict]:
    """
    Take a sign-in in progress (it can only be finished once): {"server_id", "user_id", "flow"},
    or None if it doesn't exist or is too old.
    """
    with db.connection() as conn:
        row = conn.execute(delete(mcp_oauth_flows).where(mcp_oauth_flows.c.state == state)
                           .returning(mcp_oauth_flows)).first()
    if row is None or row.created_at < _utcnow() - FLOW_MAX_AGE:
        return None
    return {"server_id": row.server_id, "user_id": row.user_id, "flow": decrypt_json(row.flow_encrypted)}
