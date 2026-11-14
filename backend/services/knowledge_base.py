"""
The knowledge base: each user's Markdown notes, which the agent keeps across all of the user's
conversations with the kb_* tools (backend/services/tools/kb_tools.py). See docs/knowledge_base.md.

A user has one shared knowledge base (vault 0), which every agent with the knowledge base uses, and
one of its own for each agent with own_memory (vault: the agent's personas.id). Every function works
on one of them; slugs, links and searches never cross vaults.

The note "memory" of a vault is the agent's memory: short lines, each with the date it was written,
that go into the system prompt of every answer (the details are in the notes they point to). The
agent changes it line by line with memory_add(), memory_replace() and memory_remove(), which keep
it below MEMORY_MAX_LINES and MEMORY_MAX_CHARS; kb_write, kb_update and kb_archive don't touch it,
and lists and searches leave it out.

Postgres holds the only copy (kb_notes), so a note is readable right after it is written. A note's
slug is its stable id: it is made from the first title and stays when the title changes, and a
title whose slug exists already is refused rather than stored as a second note. Links to other
notes are [[slug]], [[Title]] (also with |alias or #heading) or Markdown links to slug.md; their
slugs go to kb_links, which gives the backlinks. Every write stores the new version in
kb_note_revisions, with who wrote it and in which conversation. Archiving hides a note from
lists and searches; an update restores it.

A note can keep files, e.g. an image (kb_files, "Files" below): a stored file of a conversation
(uploaded_files) gets a name of its own in the vault, made from the note's slug, and the note's text
places it with ![[name]]. Kept files stay when their conversation is deleted and go with their note.
Any note of the vault, and any answer of an agent that uses it, shows one by its name.

Family mode: with family_mode, the reads leave out hidden notes and the lines tagged #hidden, and a
save puts the hidden lines back (hidden_content.restore_hidden()). A writer from a hidden conversation
(Writer.from_hidden) hides a new note and tags the lines it adds. A note's mark records who set it
(hidden_by): what the user decided on the page, agents don't change.

Search combines the words of the query (full-text search with the 'simple' configuration: the
same for German and English, no stemming, words of four letters or more also match as prefixes),
exact text (a case-insensitive substring) and tags. Embeddings are planned.

Adapted from the knowledge base of Superhuman Remote Worker (its kb_* tools, slugs and link
parsing), without its git repository and index.
"""
import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, Optional
from urllib.parse import unquote

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from backend.database import db
from backend.database.tables import conversations, kb_files, kb_links, kb_note_revisions, kb_notes, personas
from backend.services import file_store, file_utils, hidden_content

log = logging.getLogger(__name__)

MAX_TITLE_CHARS = 200
MAX_DESCRIPTION_CHARS = 300
MAX_CONTENT_CHARS = 50_000
MAX_TAGS = 20
MAX_TAG_CHARS = 50
MAX_SLUG_CHARS = 80
# Notes longer than this get a hint to split them (agent notes are usually a few KB)
LONG_NOTE_CHARS = 15_000

# Files one note keeps
MAX_NOTE_FILES = 20
# One at a time names the files a user's notes keep (pg_advisory_xact_lock with the user's id)
_FILES_LOCK = 0x6B62

# The memory: the note with this slug in each vault, part of every answer's system prompt
MEMORY_SLUG = "memory"
MEMORY_TITLE = "Memory"
MEMORY_DESCRIPTION = "What the agent keeps in mind in every conversation, with pointers to the notes"
MEMORY_MAX_LINES = 200         # Lines of text (headings don't count)
MEMORY_MAX_CHARS = 20_000      # About 5,000 tokens of every answer's prompt
MEMORY_LINE_CHARS = 500
MEMORY_NEAR_SHARE = 0.9        # From here on, every change reminds the agent to tidy the memory up
MEMORY_SECTION_CHARS = 60
# The date memory_add() and memory_replace() put at the end of a line: "- Likes tea (2026-11-04)"
_MEMORY_DATE_RE = re.compile(r"\s*\(\d{4}-\d{2}-\d{2}\)\s*$")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")

# Query words: letters and digits (no underscores, which the full-text parser splits on)
_WORD_RE = re.compile(r"[^\W_]+")
# Query words from this length on also match as prefixes ("katze" finds "katzen")
_PREFIX_MIN_CHARS = 4
_MAX_QUERY_WORDS = 16
# [[target]], [[target|alias]], [[target#heading]]
_WIKILINK_RE = re.compile(r"\[\[([^\[\]|#]+)(?:#[^\[\]|]*)?(?:\|[^\[\]]*)?\]\]")
# [text](target) without a scheme: [text](other-note.md), [text](folder/Other%20Note.md#part)
_MD_LINK_RE = re.compile(r"\[[^\[\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
# Code, where [[...]] is text and not a link: fenced blocks (also unclosed at the end) and inline code.
# One group, so CODE_RE.split() puts the code at the odd indices.
CODE_RE = re.compile(r"(```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)|`[^`\n]*`)")
# A file placed in a text: ![[name]], ![[name|300]] or ![what it shows](name "title"), as the chat
# reads them (src/app/chat-ui/chat-ui-message/answer-parts.ts). Groups: the name and what follows it
# of the first form, the text and the address of the second
_EMBED_RE = re.compile(r"!\[\[([^\[\]|\n]+)(\|[^\[\]\n]*)?\]\]"
                       r"|!\[((?:[^\[\]\\\n]|\\.|\[[^\[\]\n]*\])*)\]\(((?:[^()\n]|\([^()\n]*\))*)\)")
_WEB_ADDRESS_RE = re.compile(r"(?:(?:https?:)?//|data:|blob:)", re.IGNORECASE)
_TRANSLITERATION = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "æ": "ae", "ø": "o", "œ": "oe"})

_NOTE_COLUMNS = (kb_notes.c.id, kb_notes.c.slug, kb_notes.c.title, kb_notes.c.description, kb_notes.c.tags,
                 kb_notes.c.content, kb_notes.c.status, kb_notes.c.hidden, kb_notes.c.hidden_by, kb_notes.c.created_at,
                 kb_notes.c.updated_at)


STATUSES = ("active", "archived")


class KBError(ValueError):
    """A request the knowledge base refuses; the message is meant for the model."""


class KBNotFound(KBError):
    """There is no such note, or no such version of it."""


class KBExists(KBError):
    """A note with the slug exists already (`note`: that note)."""

    def __init__(self, message: str, note: dict):
        super().__init__(message)
        self.note = note


class KBConflict(KBError):
    """The note changed since the version an edit started from (`version`: its version now)."""

    def __init__(self, message: str, version: int):
        super().__init__(message)
        self.version = version


@dataclass(frozen=True)
class Writer:
    """Who changes notes, for the revisions: the user and vault whose knowledge base it is, and where."""

    user_id: int
    author: str = "agent"                   # 'agent' | 'review' (memory review) | 'dream' (consolidation) | 'user' (the page)
    conversation_id: Optional[str] = None
    persona_id: Optional[int] = None
    vault: int = 0                          # 0: the user's shared knowledge base, else an agent's own
    from_hidden: bool = False               # Writes from a hidden conversation: hide what it adds
    # (the author 'user' is the user's own decision on a mark; the others are agents)
    family_mode: bool = False                 # The request is in family mode: it sees none and keeps it on a save


# =========================================================================
# Slugs, tags and links
# =========================================================================

def slugify(value: str) -> str:
    """
    A slug for a title or link target: lowercase ASCII letters, digits and dashes.

    German umlauts are transliterated, other accents dropped: "Größe & Gewicht" -> "groesse-gewicht".
    Returns "" if nothing is left (e.g. a title in another script).
    """
    value = unicodedata.normalize("NFKD", value.lower().translate(_TRANSLITERATION))
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-z0-9\s_-]", " ", value)
    value = re.sub(r"[\s_-]+", "-", value).strip("-")
    return value[:MAX_SLUG_CHARS].rstrip("-")


def note_slug(title: str) -> str:
    """The slug of a new note: slugify(title), or note-<hash> for a title without letters it can keep."""
    return slugify(title) or "note-" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:8]


def normalize_tags(tags: Optional[Iterable[str]]) -> list[str]:
    """Lowercase tags without '#', spaces as dashes, without duplicates, in their order."""
    result = []
    for tag in tags or ():
        tag = re.sub(r"\s+", "-", str(tag).strip().lstrip("#").strip().lower())
        if tag and tag not in result:
            if len(tag) > MAX_TAG_CHARS:
                raise KBError(f"Tag '{tag[:20]}...' is longer than {MAX_TAG_CHARS} characters")
            result.append(tag)
    if len(result) > MAX_TAGS:
        raise KBError(f"A note can have at most {MAX_TAGS} tags, got {len(result)}")
    return result


# What a stored file's name ends with (a note's doesn't: .md is a note)
_FILE_ENDINGS = (set(file_store.TYPES_BY_EXTENSION) | set(file_store.EXTENSIONS.values())) - {".md"}


def names_file(target: str) -> bool:
    """A link's target names a file, not a note: it ends like a stored file (red-fox.png, report.pdf)."""
    name = target.strip().lower()
    return "." in name and "." + name.rsplit(".", 1)[1] in _FILE_ENDINGS


def link_targets(content: str) -> list[str]:
    """
    The slugs a note's content links to, in order: [[target]] links and Markdown links without a
    scheme (to other notes, e.g. [text](other-note.md)). Web links, anchors, code and files (the
    images a note places, ![[red-fox.png]]) are skipped.
    """
    content = CODE_RE.sub(" ", content)
    targets = [match.group(1) for match in _WIKILINK_RE.finditer(content) if not names_file(match.group(1))]
    for match in _MD_LINK_RE.finditer(content):
        target = match.group(1)
        if ":" in target or target.startswith("#") or names_file(target.split("#", 1)[0]):
            continue  # https://..., mailto:..., #heading, a file
        target = unquote(target.split("#", 1)[0]).rstrip("/").rsplit("/", 1)[-1]
        if target.lower().endswith(".md"):
            target = target[:-3]
        targets.append(target)
    slugs = []
    for target in targets:
        slug = slugify(target)
        if slug and slug not in slugs:
            slugs.append(slug)
    return slugs


def _escape_like(value: str) -> str:
    """Escape the LIKE wildcards of a literal text (backslash is the default escape character)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _query_words(query: str) -> list[str]:
    """The words of a search query, lowercased, without duplicates and single characters."""
    words = []
    for word in _WORD_RE.findall(query.lower()):
        if len(word) > 1 and word not in words:
            words.append(word)
    return words[:_MAX_QUERY_WORDS]


def _tsquery(words: list[str]) -> str:
    """A to_tsquery() text that matches any of the words, longer ones also as prefixes."""
    return " | ".join(f"'{word}':*" if len(word) >= _PREFIX_MIN_CHARS else f"'{word}'" for word in words)


# =========================================================================
# Checks of what the model sends
# =========================================================================

def _clean_title(title: Optional[str]) -> str:
    title = " ".join((title or "").split())
    if not title:
        raise KBError("The title must not be empty")
    if len(title) > MAX_TITLE_CHARS:
        raise KBError(f"The title is longer than {MAX_TITLE_CHARS} characters")
    return title


def _clean_description(description: Optional[str]) -> Optional[str]:
    description = " ".join((description or "").split())
    if len(description) > MAX_DESCRIPTION_CHARS:
        raise KBError(f"The description is longer than {MAX_DESCRIPTION_CHARS} characters; keep it to one sentence")
    return description or None


def _clean_content(content: Optional[str], title: str) -> str:
    """The content without a first heading that repeats the title (kb_read shows the title itself)."""
    content = (content or "").strip()
    first, _, rest = content.partition("\n")
    if re.fullmatch(r"#\s+" + re.escape(title) + r"\s*#*", first.strip(), re.IGNORECASE):
        content = rest.strip()
    if not content:
        raise KBError("The content must not be empty")
    return _check_length(content)


def _check_length(content: str) -> str:
    if len(content) > MAX_CONTENT_CHARS:
        raise KBError(f"The note is longer than {MAX_CONTENT_CHARS} characters ({len(content)}); split it into "
                      f"several notes that link to each other")
    return content


# =========================================================================
# Reading
# =========================================================================

def _find_note(conn: Connection, user_id: int, ref: str, lock: bool = False, vault: int = 0,
               family_mode: bool = False) -> Optional[dict]:
    """
    A note of a vault by its slug, by the slug its title would get, or by its exact title
    (case-insensitive). With family_mode, a note hidden is not found.
    """
    ref = (ref or "").strip()
    if ref.startswith("[[") and ref.endswith("]]"):
        ref = ref[2:-2].split("|", 1)[0].strip()
    if not ref:
        return None
    slug = slugify(ref)
    query = (
        select(*_NOTE_COLUMNS)
        .where(kb_notes.c.user_id == user_id, kb_notes.c.vault == vault)
        .where((kb_notes.c.slug.in_([ref, slug])) | (func.lower(kb_notes.c.title) == ref.lower()))
        .order_by((kb_notes.c.slug == ref).desc(), (kb_notes.c.slug == slug).desc(), kb_notes.c.id)
        .limit(1)
    )
    if lock:
        query = query.with_for_update()
    row = conn.execute(query).first()
    if row is None or (family_mode and row.hidden):
        return None
    return dict(row._mapping)


def _not_found(ref: str) -> KBNotFound:
    return KBNotFound(f"There is no note '{ref}'. Find the slug with kb_search or kb_list, or create the note with kb_write")


def _check_status(status: str) -> str:
    if status not in STATUSES:
        raise KBError(f"Unknown status '{status}', expected one of {', '.join(STATUSES)}")
    return status


def _version(conn: Connection, note_id: int) -> int:
    """A note's version: the id of its newest revision (every write adds one)."""
    return conn.execute(select(func.max(kb_note_revisions.c.id))
                        .where(kb_note_revisions.c.note_id == note_id)).scalar_one() or 0


def get_note(user_id: int, ref: str, vault: int = 0, family_mode: bool = False) -> dict:
    """
    A note with its version and links: "links" (the notes it links to: slug, title or None if there
    is no such note, status) and "backlinks" (the active notes that link to it: slug, title). Also
    its files: "files" (the ones it keeps, see _kept_files()) and "placed_files" (files of other notes
    that its text places). With family_mode, a hidden note isn't found, and the note comes without its
    hidden lines, links to hidden notes, backlinks from them and hidden files.

    Raises:
        KBError: There is no such note.
    """
    with db.connection() as conn:
        note = _find_note(conn, user_id, ref, vault=vault, family_mode=family_mode)
        if note is None:
            raise _not_found(ref)
        note["version"] = _version(conn, note["id"])
        if family_mode:
            note["content"] = hidden_content.visible(note["content"])
        targets = link_targets(note["content"])
        existing = {}
        if targets:
            rows = conn.execute(
                select(kb_notes.c.slug, kb_notes.c.title, kb_notes.c.status, kb_notes.c.hidden)
                .where(kb_notes.c.user_id == user_id, kb_notes.c.vault == vault, kb_notes.c.slug.in_(targets))
            )
            existing = {row.slug: row for row in rows}
        note["links"] = [
            {"slug": slug,
             "title": existing[slug].title if slug in existing else None,
             "status": existing[slug].status if slug in existing else None}
            for slug in targets
            if slug != note["slug"] and not (family_mode and slug in existing and existing[slug].hidden)
        ]
        backlinks = (select(kb_notes.c.slug, kb_notes.c.title)
                     .select_from(kb_links.join(kb_notes, kb_links.c.note_id == kb_notes.c.id))
                     .where(kb_notes.c.user_id == user_id, kb_notes.c.vault == vault, kb_notes.c.status == "active",
                            kb_links.c.target_slug == note["slug"], kb_notes.c.id != note["id"])
                     .order_by(kb_notes.c.title))
        if family_mode:
            backlinks = backlinks.where(kb_notes.c.hidden.is_(False))
        note["backlinks"] = [dict(row._mapping) for row in conn.execute(backlinks)]
        _with_files(conn, user_id, vault, [note], family_mode)
        own = {row["name"].lower() for row in note["files"]}
        others = [key for key in placed_files(note["content"]) if key not in own]
        note["placed_files"] = _kept_files(
            conn, user_id, vault, family_mode, "AND f.note_id <> :note_id AND (lower(f.name) = ANY(:keys) "
            "OR f.file_id = ANY(:keys))", note_id=note["id"], keys=others) if others else []
    return note


def list_notes(user_id: int, tag: Optional[str] = None, limit: int = 50, status: str = "active",
               vault: int = 0, family_mode: bool = False) -> dict:
    """
    The notes of a vault with a status (the active ones by default), most recently updated first,
    without the memory (and with family_mode without the hidden notes).

    Returns:
        {"notes": [...] (without content, each with "files": the files it keeps), "total": the number
         of matching notes, "tags": [(tag, count)], the 20 most used tags (only without a tag filter)}
    """
    tag_filter = normalize_tags([tag])[0] if tag and tag.strip().lstrip("#").strip() else None
    conditions = [kb_notes.c.user_id == user_id, kb_notes.c.vault == vault,
                  kb_notes.c.status == _check_status(status), kb_notes.c.slug != MEMORY_SLUG]
    if tag_filter:
        conditions.append(kb_notes.c.tags.any(tag_filter))
    if family_mode:
        conditions.append(kb_notes.c.hidden.is_(False))
    with db.connection() as conn:
        total = conn.execute(select(func.count()).select_from(kb_notes).where(*conditions)).scalar_one()
        notes = [
            dict(row._mapping) for row in conn.execute(
                select(kb_notes.c.id, kb_notes.c.slug, kb_notes.c.title, kb_notes.c.description, kb_notes.c.tags,
                       kb_notes.c.status, kb_notes.c.hidden, kb_notes.c.hidden_by, kb_notes.c.updated_at)
                .where(*conditions)
                .order_by(kb_notes.c.updated_at.desc().nulls_last(), kb_notes.c.id.desc())
                .limit(limit)
            )
        ]
        _with_files(conn, user_id, vault, notes, family_mode)
        tags = []
        if not tag_filter:
            tags = [tuple(row) for row in conn.execute(text(
                "SELECT tag, count(*) AS n FROM kb_notes, unnest(tags) AS tag "
                "WHERE user_id = :user_id AND vault = :vault AND status = :status AND slug <> :memory "
                + ("AND NOT hidden " if family_mode else "") +
                "GROUP BY tag ORDER BY n DESC, tag LIMIT 20"
            ), {"user_id": user_id, "vault": vault, "status": status, "memory": MEMORY_SLUG})]
    return {"notes": notes, "total": total, "tags": tags}


def count_notes(user_id: int, vault: int = 0, family_mode: bool = False) -> dict:
    """The number of notes of a vault per status, without the memory: {"active": n, "archived": n}."""
    conditions = [kb_notes.c.user_id == user_id, kb_notes.c.vault == vault, kb_notes.c.slug != MEMORY_SLUG]
    if family_mode:
        conditions.append(kb_notes.c.hidden.is_(False))
    with db.connection() as conn:
        rows = conn.execute(select(kb_notes.c.status, func.count()).where(*conditions)
                            .group_by(kb_notes.c.status)).all()
    counts = dict.fromkeys(STATUSES, 0)
    counts.update({row[0]: row[1] for row in rows})
    return counts


def all_notes(user_id: int, vault: int = 0, family_mode: bool = False) -> list[dict]:
    """
    All notes of a vault with their content and the files they keep ("files"), active and archived
    and the memory, by slug (for the export); with family_mode without the hidden notes, lines and files.
    """
    query = select(*_NOTE_COLUMNS).where(kb_notes.c.user_id == user_id, kb_notes.c.vault == vault)
    if family_mode:
        query = query.where(kb_notes.c.hidden.is_(False))
    with db.connection() as conn:
        notes = [dict(row._mapping) for row in conn.execute(query.order_by(kb_notes.c.slug))]
        _with_files(conn, user_id, vault, notes, family_mode)
    if family_mode:
        for note in notes:
            note["content"] = hidden_content.visible(note["content"])
    return notes


def changes_since(user_id: int, vault: int, since: datetime, until: Optional[datetime] = None) -> list[dict]:
    """
    The changes of a vault's notes between since and until (naive UTC), oldest first: one row per
    note and author (who: 'agent', 'review', 'dream', 'user'), with its actions, the agent's name
    and the time of the last one. For the nightly consolidation.
    """
    conditions = ["n.user_id = :user_id", "n.vault = :vault", "r.created_at > :since"]
    params: dict = {"user_id": user_id, "vault": vault, "since": since}
    if until is not None:
        conditions.append("r.created_at <= :until")
        params["until"] = until
    with db.connection() as conn:
        rows = conn.execute(text(f"""
            SELECT n.slug, n.title, n.description, n.status, r.author, p.name AS persona_name,
                   array_agg(DISTINCT r.action) AS actions, max(r.created_at) AS changed_at
            FROM kb_note_revisions r
            JOIN kb_notes n ON n.id = r.note_id
            LEFT JOIN personas p ON p.id = r.persona_id
            WHERE {' AND '.join(conditions)}
            GROUP BY n.slug, n.title, n.description, n.status, r.author, p.name
            ORDER BY max(r.created_at)
        """), params).all()
    return [dict(row._mapping) for row in rows]


def list_vaults(user_id: int, family_mode: bool = False) -> list[dict]:
    """
    The user's vaults that have notes: [{"vault", "active", "archived", "memory_lines"}], by vault.
    With family_mode without the own ones of hidden agents, hidden notes and the memory's hidden lines.
    """
    shown = "AND NOT hidden " if family_mode else ""
    with db.connection() as conn:
        rows = conn.execute(text(
            "SELECT vault, "
            f"count(*) FILTER (WHERE slug <> :memory AND status = 'active' {shown}) AS active, "
            f"count(*) FILTER (WHERE slug <> :memory AND status = 'archived' {shown}) AS archived, "
            "max(content) FILTER (WHERE slug = :memory) AS memory "
            "FROM kb_notes WHERE user_id = :user_id "
            + ("AND (vault = 0 OR vault NOT IN (SELECT id FROM personas WHERE hidden)) " if family_mode else "") +
            "GROUP BY vault ORDER BY vault"
        ), {"user_id": user_id, "memory": MEMORY_SLUG}).all()
    return [{"vault": row.vault, "active": row.active, "archived": row.archived,
             "memory_lines": memory_usage((hidden_content.visible(row.memory) if family_mode else row.memory) or "")[0]}
            for row in rows]


_REVISION_SUMMARY_COLUMNS = (
    kb_note_revisions.c.id, kb_note_revisions.c.action, kb_note_revisions.c.title, kb_note_revisions.c.status,
    kb_note_revisions.c.author, kb_note_revisions.c.conversation_id,
    conversations.c.name.label("conversation_name"), kb_note_revisions.c.persona_id,
    personas.c.name.label("persona_name"), kb_note_revisions.c.reason, kb_note_revisions.c.created_at,
)


def _revisions_query(user_id: int, note_id: int, *columns):
    """A note's revisions with the names of their conversation (if the user still has it) and agent."""
    return (
        select(*_REVISION_SUMMARY_COLUMNS, *columns)
        .select_from(
            kb_note_revisions
            .outerjoin(conversations, (conversations.c.id == kb_note_revisions.c.conversation_id)
                       & (conversations.c.userId == user_id))
            .outerjoin(personas, personas.c.id == kb_note_revisions.c.persona_id)
        )
        .where(kb_note_revisions.c.note_id == note_id)
    )


def list_revisions(user_id: int, ref: str, vault: int = 0, family_mode: bool = False) -> list[dict]:
    """
    A note's versions, newest first, without their content: action, author, the conversation and
    agent they were written in (conversation_name None if it was deleted), reason.

    Raises:
        KBNotFound: There is no such note.
    """
    with db.connection() as conn:
        note = _find_note(conn, user_id, ref, vault=vault, family_mode=family_mode)
        if note is None:
            raise _not_found(ref)
        return [dict(row._mapping) for row in conn.execute(
            _revisions_query(user_id, note["id"]).order_by(kb_note_revisions.c.id.desc())
        )]


def get_revision(user_id: int, ref: str, revision_id: int, vault: int = 0, family_mode: bool = False) -> dict:
    """
    One version of a note, with its description, tags and content (with family_mode without its hidden lines).

    Raises:
        KBNotFound: There is no such note, or the version isn't one of it.
    """
    with db.connection() as conn:
        note = _find_note(conn, user_id, ref, vault=vault, family_mode=family_mode)
        if note is None:
            raise _not_found(ref)
        row = conn.execute(
            _revisions_query(user_id, note["id"], kb_note_revisions.c.description, kb_note_revisions.c.tags,
                             kb_note_revisions.c.content)
            .where(kb_note_revisions.c.id == revision_id)
        ).first()
    if row is None:
        raise KBNotFound(f"Note '{note['slug']}' has no version {revision_id}")
    revision = dict(row._mapping)
    if family_mode:
        revision["content"] = hidden_content.visible(revision["content"])
    return revision


# Title words count most, then description and tags, then the content
_DOCUMENT = ("setweight(to_tsvector('simple', title), 'A') || "
             "setweight(to_tsvector('simple', coalesce(description, '') || ' ' || array_to_string(tags, ' ')), 'B') || "
             "setweight(to_tsvector('simple', content), 'D')")
_EXACT_FIELDS = ("slug", "title", "coalesce(description, '')", "array_to_string(tags, ' ')", "content")
# The content without the lines tagged #hidden, for a search that is in family mode (the sections of a
# tagged heading still match: best effort, the snippet comes from hidden_content.visible())
_VISIBLE_CONTENT = r"regexp_replace(content, '(?n)^.*(^|\s)#hidden([^\w/-].*)?$', '', 'gi')"


def search_notes(user_id: int, query: Optional[str] = None, exact: Optional[Iterable[str]] = None,
                 tags: Optional[Iterable[str]] = None, limit: int = 10, status: str = "active",
                 vault: int = 0, family_mode: bool = False) -> list[dict]:
    """
    Search the notes of a vault with a status (the active ones by default) by words, exact text and
    tags. The memory is left out: it is part of every answer anyway. With family_mode, hidden notes and
    lines are left out.

    A note is found if it contains any query word, any exact text or any of the tags. The score is
    the full-text rank of the words, plus 1 per exact text it contains and 0.3 per tag it has; ties
    go to the more recently updated note.

    Args:
        query: Words to look for (any of them; more and rarer matches rank higher).
        exact: Literal texts, matched as case-insensitive substrings of slug, title, description,
            tags and content.
        tags: Tags; notes with them rank higher.

    Returns:
        The best notes, each with "matched" (the ways it matched: "words", "exact", "tags") and
        "files" (the files it keeps).

    Raises:
        KBError: Neither query words, exact texts nor tags.
    """
    words = _query_words(query or "")
    exact = [value.strip() for value in (exact or ()) if value and value.strip()]
    tags = normalize_tags(tags)
    if not (words or exact or tags):
        raise KBError("Give at least one of query (words), exact (a literal text) or tags")

    params: dict = {"user_id": user_id, "vault": vault, "limit": limit, "status": _check_status(status),
                    "memory": MEMORY_SLUG}
    document = _DOCUMENT.replace("content", _VISIBLE_CONTENT) if family_mode else _DOCUMENT
    fields = tuple(_VISIBLE_CONTENT if field == "content" else field for field in _EXACT_FIELDS) if family_mode \
        else _EXACT_FIELDS
    matches, scores, columns = [], [], []
    if words:
        params["tsquery"] = _tsquery(words)
        matches.append(f"({document}) @@ to_tsquery('simple', :tsquery)")
        columns.append(f"ts_rank({document}, to_tsquery('simple', :tsquery)) AS word_rank")
        scores.append("word_rank")
    if exact:
        hits = []
        for i, value in enumerate(exact[:10]):
            params[f"exact{i}"] = f"%{_escape_like(value)}%"
            hits.append("(CASE WHEN " + " OR ".join(f"{field} ILIKE :exact{i}" for field in fields)
                        + " THEN 1 ELSE 0 END)")
        columns.append(f"({' + '.join(hits)}) AS exact_hits")
        matches.append(f"({' + '.join(hits)}) > 0")
        scores.append("exact_hits")
    if tags:
        params["tags"] = tags
        columns.append("(SELECT count(*) FROM unnest(tags) AS tag WHERE tag = ANY(:tags)) AS tag_hits")
        matches.append("tags && CAST(:tags AS TEXT[])")
        scores.append("0.3 * tag_hits")

    sql = f"""
        SELECT * FROM (
            SELECT id, slug, title, description, tags, status, hidden, hidden_by, content, updated_at, {', '.join(columns)}
            FROM kb_notes
            WHERE user_id = :user_id AND vault = :vault AND status = :status AND slug <> :memory
              {'AND NOT hidden' if family_mode else ''} AND ({' OR '.join(matches)})
        ) AS hits
        ORDER BY {' + '.join(scores)} DESC, updated_at DESC NULLS LAST
        LIMIT :limit
    """
    with db.connection() as conn:
        rows = [dict(row._mapping) for row in conn.execute(text(sql), params)]
        _with_files(conn, user_id, vault, rows, family_mode)

    for row in rows:
        row["matched"] = [name for name, key in (("words", "word_rank"), ("exact", "exact_hits"), ("tags", "tag_hits"))
                          if row.get(key)]
        content = row.pop("content")
        row["snippet"] = _snippet(hidden_content.visible(content) if family_mode else content, exact + words)
    return rows


def _snippet(content: str, needles: list[str], width: int = 220) -> str:
    """The part of the content around the first needle found in it, else its beginning; on one line."""
    lowered = content.lower()
    positions = [pos for pos in (lowered.find(needle.lower()) for needle in needles) if pos >= 0]
    start = max(0, min(positions) - width // 3) if positions else 0
    snippet = " ".join(content[start:start + width].split())
    return ("…" if start > 0 else "") + snippet + ("…" if start + width < len(content) else "")


# =========================================================================
# Writing
# =========================================================================

def _add_revision(conn: Connection, note: dict, action: str, writer: Writer, reason: Optional[str] = None) -> None:
    """Store the note as it is now as a new revision; its id becomes the note's "version"."""
    note["version"] = conn.execute(insert(kb_note_revisions).values(
        note_id=note["id"], action=action, title=note["title"], description=note["description"],
        tags=note["tags"], content=note["content"], status=note["status"], author=writer.author,
        conversation_id=writer.conversation_id, persona_id=writer.persona_id, reason=reason,
    ).returning(kb_note_revisions.c.id)).scalar_one()


def _set_links(conn: Connection, note_id: int, content: str) -> None:
    conn.execute(delete(kb_links).where(kb_links.c.note_id == note_id))
    targets = link_targets(content)
    if targets:
        conn.execute(pg_insert(kb_links).values([{"note_id": note_id, "target_slug": slug} for slug in targets])
                     .on_conflict_do_nothing())


def create_note(writer: Writer, title: str, content: str, description: Optional[str] = None,
                tags: Optional[Iterable[str]] = None, hidden_note: bool = False,
                files: Optional[Iterable[dict]] = None) -> dict:
    """
    Create a note in the writer's vault; its slug is made from the title. It is hidden if hidden_note
    or the writer writes from a hidden conversation, and the mark is the writer's (hidden_by).

    Args:
        files: Stored files the note keeps (rows of uploaded_files, the writer's own), e.g. an image
            of the conversation. Each gets a name in the knowledge base, made from the note's slug,
            and the text places it: where it names the file already, else at its start (_place_files()).

    Returns:
        The note, with "kept" (the names of the files it keeps now) and "kept_already" (files given
        that a note keeps already: name -> that note's slug).

    Raises:
        KBError: Invalid fields, a note with that slug exists already (also an archived one), the
            title would give the memory's slug, or more files than a note keeps.
    """
    title = _clean_title(title)
    values = {
        "user_id": writer.user_id, "vault": writer.vault, "slug": note_slug(title), "title": title,
        "description": _clean_description(description), "tags": normalize_tags(tags),
        "content": _clean_content(content, title), "hidden": bool(hidden_note or writer.from_hidden),
    }
    values["hidden_by"] = _marker(writer) if values["hidden"] else None
    if values["slug"] == MEMORY_SLUG:
        raise KBError(f"The title \"{title}\" is reserved for the memory; choose a different title"
                      + (", or change the memory with memory_add, memory_replace and memory_remove"
                         if writer.author != "user" else ""))
    try:
        with db.connection() as conn:
            existing = _find_note(conn, writer.user_id, values["slug"], vault=writer.vault)
            if existing is not None and existing["slug"] == values["slug"]:
                raise _exists(existing, writer)
            plan = _plan_files(conn, writer, values["slug"], None, files)
            if plan:
                values["content"] = _check_length(_place_files(values["content"], plan))
            note = dict(conn.execute(insert(kb_notes).values(**values).returning(*_NOTE_COLUMNS)).one()._mapping)
            note["kept"] = _keep_files(conn, writer, note["id"], plan)
            note["kept_already"] = {kept.name: kept.note for kept in plan if kept.note is not None}
            _add_revision(conn, note, "create", writer)
            _set_links(conn, note["id"], note["content"])
    except IntegrityError:
        # The same slug, written at the same moment by a parallel tool call
        with db.connection() as conn:
            existing = _find_note(conn, writer.user_id, values["slug"], vault=writer.vault)
        if existing is None:
            raise
        raise _exists(existing, writer)
    log.info(f"Knowledge base {_vault_name(writer)}: created note {note['slug']}")
    return note


def _marker(writer: Writer) -> str:
    """Who sets a mark: the user (on the page) or an agent (an answer, the memory review, the consolidation)."""
    return "user" if writer.author == "user" else "agent"


def _vault_name(writer: Writer) -> str:
    """The vault for log lines: "user 3", "user 3, agent 7"."""
    return f"of user {writer.user_id}" + (f", agent {writer.vault}" if writer.vault else "")


def _memory_by_line() -> KBError:
    return KBError("The memory is changed line by line: use memory_add, memory_replace or memory_remove")


def _exists(note: dict, writer: Optional[Writer] = None) -> KBError:
    if writer is not None and writer.family_mode and note.get("hidden"):
        return KBError("A note with this slug exists already; choose a different title")
    archived = " (archived)" if note["status"] == "archived" else ""
    return KBExists(f"A note with the slug '{note['slug']}' exists already{archived}: \"{note['title']}\". "
                    f"Change it with kb_update (this also restores an archived note), or choose a different title",
                    note)


def update_note(writer: Writer, ref: str, content: Optional[str] = None, append: Optional[str] = None,
                title: Optional[str] = None, description: Optional[str] = None,
                tags: Optional[Iterable[str]] = None, base_version: Optional[int] = None,
                reason: Optional[str] = None, hidden_note: Optional[bool] = None,
                files: Optional[Iterable[dict]] = None) -> tuple[dict, list[str]]:
    """
    Change a note; its slug stays. Updating an archived note restores it. Only the user (the page)
    changes the memory this way; the agent changes it line by line (memory_add() and the like).

    Args:
        content: Replaces the whole content.
        append: Added at the end of the content (not together with content).
        title, description: Replace them ("" removes the description).
        tags: Replaces the list of tags ([] removes them).
        base_version: The version the change was made on (the page); refused if the note changed since.
        reason: Stored with the revision (e.g. which version was restored).
        hidden_note: Hides the note or not. From the page it is the user's decision; an agent
            can't change a mark the user set (refused if it is the only change, else left alone).
        files: Stored files the note keeps from now on, as for create_note(). The new content or
            the appended text places them; with neither, they are placed at the note's end.

    A writer that is in family mode (Writer.family_mode) wrote content without the hidden lines, which
    are put back; one from a hidden conversation (Writer.from_hidden) tags the lines it adds, unless the
    note is hidden anyway.

    Returns:
        (the note, with "kept" and "kept_already" as from create_note(); what changed, [] if the
        values were the same already)

    Raises:
        KBError: No such note (KBNotFound), the note changed since base_version (KBConflict),
            nothing to change, content and append together, invalid fields, the memory and not the
            user, more files than a note keeps.
    """
    files = list(files or ())
    if content is not None and append is not None:
        raise KBError("Give either content (replaces the whole text) or append (adds to the end), not both")
    if all(value is None for value in (content, append, title, description, tags, hidden_note)) and not files:
        raise KBError("Nothing to change: give content, append, title, description or tags")

    with db.connection() as conn:
        note = _find_note(conn, writer.user_id, ref, lock=True, vault=writer.vault, family_mode=writer.family_mode)
        if note is None:
            raise _not_found(ref)
        if note["slug"] == MEMORY_SLUG and writer.author != "user":
            raise _memory_by_line()
        if note["slug"] == MEMORY_SLUG and hidden_note:
            raise KBError("The memory can't be hidden as a whole; tag its hidden lines with #hidden")
        note["version"] = _version(conn, note["id"])
        if base_version is not None and base_version != note["version"]:
            raise KBConflict(f"Note '{note['slug']}' changed since version {base_version}; it is at version "
                             f"{note['version']} now", note["version"])
        new = dict(note)
        changes = []
        if title is not None:
            new["title"] = _clean_title(title)
        plan = _plan_files(conn, writer, note["slug"], note["id"], files)
        if plan and note["slug"] == MEMORY_SLUG:
            raise KBError("The memory keeps no files; write a note for the file and point to it from the memory")
        if plan and content is not None:
            content = _place_files(_clean_content(content, new["title"]), plan)
        elif plan and append is not None:
            append = _place_files(append.strip(), plan, at_end=True)
        elif plan:
            # Placed at the note's end, unless its text shows them already
            shown = placed_files(note["content"])
            append = "\n".join(f"![[{kept.name}]]" for kept in plan if kept.name.lower() not in shown) or None
        tag_new = writer.from_hidden and not note["hidden"]
        if content is not None:
            new["content"] = _clean_content(content, new["title"])
            if writer.family_mode:
                new["content"] = hidden_content.restore_hidden(note["content"], new["content"])
            if tag_new:
                new["content"] = hidden_content.tag_new_lines(note["content"], new["content"])
        if append is not None:
            addition = append.strip()
            if not addition:
                raise KBError("append must not be empty")
            if tag_new:
                addition = hidden_content.tag_lines(addition)
            new["content"] = _clean_content(f"{note['content'].rstrip()}\n\n{addition}", new["title"])
        if description is not None:
            new["description"] = _clean_description(description)
        if tags is not None:
            new["tags"] = normalize_tags(tags)
        # Agents never change what the user decided, and take back only marks of agents
        user_mark = writer.author != "user" and (note["hidden_by"] == "user"
                                                 or (note["hidden"] and note["hidden_by"] != "agent"))
        if hidden_note is not None and bool(hidden_note) != note["hidden"]:
            if not user_mark:
                new["hidden"], new["hidden_by"] = bool(hidden_note), _marker(writer)
            elif all(value is None for value in (content, append, title, description, tags)):
                raise KBError(f"The user decided this note is {'' if note['hidden'] else 'not '}hidden, so it stays "
                              f"as it is")

        if new["title"] != note["title"]:
            changes.append(f"title → \"{new['title']}\"")
        if new["content"] != note["content"]:
            changes.append(f"appended {len(append.strip())} characters" if append is not None else "content replaced")
        new_files = [kept.name for kept in plan if kept.note is None]
        if new_files:
            changes.append(f"keeps {', '.join(new_files)}")
        if new["description"] != note["description"]:
            changes.append("description changed" if new["description"] else "description removed")
        if new["tags"] != note["tags"]:
            changes.append(f"tags → [{', '.join(new['tags'])}]")
        if new["hidden"] != note["hidden"]:
            changes.append("hidden" if new["hidden"] else "no longer hidden")
        if note["status"] == "archived":
            new["status"] = "active"
            changes.append("restored from the archive")
        if not changes:
            note["kept"], note["kept_already"] = [], {kept.name: kept.note for kept in plan}
            return note, []
        if hidden_note is not None and bool(hidden_note) != note["hidden"] and user_mark:
            changes.append("the hidden mark stays as the user set it")

        content_changed = new["content"] != note["content"]
        note = dict(conn.execute(
            update(kb_notes).where(kb_notes.c.id == note["id"])
            .values(title=new["title"], description=new["description"], tags=new["tags"],
                    content=new["content"], status=new["status"], hidden=new["hidden"], hidden_by=new["hidden_by"])
            .returning(*_NOTE_COLUMNS)
        ).one()._mapping)
        note["kept"] = _keep_files(conn, writer, note["id"], plan)
        note["kept_already"] = {kept.name: kept.note for kept in plan if kept.note is not None}
        _add_revision(conn, note, "update", writer, reason=reason)
        if content_changed:
            _set_links(conn, note["id"], note["content"])
    log.info(f"Knowledge base {_vault_name(writer)}: updated note {note['slug']} ({', '.join(changes)})")
    return note, changes


def archive_note(writer: Writer, ref: str, reason: Optional[str] = None) -> tuple[dict, bool]:
    """
    Archive a note: lists and searches skip it, reading it still works, an update restores it.

    Returns:
        (the note, False if it was archived already)

    Raises:
        KBError: There is no such note, or it is the memory (which is never archived).
    """
    with db.connection() as conn:
        note = _find_note(conn, writer.user_id, ref, lock=True, vault=writer.vault, family_mode=writer.family_mode)
        if note is None:
            raise _not_found(ref)
        if note["slug"] == MEMORY_SLUG:
            raise (KBError("The memory can't be archived; delete it instead") if writer.author == "user"
                   else _memory_by_line())
        if note["status"] == "archived":
            note["version"] = _version(conn, note["id"])
            return note, False
        note = dict(conn.execute(
            update(kb_notes).where(kb_notes.c.id == note["id"]).values(status="archived").returning(*_NOTE_COLUMNS)
        ).one()._mapping)
        _add_revision(conn, note, "archive", writer, reason=" ".join((reason or "").split()) or None)
    log.info(f"Knowledge base {_vault_name(writer)}: archived note {note['slug']}")
    return note, True


def restore_note(writer: Writer, ref: str) -> tuple[dict, bool]:
    """
    Bring an archived note back to the lists and searches, unchanged (the page; the agent restores
    a note by updating it).

    Returns:
        (the note, False if it was active already)

    Raises:
        KBNotFound: There is no such note.
    """
    with db.connection() as conn:
        note = _find_note(conn, writer.user_id, ref, lock=True, vault=writer.vault, family_mode=writer.family_mode)
        if note is None:
            raise _not_found(ref)
        if note["status"] == "active":
            note["version"] = _version(conn, note["id"])
            return note, False
        note = dict(conn.execute(
            update(kb_notes).where(kb_notes.c.id == note["id"]).values(status="active").returning(*_NOTE_COLUMNS)
        ).one()._mapping)
        _add_revision(conn, note, "restore", writer)
    log.info(f"Knowledge base {_vault_name(writer)}: restored note {note['slug']}")
    return note, True


def restore_revision(writer: Writer, ref: str, revision_id: int,
                     base_version: Optional[int] = None) -> tuple[dict, list[str]]:
    """
    Make an earlier version of a note its current one again, as a new revision (so nothing is lost).

    Raises:
        KBNotFound: There is no such note or version. KBConflict: the note changed since base_version.
    """
    revision = get_revision(writer.user_id, ref, revision_id, vault=writer.vault, family_mode=writer.family_mode)
    when = revision["created_at"].strftime("%Y-%m-%d %H:%M") if revision["created_at"] else f"#{revision_id}"
    return update_note(writer, ref, content=revision["content"], title=revision["title"],
                       description=revision["description"] or "", tags=revision["tags"],
                       base_version=base_version, reason=f"Restored the version of {when}")


def delete_note(user_id: int, ref: str, vault: int = 0, family_mode: bool = False) -> str:
    """
    Delete a note for good, with all its versions and the files it keeps (only from the page: the
    agent can only archive). A kept file that a conversation still has stays there. Links to the
    note from other notes stay and point to a note that doesn't exist (any more).

    Returns:
        The slug of the deleted note.

    Raises:
        KBNotFound: There is no such note.
    """
    with db.connection() as conn:
        note = _find_note(conn, user_id, ref, lock=True, vault=vault, family_mode=family_mode)
        if note is None:
            raise _not_found(ref)
        kept = list(conn.execute(select(kb_files.c.file_id).where(kb_files.c.note_id == note["id"])).scalars())
        conn.execute(delete(kb_notes).where(kb_notes.c.id == note["id"]))
    _delete_unused_files(kept)
    log.info(f"Knowledge base {user_id}/{vault}: deleted note {note['slug']} for good")
    return note["slug"]


# =========================================================================
# Files
# =========================================================================

@dataclass
class _Kept:
    """A file of a note write: the stored file and its name in the knowledge base."""
    row: dict                    # The stored file (uploaded_files)
    name: str                    # Its name in the knowledge base
    note: Optional[str] = None   # The slug of the note that keeps it already; None: this write keeps it
    placed: bool = False         # The note's text places it


def _address(raw: str) -> str:
    """The address of a Markdown image without its "title" and <angle brackets>."""
    target = re.sub(r"\s+(?:\"[^\"]*\"|'[^']*')$", "", raw.strip()).strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    return target


def _plain_name(reference: str) -> str:
    """A reference as a plain file name: sandbox:/mnt/data/My%20Fox.png -> My Fox.png"""
    name = re.sub(r"^[a-z][a-z0-9+.-]*:", "", reference.strip(), flags=re.IGNORECASE)
    name = re.split(r"[?#]", name, maxsplit=1)[0].rstrip("/")
    return unquote(name.rsplit("/", 1)[-1]).strip()


def _file_key(reference: str) -> str:
    """What a reference to a file is compared by: a file ID as it is, a name plain and in lowercase."""
    reference = (reference or "").strip().strip("\"'")
    return reference if file_utils.is_file_id(reference) else _plain_name(reference).lower()


def _replace_placed(content: str, replace: Callable[[str], Optional[str]]) -> str:
    """
    The content with the files it places (outside of code; web addresses are no files) named anew:
    replace(the reference's key) gives the new name, or None to leave it as it is.
    """
    def placed(match: re.Match) -> str:
        embed = match.group(1) is not None
        reference = match.group(1).strip() if embed else _address(match.group(4))
        if not embed and _WEB_ADDRESS_RE.match(reference):
            return match.group(0)
        name = replace(_file_key(reference))
        if name is None:
            return match.group(0)
        return f"![[{name}{match.group(2) or ''}]]" if embed else f"![{match.group(3)}]({name})"

    parts = CODE_RE.split(content)
    return "".join(part if index % 2 else _EMBED_RE.sub(placed, part) for index, part in enumerate(parts))


def placed_files(content: Optional[str]) -> list[str]:
    """The files a text places, in order and each once: names plain and in lowercase, file IDs as they are."""
    keys: list[str] = []

    def seen(key: str) -> None:
        if key and key not in keys:
            keys.append(key)

    _replace_placed(content or "", seen)
    return keys


def _file_shown(name: str, content: Optional[str]) -> bool:
    """For family mode: a kept file is left out if its note's text places it in hidden lines only."""
    key = name.lower()
    return key in placed_files(hidden_content.visible(content)) or key not in placed_files(content)


def _kept_files(conn: Connection, user_id: int, vault: int, family_mode: bool = False, where: str = "",
                **params) -> list[dict]:
    """
    Files the notes of a vault keep, in the order they were kept: the stored file's columns
    (uploaded_files), with "name" its name in the knowledge base ("original_name": the one it was
    stored under), and the note that keeps it ("note_id", "note_slug", "note_title", "note_status").
    With family_mode without the files of hidden notes and the ones only hidden lines place.

    Args:
        where: A further condition on kb_files f, kb_notes n or uploaded_files u ("AND ..."), with params.
    """
    rows = conn.execute(text(
        "SELECT u.*, f.name AS kb_name, f.note_id, n.slug AS note_slug, n.title AS note_title, "
        "n.status AS note_status, n.hidden AS note_hidden"
        + (", n.content AS note_content" if family_mode else "") +
        " FROM kb_files f JOIN kb_notes n ON n.id = f.note_id JOIN uploaded_files u ON u.file_id = f.file_id "
        f"WHERE f.user_id = :user_id AND f.vault = :vault {where} ORDER BY f.id"
    ), {"user_id": user_id, "vault": vault, **params})
    files = []
    for row in rows:
        row = dict(row._mapping)
        content = row.pop("note_content", None)
        if family_mode and (row["note_hidden"] or not _file_shown(row["kb_name"], content)):
            continue
        row["original_name"], row["name"] = row["name"], row.pop("kb_name")
        files.append(row)
    return files


def vault_files(user_id: int, vault: int = 0, family_mode: bool = False) -> list[dict]:
    """The files the notes of a vault keep, in the order they were kept (see _kept_files())."""
    with db.connection() as conn:
        return _kept_files(conn, user_id, vault, family_mode)


def find_file(user_id: int, vault: int, reference: str, family_mode: bool = False) -> Optional[dict]:
    """
    The kept file of a vault that a reference names: by its name in the knowledge base (whatever
    its case) or by its file ID. None if the vault keeps no such file (or, with family_mode, hides it).
    """
    key = _file_key(reference)
    if not key:
        return None
    where = "AND f.file_id = :key" if file_utils.is_file_id(key) else "AND lower(f.name) = :key"
    with db.connection() as conn:
        files = _kept_files(conn, user_id, vault, family_mode, where, key=key)
    return files[0] if files else None


def _with_files(conn: Connection, user_id: int, vault: int, notes: list[dict], family_mode: bool = False) -> None:
    """Give each of the notes (rows with "id") its "files": the files it keeps."""
    ids = [note["id"] for note in notes]
    kept = _kept_files(conn, user_id, vault, family_mode, "AND f.note_id = ANY(:ids)", ids=ids) if ids else []
    for note in notes:
        note["files"] = [row for row in kept if row["note_id"] == note["id"]]


def _plan_files(conn: Connection, writer: Writer, slug: str, note_id: Optional[int],
                files: Optional[Iterable[dict]]) -> list[_Kept]:
    """
    What a write of the note `slug` does with the stored files it is given (rows of uploaded_files):
    a file the vault keeps already goes by its name there, a new one is named after the note,
    <slug>.png, further ones <slug>-2.jpg and so on (whatever their type: no two kept files differ
    only in their ending). Nothing is stored yet (_keep_files()).

    Raises:
        KBError: A file isn't the writer's, or the note would keep more than MAX_NOTE_FILES.
    """
    rows: dict[str, dict] = {}
    for row in files or ():
        if row.get("user_id") != writer.user_id:
            raise KBError(f"The file '{file_store.file_name(row)}' can't be kept: it isn't the user's")
        rows.setdefault(row["file_id"], row)
    if not rows:
        return []
    # Names are unique in the vault: one write at a time picks them
    conn.execute(text("SELECT pg_advisory_xact_lock(:key, :user_id)"),
                 {"key": _FILES_LOCK, "user_id": writer.user_id})
    names = conn.execute(select(kb_files.c.name, kb_files.c.note_id)
                         .where(kb_files.c.user_id == writer.user_id, kb_files.c.vault == writer.vault)).all()
    taken = {row.name.lower().rsplit(".", 1)[0] for row in names}
    # What the writer may know is kept: on a device in family mode a hidden file is kept once more, under a
    # name of this note, rather than named
    known = {row["file_id"]: row for row in reversed(_kept_files(
        conn, writer.user_id, writer.vault, writer.family_mode, "AND f.file_id = ANY(:ids)", ids=list(rows)))}
    plan = []
    for file_id, row in rows.items():
        if file_id in known:
            plan.append(_Kept(row, known[file_id]["name"], note=known[file_id]["note_slug"]))
            continue
        stem, number = slug, 1
        while stem in taken:
            number += 1
            stem = f"{slug}-{number}"
        taken.add(stem)
        extension = file_store.extension_for(row.get("mime_type"), row.get("original_name") or row.get("name"))
        plan.append(_Kept(row, f"{stem}{extension.lower()}"))
    new = sum(1 for kept in plan if kept.note is None)
    own = sum(1 for row in names if row.note_id == note_id) if note_id is not None else 0
    if new and own + new > MAX_NOTE_FILES:
        raise KBError(f"A note keeps at most {MAX_NOTE_FILES} files ({own} kept, {new} more given): write "
                      f"further notes for the others, one note per image")
    return plan


def _keep_files(conn: Connection, writer: Writer, note_id: int, plan: list[_Kept]) -> list[str]:
    """Store the new files of a plan as files of the note; returns their names."""
    new = [{"user_id": writer.user_id, "vault": writer.vault, "note_id": note_id, "name": kept.name,
            "file_id": kept.row["file_id"]} for kept in plan if kept.note is None]
    if new:
        conn.execute(insert(kb_files), new)
    return [row["name"] for row in new]


def _place_files(content: str, plan: list[_Kept], at_end: bool = False) -> str:
    """
    A note's text with the files of a write placed under their names in the knowledge base. Where
    the text places one by the name or file ID it has in the conversation, that becomes its new
    name; the ones it doesn't place go before the text (at_end: after it), as ![[name]] on lines
    of their own.
    """
    known: dict[str, _Kept] = {}
    stored = [(kept.row.get("original_name") or kept.row.get("name") or "").lower() for kept in plan]
    for kept, original in zip(plan, stored):
        known[kept.row["file_id"]] = known[kept.name.lower()] = kept
    for kept, original in zip(plan, stored):
        if original and stored.count(original) == 1:
            known.setdefault(original, kept)

    def name(key: str) -> Optional[str]:
        kept = known.get(key)
        if kept is None:
            return None
        kept.placed = True
        return kept.name

    content = _replace_placed(content, name)
    lines = "\n".join(f"![[{kept.name}]]" for kept in plan if not kept.placed)
    if not lines or not content.strip():
        return lines or content
    return f"{content.rstrip()}\n\n{lines}" if at_end else f"{lines}\n\n{content.lstrip(chr(10))}"


def _without_file(content: str, name: str) -> str:
    """A note's text without the places that show the file `name`; a line left empty goes too."""
    marker = "\x00"
    marked = _replace_placed(content, lambda key: marker if key == name.lower() else None)
    if marker not in marked:
        return content
    lines = []
    for line in marked.split("\n"):
        if marker in line:
            line = re.sub(r"!\[\[\x00[^\]]*\]\]|!\[[^\x00]*?\]\(\x00\)", "", line)
            if not line.strip(" \t-*+>"):
                continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _delete_unused_files(file_ids: Iterable[str]) -> int:
    """
    Delete the stored files among these that nothing has any more: in no conversation and kept
    by no note. For what a deleted note kept. Returns how many were deleted.
    """
    deleted = 0
    for file_id in dict.fromkeys(file_ids):
        try:
            with db.connection() as conn:
                unused = conn.execute(text(
                    "SELECT 1 FROM uploaded_files u WHERE u.file_id = :id AND u.conversation_id IS NULL "
                    "AND NOT EXISTS (SELECT 1 FROM kb_files f WHERE f.file_id = u.file_id)"), {"id": file_id}).first()
            if unused:
                file_utils.delete_stored_file(file_id)
                db.delete_cache_by_file(file_id)
                db.delete_uploaded_file(file_id)
                deleted += 1
        except Exception as e:
            log.warning(f"Could not delete the file {file_id} a note kept: {type(e).__name__}: {e}")
    return deleted


def remove_file(writer: Writer, ref: str, name: str) -> tuple[dict, str]:
    """
    Take a file away from the note that keeps it (the page): the note's text no longer places it,
    and the stored file is deleted unless a conversation still has it.

    Returns:
        (the note, the removed file's name)

    Raises:
        KBNotFound: There is no such note, or it keeps no such file.
    """
    with db.connection() as conn:
        note = _find_note(conn, writer.user_id, ref, lock=True, vault=writer.vault, family_mode=writer.family_mode)
        if note is None:
            raise _not_found(ref)
        kept = _kept_files(conn, writer.user_id, writer.vault, writer.family_mode,
                           "AND f.note_id = :note_id AND lower(f.name) = :name",
                           note_id=note["id"], name=_file_key(name))
        if not kept:
            raise KBNotFound(f"Note '{note['slug']}' keeps no file '{name}'")
        file = kept[0]
        conn.execute(delete(kb_files).where(kb_files.c.note_id == note["id"],
                                            func.lower(kb_files.c.name) == file["name"].lower()))
        content = _without_file(note["content"], file["name"]) or note["content"]
        if content != note["content"]:
            note = dict(conn.execute(
                update(kb_notes).where(kb_notes.c.id == note["id"]).values(content=content).returning(*_NOTE_COLUMNS)
            ).one()._mapping)
        _add_revision(conn, note, "update", writer, reason=f"Removed the file {file['name']}")
    _delete_unused_files([file["file_id"]])
    log.info(f"Knowledge base {_vault_name(writer)}: note {note['slug']} no longer keeps {file['name']}")
    return note, file["name"]


# =========================================================================
# The memory
# =========================================================================

def _today() -> str:
    from backend.llm.prompts import memory_today
    return memory_today().isoformat()


def _heading(line: str) -> Optional[str]:
    """The text of a Markdown heading line, else None."""
    match = _HEADING_RE.match(line.strip())
    return match.group(1) if match else None


def memory_usage(content: str) -> tuple[int, int]:
    """(lines of text without headings and blank lines, characters) of a memory."""
    lines = [line for line in content.splitlines() if line.strip() and _heading(line) is None]
    return len(lines), len(content)


def _memory_text(text: Optional[str]) -> tuple[str, bool]:
    """
    One line of the memory as the agent gives it: on one line, without a bullet or date of its own,
    and whether it ended with the tag #hidden (which goes after the date).
    """
    text = " ".join((text or "").split())
    text = re.sub(r"^[-*+]\s+", "", text)
    text, tagged = hidden_content.strip_trailing_tag(text)
    text = _MEMORY_DATE_RE.sub("", text).strip()
    if not text:
        raise KBError("The text must not be empty")
    if len(text) > MEMORY_LINE_CHARS:
        raise KBError(f"A line of the memory has at most {MEMORY_LINE_CHARS} characters ({len(text)} given): keep "
                      f"it short and put the details into a note (kb_write) that the line points to with [[slug]]")
    return text, tagged


def _memory_line(text: str, tagged: bool = False) -> str:
    """A line of the memory: "- <text> (<date>)", with " #hidden" at the end if tagged."""
    return f"- {text} ({_today()})" + (f" {hidden_content.TAG}" if tagged else "")


def _line_key(line: str) -> str:
    """A memory line without bullet, date and #hidden at its end, lowercased, to find duplicates."""
    line = hidden_content.strip_trailing_tag(re.sub(r"^\s*[-*+]\s+", "", line))[0]
    return _MEMORY_DATE_RE.sub("", line).strip().lower()


def _find_line(lines: list[str], part: str, family_mode: bool = False) -> int:
    """The index of the one line of text that contains part (case-insensitive); with family_mode a visible one."""
    part = " ".join((part or "").split())
    if not part:
        raise KBError("Give a part of the line, e.g. a few words of it")
    needle = part.lower()
    hidden = hidden_content.hidden_mask(lines) if family_mode else [False] * len(lines)
    found = [i for i, line in enumerate(lines)
             if line.strip() and not hidden[i] and _heading(line) is None
             and needle in " ".join(line.split()).lower()]
    if not found:
        raise KBError(f"No line of the memory contains \"{part}\"; copy a part of the line from the memory in the "
                      f"system prompt")
    if len(found) > 1:
        raise KBError(f"{len(found)} lines of the memory contain \"{part}\"; give a longer part, so that it "
                      f"matches only one")
    return found[0]


def _tidy(lines: list[str]) -> str:
    """The lines as content: no headings without text under them, no runs of blank lines."""
    kept: list[str] = []
    for i, line in enumerate(lines):
        if _heading(line) is not None:
            following = next((other for other in lines[i + 1:] if other.strip()), None)
            if following is None or _heading(following) is not None:
                continue
            if kept and kept[-1].strip():
                kept.append("")
        elif not line.strip() and (not kept or not kept[-1].strip()):
            continue
        kept.append(line.rstrip())
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept)


def _check_memory_size(content: str) -> None:
    lines, chars = memory_usage(content)
    if lines > MEMORY_MAX_LINES or chars > MEMORY_MAX_CHARS:
        raise KBError(f"The memory is full ({lines} of {MEMORY_MAX_LINES} lines, {chars} of {MEMORY_MAX_CHARS} "
                      f"characters), so nothing was changed. Make room first: merge lines on the same topic "
                      f"(memory_replace), move details into notes and keep a short line that points to them "
                      f"with [[slug]], and remove lines that are outdated (memory_remove)")


def memory_status(content: str) -> str:
    """How full the memory is, with a reminder to tidy it up when it is nearly full."""
    lines, chars = memory_usage(content)
    status = f"The memory has {lines} of {MEMORY_MAX_LINES} lines and {chars} of {MEMORY_MAX_CHARS} characters."
    if lines >= MEMORY_NEAR_SHARE * MEMORY_MAX_LINES or chars >= MEMORY_NEAR_SHARE * MEMORY_MAX_CHARS:
        status += (" It is nearly full: merge lines on the same topic, move details into notes that a short line "
                   "points to, and remove what is outdated.")
    return status


def get_memory(user_id: int, vault: int = 0, family_mode: bool = False) -> Optional[dict]:
    """
    The memory note of a vault (with its version), or None if it has none yet; with family_mode
    without its hidden lines.
    """
    with db.connection() as conn:
        note = _find_note(conn, user_id, MEMORY_SLUG, vault=vault, family_mode=family_mode)
        if note is not None:
            note["version"] = _version(conn, note["id"])
            if family_mode:
                note["content"] = hidden_content.visible(note["content"])
    return note


def _change_memory(writer: Writer, change) -> tuple[dict, bool]:
    """
    Apply change(lines) -> new lines (or None for no change) to the memory, as one revision.

    Returns:
        (the memory note, whether it changed)
    """
    with db.connection() as conn:
        note = _find_note(conn, writer.user_id, MEMORY_SLUG, lock=True, vault=writer.vault)
        lines = note["content"].splitlines() if note else []
        new_lines = change(lines)
        if new_lines is None:
            if note is not None:
                note["version"] = _version(conn, note["id"])
            return note or {"slug": MEMORY_SLUG, "title": MEMORY_TITLE, "content": ""}, False
        content = _tidy(new_lines)
        _check_memory_size(content)
        if note is None:
            try:
                with conn.begin_nested():
                    note = dict(conn.execute(insert(kb_notes).values(
                        user_id=writer.user_id, vault=writer.vault, slug=MEMORY_SLUG, title=MEMORY_TITLE,
                        description=MEMORY_DESCRIPTION, tags=[], content=content,
                    ).returning(*_NOTE_COLUMNS)).one()._mapping)
            except IntegrityError:
                # Written at the same moment by a parallel tool call: change that one
                note = None
            if note is None:
                return _change_memory(writer, change)
            _add_revision(conn, note, "create", writer)
        else:
            note = dict(conn.execute(
                update(kb_notes).where(kb_notes.c.id == note["id"])
                .values(content=content, status="active").returning(*_NOTE_COLUMNS)
            ).one()._mapping)
            _add_revision(conn, note, "update", writer)
        _set_links(conn, note["id"], note["content"])
    log.info(f"Knowledge base {_vault_name(writer)}: changed the memory")
    return note, True


def memory_add(writer: Writer, text: str, section: Optional[str] = None,
               hidden_line: Optional[bool] = None) -> tuple[dict, bool]:
    """
    Add a line to the memory, with today's date at its end: under the heading section (made at the
    end if missing), else before the first heading.

    The line ends with #hidden if hidden_line, or (without it) if the text does or the writer writes from
    a hidden conversation; hidden_line False: an agent says it isn't hidden, even in a hidden conversation.

    Returns:
        (the memory, False if it has the same line already)

    Raises:
        KBError: Empty or too long text or section, or the memory would get too long.
    """
    text, tagged = _memory_text(text)
    tagged = hidden_line if hidden_line is not None else tagged or writer.from_hidden
    heading = " ".join((section or "").split()).lstrip("#").strip()
    if len(heading) > MEMORY_SECTION_CHARS:
        raise KBError(f"A section name has at most {MEMORY_SECTION_CHARS} characters")

    def change(lines: list[str]) -> Optional[list[str]]:
        if any(_line_key(line) == text.lower() for line in lines if _heading(line) is None):
            return None
        line = _memory_line(text, tagged)
        if heading:
            start = next((i for i, other in enumerate(lines) if (_heading(other) or "").lower() == heading.lower()),
                         None)
            if start is None:
                return lines + ["", f"## {heading}", line]
        else:
            start = -1
        # At the end of the section (or of the lines before the first heading)
        end = next((i for i in range(start + 1, len(lines)) if _heading(lines[i]) is not None), len(lines))
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        return lines[:end] + [line] + lines[end:]

    return _change_memory(writer, change)


def memory_replace(writer: Writer, line: str, text: str, hidden_line: Optional[bool] = None) -> dict:
    """
    Replace the one line of the memory that contains line (a part of it) with text, dated today. The
    new line keeps the tag #hidden of the old one, and gets it from a writer in a hidden conversation;
    hidden_line True or False decides it instead.

    Raises:
        KBError: No line or several lines contain it, empty or too long text, the memory would get too long.
    """
    text, tagged = _memory_text(text)

    def change(lines: list[str]) -> list[str]:
        index = _find_line(lines, line, writer.family_mode)
        keep = hidden_line if hidden_line is not None else tagged or writer.from_hidden or hidden_content.has_tag(lines[index])
        return lines[:index] + [_memory_line(text, keep)] + lines[index + 1:]

    return _change_memory(writer, change)[0]


def memory_remove(writer: Writer, line: str) -> tuple[dict, str]:
    """
    Remove the one line of the memory that contains line (a part of it); a heading left without
    lines goes too.

    Returns:
        (the memory, the removed line)

    Raises:
        KBError: No line or several lines contain it.
    """
    removed: list[str] = []

    def change(lines: list[str]) -> list[str]:
        index = _find_line(lines, line, writer.family_mode)
        removed.append(lines[index].strip())
        return lines[:index] + lines[index + 1:]

    note, _ = _change_memory(writer, change)
    return note, removed[0]
