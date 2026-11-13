"""
What guests may use (docs/authentication.md).

Guests chat without an account, so their use is counted per client address in the table
guest_usage: one counter per address and kind of request (GUEST_LIMITS in backend/config.py),
e.g. the answers of a model or the uploaded files. A counter starts again GUEST_LIMIT_HOURS
after its last counted request. Signed-in users are not limited.

The address is the connection's (client_ip): behind a proxy, uvicorn must trust that proxy and
only that proxy for it (FORWARDED_ALLOW_IPS), or a client could claim any address.
"""
import ipaddress
import logging
from datetime import datetime, timedelta, UTC
from typing import Optional

from fastapi import Depends, HTTPException, Request

from backend.config import GUEST_LIMIT_HOURS, GUEST_LIMITS, GUEST_MAX_REQUEST_KB
from backend.database import db
from backend.security.auth import client_ip, get_current_user_optional

log = logging.getLogger(__name__)

WINDOW = timedelta(hours=GUEST_LIMIT_HOURS)


def address_key(ip: Optional[str]) -> str:
    """
    The address a guest is counted under.

    An IPv4 address counts as it is. An IPv6 address counts as its /64 network: one
    connection has at least a whole /64 to pick addresses from, so single addresses would
    limit nothing. Guests whose address the server doesn't know share one counter.

    :param ip: The client's address (client_ip), or None.
    :return: The key, e.g. "203.0.113.7" or "2001:db8:1:2::/64".
    """
    if not ip:
        return "unknown"
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip[:64]  # No address (a test client's name); never a key of any length
    if address.version == 6:
        if address.ipv4_mapped:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def count_request(request: Request, counter: str, amount: int = 1) -> None:
    """
    Count a request against one of the guests' limits for the client's address.

    :param request: The HTTP request.
    :param counter: The limit's name (a key of GUEST_LIMITS).
    :param amount: How many to count, e.g. the files of an upload.
    :raises HTTPException: 429 with Retry-After once the address has used the limit up.
    """
    limit = GUEST_LIMITS[counter]
    address = address_key(client_ip(request))
    starts_again = db.count_guest_usage(f"{counter}:{address}", amount, limit, WINDOW)
    if starts_again is None:
        return

    starts_again = starts_again.replace(tzinfo=UTC)
    retry_after = max(1, int((starts_again - datetime.now(UTC)).total_seconds()))
    log.warning(f"Guest limit '{counter}' ({limit} per {GUEST_LIMIT_HOURS:g} h) used up for {address}")
    raise HTTPException(
        status_code=429,
        # The chat reads the time after "after" (ChatStateService.handleRateLimitError)
        detail=f"Too many requests. Please try again after {starts_again.isoformat()}",
        headers={"Retry-After": str(retry_after)}
    )


def count_guest_request(request: Request, user: Optional[dict], counter: str, amount: int = 1) -> None:
    """
    Count a request against one of the guests' limits if a guest sent it.

    For limits that only apply in some cases, e.g. speech that isn't cached yet; endpoints
    that always count use guest_limit() as a dependency.

    :param user: The current user (get_current_user).
    :raises HTTPException: 429 once the guest's address has used the limit up.
    """
    if user and user.get("is_guest"):
        count_request(request, counter, amount)


def guest_limit(counter: str):
    """
    A dependency that counts the request against one of the guests' limits:
    `dependencies=[Depends(guest_limit("titles"))]`.

    Requests without a session are not counted; the endpoint answers them with 401.
    """
    async def dependency(request: Request, current_user: Optional[dict] = Depends(get_current_user_optional)):
        count_guest_request(request, current_user, counter)
    return dependency


# Every answer of a model a guest asks for
rate_limit_guest = guest_limit("answers")


async def guest_write(request: Request, current_user: Optional[dict] = Depends(get_current_user_optional)):
    """
    A dependency for the endpoints that store a conversation or a message: a guest's
    request is counted, and refused if it is larger than guests may store. Without both,
    a visitor could fill the database.

    :raises HTTPException: 413 for a guest's request over GUEST_MAX_REQUEST_KB, 429 once the
        guest's address has used the limit up.
    """
    if not current_user or not current_user.get("is_guest"):
        return
    if len(await request.body()) > GUEST_MAX_REQUEST_KB * 1024:
        raise HTTPException(status_code=413,
                            detail=f"Guests can send up to {GUEST_MAX_REQUEST_KB} KB at once. Log in to send more.")
    count_request(request, "writes")
