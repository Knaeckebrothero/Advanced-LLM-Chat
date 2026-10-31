"""
Export and import of conversation files (docs/conversation_file.md).

An export holds every message of a conversation in the order of their ids (the
server's clock). An import creates a new conversation of the importing user: the
messages keep their times, and the user's default model answers when the
conversation goes on.
"""
import json
from datetime import datetime, timezone

from backend.database import db
from backend.models.conversation_file import (
    CONVERSATION_FILE_TYPE,
    CONVERSATION_FILE_VERSION,
    ConversationFile,
)
from backend.models.message import AgentStep
from backend.services.llm import generate_conversation_id

# The role names of the app; other exports may write the assistant in lower case
ROLE_NAMES = {"user": "user", "assistant": "Assistant", "system": "system"}


class ConversationFileError(ValueError):
    """A conversation file that can't be imported (the message says why)."""


def _utc(value: datetime) -> datetime:
    """The time in UTC; a time without a time zone is taken as UTC (as the database stores them)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    """ISO 8601 in UTC with milliseconds, e.g. 2024-04-28T15:20:16.573Z."""
    return _utc(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _split_text(content: str) -> tuple[str, list]:
    """The text and the attachments of a stored text message ({"content", "attachments"} JSON or plain text)."""
    if content and content.startswith('{'):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return content, []
        if isinstance(parsed, dict) and 'content' in parsed:
            return parsed.get('content') or '', parsed.get('attachments') or []
    return content or '', []


def _step_to_dict(step: AgentStep) -> dict:
    """An agent step as the server stores it: callId only on tool steps."""
    step_dict = step.model_dump()
    if step_dict.get('callId') is None:
        step_dict.pop('callId', None)
    return step_dict


def _file_id(attachment: dict):
    return attachment.get('fileId', attachment.get('id'))


def export_conversation(conversation: dict, messages: list[dict]) -> dict:
    """
    A conversation and its messages as a conversation file.

    :param conversation: The conversations row.
    :param messages: All messages rows of the conversation.
    :return: The conversation file (JSON-serializable).
    """
    exported = []
    for msg in sorted(messages, key=lambda m: m['id']):
        msg_type = msg.get('type') or 'text'
        # The id is the server's clock in milliseconds; rows where it isn't only have the time in seconds
        ms = msg['id'] if msg['id'] // 1000 == msg['time'] else msg['time'] * 1000
        entry = {
            "roleName": msg['roleName'],
            "type": msg_type,
            "time": _iso(datetime.fromtimestamp(ms / 1000, tz=timezone.utc)),
        }
        if msg_type == 'text':
            entry["content"], attachments = _split_text(msg['content'])
            if attachments:
                entry["attachments"] = attachments
        else:
            entry["content"] = msg.get('content') or ''
        if msg.get('rating') is not None:
            entry["rating"] = msg['rating']
        if msg_type == 'agent':
            entry["steps"] = msg.get('agent_steps') or []
            entry["status"] = msg.get('agent_status') or 'complete'
            for key, column in (("error", 'agent_error'), ("modelName", 'model_name'), ("usage", 'usage')):
                if msg.get(column) is not None:
                    entry[key] = msg[column]
        exported.append(entry)

    return {
        "type": CONVERSATION_FILE_TYPE,
        "version": CONVERSATION_FILE_VERSION,
        "exportedAt": _iso(datetime.now(timezone.utc)),
        "conversation": {
            "name": conversation['name'],
            "createdAt": _iso(conversation['createdAt']),
            "updatedAt": _iso(conversation['updatedAt']),
        },
        "messages": exported,
    }


def import_conversation(file: ConversationFile, user_id: int) -> dict:
    """
    Create a new conversation of a user from a conversation file.

    Attachments stay only if the user uploaded the file (the file itself isn't in a
    conversation file, and nobody else may open it). The conversation gets no model
    or agent, so the user's default model answers.

    :param file: The validated conversation file.
    :param user_id: The importing user.
    :return: The created conversations row.
    :raises ConversationFileError: If a message has an unknown role.
    """
    referenced = {_file_id(att) for msg in file.messages for att in msg.attachments or []}
    owned = db.get_owned_file_ids(user_id, {file_id for file_id in referenced if isinstance(file_id, str)})

    rows = []
    for index, msg in enumerate(file.messages):
        role_name = ROLE_NAMES.get(msg.roleName.lower())
        if role_name is None:
            raise ConversationFileError(f"Message {index + 1} has the unknown role {msg.roleName!r} "
                                        f"(expected user, Assistant or system)")
        row = {
            "id": round(_utc(msg.time).timestamp() * 1000),
            "roleName": role_name,
            "type": msg.type,
            "content": msg.content,
            "rating": msg.rating,
        }
        if msg.type == 'text':
            attachments = [att for att in msg.attachments or [] if _file_id(att) in owned]
            if attachments:
                row["content"] = json.dumps({"content": msg.content, "attachments": attachments})
        elif msg.type == 'agent':
            row.update(
                agent_status=msg.status or 'complete',
                agent_steps=[_step_to_dict(step) for step in msg.steps or []],
                agent_error=msg.error,
                model_name=msg.modelName,
                usage=msg.usage.model_dump() if msg.usage else None,
            )
        rows.append(row)

    now = datetime.now(timezone.utc)
    first = file.messages[0].time if file.messages else now
    last = file.messages[-1].time if file.messages else now
    created_at = _utc(file.conversation.createdAt or first)
    updated_at = _utc(file.conversation.updatedAt or last)

    return db.import_conversation(
        conversation_id=generate_conversation_id(),
        user_id=user_id,
        name=file.conversation.name.strip() or "Imported conversation",
        created_at=created_at.replace(tzinfo=None),
        updated_at=max(updated_at, created_at).replace(tzinfo=None),
        message_rows=rows,
    )
