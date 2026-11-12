"""
Questions of MCP servers to the user: elicitation (docs/mcp.md, "Questions from servers").

While one of its tools runs, a server may ask the user something: to confirm a paid run, for
input the tool needs (form mode: a flat form, described by a small JSON schema), or to open a
page that must not pass through the chat (URL mode: a sign-in, a payment). The client says it
can answer (the elicitation capability); a server must not ask a client that doesn't.

The question becomes a step of the answer that made the tool call ("observation", id
"elicitation-<id>", metadata.elicitation with status "pending"). The chat shows it with its
fields and buttons and sends the user's answer to POST /api/mcp/elicitations/{id}, which wakes
the waiting call; the step is then replaced by one with the outcome. Without an answer within
MCP_ELICITATION_TIMEOUT the question is cancelled, and so is one asked where no chat is
watching (no answer stream).

A plain confirmation (a form whose required fields all have defaults, like Civitai's "Spend 4
Buzz to run imageGen?" with no fields) can be accepted without asking: the user ticks "for the
rest of this chat" or "always for this server" when accepting one (stored in mcp_auto_accept;
the MCP servers page turns "always" off again). Such a question still becomes a step, already
accepted (metadata.elicitation.auto), so every spend shows in the chat. Forms that need input
and pages to open always ask.

Pending questions live in this process's memory: the answer has to reach the backend process
that runs the answer (the chart runs one backend replica).
"""
import asyncio
import logging
import math
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

from mcp_types import ElicitRequestURLParams, ElicitResult

from backend.config import MCP_ELICITATION_TIMEOUT
from backend.llm.tools import StepSink
from backend.models.message import AgentStep
from backend.services.mcp import store

log = logging.getLogger(__name__)

STEP_PREFIX = "elicitation-"
# The step's title (the frontend translates it by this string); ": <server name>" follows
STEP_TITLE = "Question"


@dataclass
class Asker:
    """Who answers the questions of one tool call: its user, through the answer's stream (sink)."""
    user_id: int
    server_name: str
    sink: Optional[StepSink]
    server_id: Optional[int] = None
    conversation_id: Optional[str] = None


# The asker of the running tool call. The SDK asks the client's callback within the call's
# context (also for servers of older protocol versions, which send the question as a request of
# their own); a connection's callback falls back to its newest running call (Connection.askers).
_current: ContextVar[Optional[Asker]] = ContextVar("mcp_asker", default=None)


@contextmanager
def asking(asker: Asker, askers: list):
    """Route the questions of a tool call to its asker while it runs (askers: the connection's)."""
    token = _current.set(asker)
    askers.append(asker)
    try:
        yield
    finally:
        askers.remove(asker)
        _current.reset(token)


@dataclass
class _Pending:
    user_id: int
    url_mode: bool
    schema: dict
    future: asyncio.Future
    confirmation: bool = False  # May be accepted without asking from now on (confirmation_defaults)
    server_id: Optional[int] = None
    conversation_id: Optional[str] = None


_pending: dict[str, _Pending] = {}


class AnswerError(Exception):
    """An answer the question doesn't take (400), or a question that isn't open (404)."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


# =========================================================================
# Asking
# =========================================================================

async def handle(askers: list, params) -> ElicitResult:
    """
    The client's elicitation callback (pool.Connection): ask the user of the running tool call.

    Args:
        askers: The connection's running tool calls (the fallback when the context has none).
        params: ElicitRequestFormParams or ElicitRequestURLParams.
    """
    asker = _current.get() or (askers[-1] if askers else None)
    if asker is None or asker.sink is None:
        log.info("An MCP server asked a question outside of an answer; cancelled")
        return ElicitResult(action="cancel")
    try:
        return await ask(asker, params)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.error(f"Question of {asker.server_name} failed: {e}", exc_info=True)
        return ElicitResult(action="cancel")


def confirmation_defaults(schema: dict) -> Optional[dict]:
    """
    The answer to a plain confirmation: a form whose required fields all have defaults (or that has
    no fields) gets their defaults. None for a form that needs the user's input.
    """
    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        return None
    for name in schema.get("required") or []:
        if not isinstance(properties.get(name), dict) or "default" not in properties[name]:
            return None
    return {name: prop["default"] for name, prop in properties.items() if isinstance(prop, dict) and "default" in prop}


async def ask(asker: Asker, params) -> ElicitResult:
    """Show the question in the chat and wait for the answer (or MCP_ELICITATION_TIMEOUT)."""
    url_mode = isinstance(params, ElicitRequestURLParams) or getattr(params, "mode", None) == "url"
    url = getattr(params, "url", None) if url_mode else None
    if url_mode and urlparse(url or "").scheme not in ("https", "http"):
        log.warning(f"{asker.server_name} asked to open a URL that isn't http(s); declined")
        return ElicitResult(action="decline")
    schema = {} if url_mode else dict(getattr(params, "requested_schema", None) or {})
    defaults = None if url_mode or asker.server_id is None else confirmation_defaults(schema)

    question_id = uuid.uuid4().hex
    started = time.time()

    def step(status: str, answer: Optional[dict] = None, **extra) -> AgentStep:
        details: dict[str, Any] = {"id": question_id, "server": asker.server_name,
                                   "mode": "url" if url_mode else "form", "status": status}
        if url_mode:
            details["url"] = url
        else:
            details["schema"] = schema
        if answer:
            details["answer"] = answer
        details.update(extra)
        return AgentStep(
            id=STEP_PREFIX + question_id,
            type="observation",
            title=f"{STEP_TITLE}: {asker.server_name}",
            content=params.message,
            timestamp=int(started * 1000),
            duration=None if status == "pending" else int((time.time() - started) * 1000),
            metadata={"elicitation": details},
        )

    # A confirmation the user accepts without being asked: shown as accepted right away
    if defaults is not None:
        scope = await asyncio.to_thread(store.auto_accept_scope, asker.server_id, asker.user_id, asker.conversation_id)
        if scope:
            log.info(f"{asker.server_name} asks user {asker.user_id}, accepted automatically ({scope}): "
                     f"{params.message[:200]}")
            asker.sink(step("accept", defaults, auto=scope))
            return ElicitResult(action="accept", content=defaults)

    future = asyncio.get_running_loop().create_future()
    _pending[question_id] = _Pending(asker.user_id, url_mode, schema, future, confirmation=defaults is not None,
                                     server_id=asker.server_id, conversation_id=asker.conversation_id)
    log.info(f"{asker.server_name} asks user {asker.user_id} ({'url' if url_mode else 'form'}): {params.message[:200]}")
    # confirmation: the chat offers to accept such questions without asking from now on
    asker.sink(step("pending", confirmation=defaults is not None,
                    **({"conversation": True} if asker.conversation_id else {})))
    action, content, remember = "cancel", None, None
    try:
        action, content, remember = await asyncio.wait_for(future, MCP_ELICITATION_TIMEOUT)
        status = action
    except asyncio.TimeoutError:
        status = "timeout"
    finally:
        _pending.pop(question_id, None)
    log.info(f"Question of {asker.server_name} to user {asker.user_id}: {status}"
             + (f" (from now on automatically: {remember})" if remember else ""))
    asker.sink(step(status, content, **({"remember": remember} if remember else {})))
    if action == "accept" and not url_mode:
        return ElicitResult(action="accept", content=content or {})
    return ElicitResult(action=action)


# =========================================================================
# Answering
# =========================================================================

def answer(question_id: str, user_id: int, action: str, content: Optional[dict] = None,
           remember: Optional[str] = None) -> None:
    """
    The user's answer to an open question.

    Args:
        action: "accept" (submitted, confirmed, or agreed to open the URL), "decline" or "cancel".
        content: The form's values (form mode with accept).
        remember: With accept of a plain confirmation: accept the server's confirmations without
            asking from now on, "conversation" (in this conversation) or "always".

    Raises:
        AnswerError: 404 if the question isn't open (answered, timed out, another user's),
            400 if the values don't fit the form, or remember for a question that isn't a confirmation.
    """
    pending = _pending.get(question_id)
    if pending is None or pending.user_id != user_id or pending.future.done():
        raise AnswerError("The question is no longer open", 404)
    if action not in ("accept", "decline", "cancel"):
        raise AnswerError(f"Unknown action: {action}")
    values = check_content(pending.schema, content or {}) if action == "accept" and not pending.url_mode else None
    if action != "accept":
        remember = None
    if remember is not None:
        if remember not in ("conversation", "always"):
            raise AnswerError(f"Unknown scope: {remember}")
        if not pending.confirmation or pending.server_id is None:
            raise AnswerError("Only plain confirmations can be accepted automatically")
        if remember == "conversation" and pending.conversation_id is None:
            raise AnswerError("This question isn't part of a conversation")
        store.set_auto_accept(pending.server_id, user_id, True,
                              pending.conversation_id if remember == "conversation" else None)
    pending.future.set_result((action, values, remember))


def check_content(schema: dict, content: dict) -> dict:
    """
    The form's values, checked against the question's schema (flat: strings, numbers, booleans,
    enums, arrays of enum strings) and converted where the browser sends text. The server checks
    them again.
    """
    if not isinstance(content, dict):
        raise AnswerError("The answer must be an object")
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    values: dict = {}
    for name, prop in properties.items():
        prop = prop if isinstance(prop, dict) else {}
        label = prop.get("title") or name
        value = content.get(name)
        if value is None or value == "" or value == []:
            if name in required:
                raise AnswerError(f"{label} is required")
            continue
        values[name] = _check_value(label, prop, value)
    return values


def _choices(prop: dict) -> Optional[list]:
    """The allowed values of an enum field (enum, or oneOf/anyOf with const)."""
    if isinstance(prop.get("enum"), list):
        return prop["enum"]
    options = prop.get("oneOf") or prop.get("anyOf")
    if isinstance(options, list):
        consts = [option.get("const") for option in options if isinstance(option, dict) and "const" in option]
        return consts or None
    return None


def _check_value(label: str, prop: dict, value: Any) -> Any:
    kind = prop.get("type")
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if value in ("true", "false"):
            return value == "true"
        raise AnswerError(f"{label} must be yes or no")
    if kind in ("integer", "number"):
        try:
            number = float(value) if not isinstance(value, bool) else math.nan
        except (TypeError, ValueError):
            number = math.nan
        if not math.isfinite(number) or (kind == "integer" and not number.is_integer()):
            raise AnswerError(f"{label} must be {'a whole number' if kind == 'integer' else 'a number'}")
        if prop.get("minimum") is not None and number < prop["minimum"]:
            raise AnswerError(f"{label} must be at least {prop['minimum']}")
        if prop.get("maximum") is not None and number > prop["maximum"]:
            raise AnswerError(f"{label} must be at most {prop['maximum']}")
        return int(number) if kind == "integer" else number
    if kind == "array":
        items = prop.get("items") if isinstance(prop.get("items"), dict) else {}
        choices = _choices(items)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise AnswerError(f"{label} must be a list of choices")
        if choices is not None and any(item not in choices for item in value):
            raise AnswerError(f"{label} has a choice that isn't offered")
        if prop.get("minItems") is not None and len(value) < prop["minItems"]:
            raise AnswerError(f"{label} needs at least {prop['minItems']} choices")
        if prop.get("maxItems") is not None and len(value) > prop["maxItems"]:
            raise AnswerError(f"{label} takes at most {prop['maxItems']} choices")
        return value
    # string (also without a type)
    if not isinstance(value, str):
        raise AnswerError(f"{label} must be text")
    choices = _choices(prop)
    if choices is not None and value not in choices:
        raise AnswerError(f"{label} must be one of the choices")
    if prop.get("minLength") is not None and len(value) < prop["minLength"]:
        raise AnswerError(f"{label} must be at least {prop['minLength']} characters")
    if prop.get("maxLength") is not None and len(value) > prop["maxLength"]:
        raise AnswerError(f"{label} must be at most {prop['maxLength']} characters")
    return value
