#!/usr/bin/env python3
"""
Convert conversations exported from the old app (2023/24) into conversation files
that the current app imports (Settings > Import conversations, docs/conversation_file.md).

An old export holds two JSON values one after the other: the conversation
({"id", "summary", "participants", ...}) and the list of its messages
({"id", "conversationID", "content", "role", "time"}). Only the messages are
converted; the summary, the participants and the variables are left out. The old
files have no conversation name, so the name is the start of the first user
message, as the app names a new conversation (or --name).

Usage:
    python scripts/convert_legacy_conversations.py OLD.json [OLD2.json ...] [-o DIR] [--name NAME]

Each OLD.json becomes OLD.converted.json, next to it or in DIR. Only the standard
library is used, so it runs without the app's environment.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FILE_TYPE = "advanced-llm-chat-conversation"
FILE_VERSION = 1
ROLE_NAMES = {"user": "user", "assistant": "Assistant", "system": "system"}


def read_json_values(text: str) -> list:
    """All JSON values of a text, also several one after the other (as in the old exports)."""
    decoder = json.JSONDecoder()
    values, index = [], 0
    while True:
        while index < len(text) and text[index].isspace():
            index += 1
        if index == len(text):
            return values
        value, index = decoder.raw_decode(text, index)
        values.append(value)


def iso_time(message: dict) -> str | None:
    """The message's time as ISO 8601: its time field, or else its id (Unix seconds)."""
    value = message.get("time")
    if isinstance(value, str) and value:
        datetime.fromisoformat(value.replace("Z", "+00:00"))  # Raises if it isn't a time
        return value
    if isinstance(message.get("id"), (int, float)):
        return datetime.fromtimestamp(message["id"], tz=timezone.utc).isoformat(timespec="milliseconds")
    return None


def title_from(content: str) -> str:
    """The app's name for a new conversation: the first message, cut at 50 characters."""
    content = " ".join(content.split())
    return content[:47].strip() + "..." if len(content) > 50 else content


def convert(path: Path, name: str | None = None) -> tuple[dict, list[str]]:
    """The conversation file for an old export, and notes about what was left out."""
    values = read_json_values(path.read_text(encoding="utf-8"))
    conversation = next((v for v in values if isinstance(v, dict)), {})
    old_messages = next((v for v in values if isinstance(v, list)), None)
    if old_messages is None:
        raise ValueError("no list of messages found")

    notes, messages = [], []
    for number, old in enumerate(old_messages, start=1):
        role = ROLE_NAMES.get(str(old.get("role", "")).lower()) if isinstance(old, dict) else None
        if role is None:
            notes.append(f"message {number} skipped: unknown role {old.get('role') if isinstance(old, dict) else old!r}")
            continue
        content = old.get("content")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False) if content is not None else ""
        if not content.strip():
            notes.append(f"message {number} skipped: empty")
            continue
        time = iso_time(old)
        if time is None:
            notes.append(f"message {number} skipped: no time")
            continue
        messages.append({"roleName": role, "type": "text", "time": time, "content": content})

    if not messages:
        raise ValueError("no messages to convert")
    if conversation.get("summary"):
        notes.append("the summary is left out (all messages are kept)")

    first_user = next((m["content"] for m in messages if m["roleName"] == "user"), None)
    file = {
        "type": FILE_TYPE,
        "version": FILE_VERSION,
        "exportedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "conversation": {
            "name": name or (title_from(first_user) if first_user else path.stem),
            "createdAt": messages[0]["time"],
            "updatedAt": messages[-1]["time"],
        },
        "messages": messages,
    }
    return file, notes


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert conversations of the old app (2023/24) for the import.")
    parser.add_argument("files", nargs="+", type=Path, help="exported conversations of the old app")
    parser.add_argument("-o", "--output-dir", type=Path, help="where to write the converted files (default: next to each file)")
    parser.add_argument("--name", help="name of the conversation (only with one file)")
    args = parser.parse_args()
    if args.name and len(args.files) > 1:
        parser.error("--name works with one file only")
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    failed = 0
    for path in args.files:
        try:
            file, notes = convert(path, args.name)
        except (OSError, ValueError) as e:
            print(f"{path}: not converted, {e}", file=sys.stderr)
            failed += 1
            continue
        target = (args.output_dir or path.parent) / f"{path.stem}.converted.json"
        target.write_text(json.dumps(file, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{path} -> {target}: \"{file['conversation']['name']}\", {len(file['messages'])} messages")
        for note in notes:
            print(f"  note: {note}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
