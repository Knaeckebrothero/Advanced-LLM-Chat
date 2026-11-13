"""
Export of a user's knowledge base as a zip that opens as an Obsidian vault (docs/knowledge_base.md).

One file per note, named after its slug, so the [[slug]] links resolve in Obsidian as they are:
the link view, the graph and the backlinks. The active notes are at the top of the vault folder,
the archived ones in archive/ (Obsidian finds a link's file by its name in any folder). Each file
starts with YAML properties (title, the title as an alias for Obsidian's link suggestions,
description, tags, created, updated), then the title as a heading and the content. Earlier
versions are not exported. Obsidian reads times without a zone as local time, so they are written
in the user's time zone (the browser sends it; UTC without one), and so are the files' dates.

Links whose target isn't written as a slug are rewritten to one, keeping the text they show:
[[Project Apollo]] becomes [[project-apollo|Project Apollo]] and [text](Project%20Apollo.md)
becomes [text](project-apollo.md), because Obsidian goes by file name. Code stays as it is. Obsidian tags may only
contain letters, digits, _, - and /, and not only digits, so other characters become dashes and
a tag of digits gets the prefix "tag-" (2026 becomes tag-2026).
"""
import io
import json
import re
import zipfile
from datetime import datetime, timezone, tzinfo
from typing import Optional
from urllib.parse import unquote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.services import knowledge_base as kb

VAULT_FOLDER = "knowledge-base"
ARCHIVE_FOLDER = "archive"

# [[target]], [[target#heading]], [[target|alias]], [[target#heading|alias]]
_WIKILINK_RE = re.compile(r"\[\[([^\[\]|#]+)(#[^\[\]|]*)?(\|[^\[\]]*)?\]\]")
# The target of a Markdown link (as in knowledge_base._MD_LINK_RE, with the target's span as group 1)
_MD_LINK_RE = re.compile(r"\[[^\[\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")


def time_zone(name: Optional[str]) -> Optional[tzinfo]:
    """The time zone with this IANA name (e.g. Europe/Berlin), or None for an unknown one (UTC)."""
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def local_time(value: Optional[datetime], zone: Optional[tzinfo]) -> Optional[datetime]:
    """A time from the database (naive, UTC) as a naive time in the zone (UTC without one)."""
    if value is None or zone is None:
        return value
    return value.replace(tzinfo=timezone.utc).astimezone(zone).replace(tzinfo=None)


def file_name(zone: Optional[tzinfo] = None, agent: Optional[str] = None) -> str:
    """The name of the zip: knowledge-base-<today>.zip, knowledge-base-<agent>-<today>.zip for an agent's own."""
    name = f"{VAULT_FOLDER}-{kb.slugify(agent) or 'agent'}" if agent is not None else VAULT_FOLDER
    return f"{name}-{datetime.now(zone or timezone.utc).date().isoformat()}.zip"


def obsidian_tag(tag: str) -> Optional[str]:
    """A tag as Obsidian accepts it, or None if nothing is left of it."""
    tag = re.sub(r"[^\w/-]+", "-", tag)
    tag = re.sub(r"-{2,}", "-", tag).strip("-/")
    if not tag:
        return None
    return f"tag-{tag}" if tag.isdigit() else tag


def obsidian_links(content: str) -> str:
    """The content with every link to another note pointing to its slug (see the module docstring)."""
    def wikilink(match: re.Match) -> str:
        target, heading, alias = match.group(1), match.group(2) or "", match.group(3)
        slug = kb.slugify(target)
        if not slug or slug == target.strip():
            return match.group(0)
        return f"[[{slug}{heading}{alias or '|' + target.strip()}]]"

    def markdown_link(match: re.Match) -> str:
        target = match.group(1)
        path, hash_, anchor = target.partition("#")
        name = unquote(path).rstrip("/").rsplit("/", 1)[-1]
        if ":" in target or not name.lower().endswith(".md"):
            return match.group(0)  # Web links, anchors, images and other files stay as they are
        slug = kb.slugify(name[:-3])
        if not slug:
            return match.group(0)
        start, end = match.start(1) - match.start(), match.end(1) - match.start()
        whole = match.group(0)
        return whole[:start] + f"{slug}.md{hash_}{anchor}" + whole[end:]

    # Links in code are text: only the parts between code are rewritten
    parts = kb.CODE_RE.split(content)
    return "".join(part if index % 2 else _MD_LINK_RE.sub(markdown_link, _WIKILINK_RE.sub(wikilink, part))
                   for index, part in enumerate(parts))


def _yaml_text(value: str) -> str:
    # A JSON string is a valid double-quoted YAML scalar, and quoting keeps "yes" or "null" text
    return json.dumps(value, ensure_ascii=False)


def _yaml_time(value: Optional[datetime]) -> Optional[str]:
    return value.replace(microsecond=0).isoformat() if value else None


def note_markdown(note: dict, zone: Optional[tzinfo] = None) -> str:
    """A note as an Obsidian Markdown file: YAML properties, the title as a heading, the content."""
    lines = ["---", f"title: {_yaml_text(note['title'])}", "aliases:", f"  - {_yaml_text(note['title'])}"]
    if note.get("description"):
        lines.append(f"description: {_yaml_text(note['description'])}")
    tags = [tag for tag in (obsidian_tag(tag) for tag in note.get("tags") or ()) if tag]
    if tags:
        lines.append("tags:")
        lines += [f"  - {_yaml_text(tag)}" for tag in dict.fromkeys(tags)]
    for key in ("created", "updated"):
        value = _yaml_time(local_time(note.get(f"{key}_at"), zone))
        if value:
            lines.append(f"{key}: {value}")
    if note.get("hidden"):
        lines.append("hidden: true")
    lines += ["---", "", f"# {note['title']}", "", obsidian_links(note["content"]).strip(), ""]
    return "\n".join(lines)


def note_path(note: dict) -> str:
    """Where a note goes in the zip: knowledge-base/<slug>.md, archived ones in knowledge-base/archive/."""
    folder = f"{VAULT_FOLDER}/{ARCHIVE_FOLDER}" if note["status"] == "archived" else VAULT_FOLDER
    return f"{folder}/{note['slug']}.md"


def export_vault(user_id: int, zone: Optional[tzinfo] = None, vault: int = 0,
                 family_mode: bool = False) -> tuple[bytes, int]:
    """
    A knowledge base of the user (with its memory as memory.md) as a zip, with times in the zone
    (UTC without one); with family_mode without the hidden notes and lines.

    Returns:
        (the zip, the number of notes in it)
    """
    notes = kb.all_notes(user_id, vault, family_mode=family_mode)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        # The vault folder itself, so even an empty knowledge base unpacks to a folder Obsidian can open
        archive.mkdir(VAULT_FOLDER)
        for note in notes:
            changed = local_time(note.get("updated_at") or note.get("created_at"), zone) or datetime.now()
            info = zipfile.ZipInfo(note_path(note), date_time=max(changed, datetime(1980, 1, 1)).timetuple()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, note_markdown(note, zone).encode("utf-8"))
    return buffer.getvalue(), len(notes)
