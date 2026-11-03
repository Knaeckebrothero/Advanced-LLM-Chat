"""
The knowledge base: each user's Markdown notes, which the agent keeps across all of the user's
conversations with the kb_* tools (backend/services/tools/kb_tools.py). See docs/knowledge_base.md.

Postgres holds the only copy (kb_notes), so a note is readable right after it is written. A note's
slug is its stable id: it is made from the first title and stays when the title changes, and a
title whose slug exists already is refused rather than stored as a second note. Links to other
notes are [[slug]], [[Title]] (also with |alias or #heading) or Markdown links to slug.md; their
slugs go to kb_links, which gives the backlinks. Every write stores the new version in
kb_note_revisions, with who wrote it and in which conversation. Archiving hides a note from
lists and searches; an update restores it.

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
from typing import Iterable, Optional
from urllib.parse import unquote

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from backend.database import db
from backend.database.tables import kb_links, kb_note_revisions, kb_notes

log = logging.getLogger(__name__)

MAX_TITLE_CHARS = 200
MAX_DESCRIPTION_CHARS = 300
MAX_CONTENT_CHARS = 50_000
MAX_TAGS = 20
MAX_TAG_CHARS = 50
MAX_SLUG_CHARS = 80
# Notes longer than this get a hint to split them (agent notes are usually a few KB)
LONG_NOTE_CHARS = 15_000

# Query words: letters and digits (no underscores, which the full-text parser splits on)
_WORD_RE = re.compile(r"[^\W_]+")
# Query words from this length on also match as prefixes ("katze" finds "katzen")
_PREFIX_MIN_CHARS = 4
_MAX_QUERY_WORDS = 16
# [[target]], [[target|alias]], [[target#heading]]
_WIKILINK_RE = re.compile(r"\[\[([^\[\]|#]+)(?:#[^\[\]|]*)?(?:\|[^\[\]]*)?\]\]")
# [text](target) without a scheme: [text](other-note.md), [text](folder/Other%20Note.md#part)
_MD_LINK_RE = re.compile(r"\[[^\[\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_TRANSLITERATION = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "æ": "ae", "ø": "o", "œ": "oe"})

_NOTE_COLUMNS = (kb_notes.c.id, kb_notes.c.slug, kb_notes.c.title, kb_notes.c.description, kb_notes.c.tags,
                 kb_notes.c.content, kb_notes.c.status, kb_notes.c.created_at, kb_notes.c.updated_at)


class KBError(ValueError):
    """A request the knowledge base refuses; the message is meant for the model."""


@dataclass(frozen=True)
class Writer:
    """Who changes notes, for the revisions: the user whose knowledge base it is, and where."""

    user_id: int
    author: str = "agent"                   # 'agent' | 'user'
    conversation_id: Optional[str] = None
    persona_id: Optional[int] = None


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


def link_targets(content: str) -> list[str]:
    """
    The slugs a note's content links to, in order: [[target]] links and Markdown links without a
    scheme (to other notes, e.g. [text](other-note.md)). Web links and anchors are skipped.
    """
    targets = [match.group(1) for match in _WIKILINK_RE.finditer(content)]
    for match in _MD_LINK_RE.finditer(content):
        target = match.group(1)
        if ":" in target or target.startswith("#"):
            continue  # https://..., mailto:..., #heading
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
    if len(content) > MAX_CONTENT_CHARS:
        raise KBError(f"The note is longer than {MAX_CONTENT_CHARS} characters ({len(content)}); split it into "
                      f"several notes that link to each other")
    return content


# =========================================================================
# Reading
# =========================================================================

def _find_note(conn: Connection, user_id: int, ref: str, lock: bool = False) -> Optional[dict]:
    """A note by its slug, by the slug its title would get, or by its exact title (case-insensitive)."""
    ref = (ref or "").strip()
    if ref.startswith("[[") and ref.endswith("]]"):
        ref = ref[2:-2].split("|", 1)[0].strip()
    if not ref:
        return None
    slug = slugify(ref)
    query = (
        select(*_NOTE_COLUMNS)
        .where(kb_notes.c.user_id == user_id)
        .where((kb_notes.c.slug.in_([ref, slug])) | (func.lower(kb_notes.c.title) == ref.lower()))
        .order_by((kb_notes.c.slug == ref).desc(), (kb_notes.c.slug == slug).desc(), kb_notes.c.id)
        .limit(1)
    )
    if lock:
        query = query.with_for_update()
    row = conn.execute(query).first()
    return dict(row._mapping) if row else None


def _not_found(ref: str) -> KBError:
    return KBError(f"There is no note '{ref}'. Find the slug with kb_search or kb_list, or create the note with kb_write")


def get_note(user_id: int, ref: str) -> dict:
    """
    A note with its links: "links" (the notes it links to: slug, title or None if there is no such
    note, status) and "backlinks" (the active notes that link to it: slug, title).

    Raises:
        KBError: There is no such note.
    """
    with db.connection() as conn:
        note = _find_note(conn, user_id, ref)
        if note is None:
            raise _not_found(ref)
        targets = link_targets(note["content"])
        existing = {}
        if targets:
            rows = conn.execute(
                select(kb_notes.c.slug, kb_notes.c.title, kb_notes.c.status)
                .where(kb_notes.c.user_id == user_id, kb_notes.c.slug.in_(targets))
            )
            existing = {row.slug: row for row in rows}
        note["links"] = [
            {"slug": slug,
             "title": existing[slug].title if slug in existing else None,
             "status": existing[slug].status if slug in existing else None}
            for slug in targets if slug != note["slug"]
        ]
        note["backlinks"] = [
            dict(row._mapping) for row in conn.execute(
                select(kb_notes.c.slug, kb_notes.c.title)
                .select_from(kb_links.join(kb_notes, kb_links.c.note_id == kb_notes.c.id))
                .where(kb_notes.c.user_id == user_id, kb_notes.c.status == "active",
                       kb_links.c.target_slug == note["slug"], kb_notes.c.id != note["id"])
                .order_by(kb_notes.c.title)
            )
        ]
    return note


def list_notes(user_id: int, tag: Optional[str] = None, limit: int = 50) -> dict:
    """
    The active notes, most recently updated first.

    Returns:
        {"notes": [...] (without content), "total": the number of matching notes,
         "tags": [(tag, count)], the 20 most used tags (only without a tag filter)}
    """
    tag_filter = normalize_tags([tag])[0] if tag and tag.strip().lstrip("#").strip() else None
    conditions = [kb_notes.c.user_id == user_id, kb_notes.c.status == "active"]
    if tag_filter:
        conditions.append(kb_notes.c.tags.any(tag_filter))
    with db.connection() as conn:
        total = conn.execute(select(func.count()).select_from(kb_notes).where(*conditions)).scalar_one()
        notes = [
            dict(row._mapping) for row in conn.execute(
                select(kb_notes.c.slug, kb_notes.c.title, kb_notes.c.description, kb_notes.c.tags,
                       kb_notes.c.updated_at)
                .where(*conditions)
                .order_by(kb_notes.c.updated_at.desc().nulls_last(), kb_notes.c.id.desc())
                .limit(limit)
            )
        ]
        tags = []
        if not tag_filter:
            tags = [tuple(row) for row in conn.execute(text(
                "SELECT tag, count(*) AS n FROM kb_notes, unnest(tags) AS tag "
                "WHERE user_id = :user_id AND status = 'active' GROUP BY tag ORDER BY n DESC, tag LIMIT 20"
            ), {"user_id": user_id})]
    return {"notes": notes, "total": total, "tags": tags}


# Title words count most, then description and tags, then the content
_DOCUMENT = ("setweight(to_tsvector('simple', title), 'A') || "
             "setweight(to_tsvector('simple', coalesce(description, '') || ' ' || array_to_string(tags, ' ')), 'B') || "
             "setweight(to_tsvector('simple', content), 'D')")
_EXACT_FIELDS = ("slug", "title", "coalesce(description, '')", "array_to_string(tags, ' ')", "content")


def search_notes(user_id: int, query: Optional[str] = None, exact: Optional[Iterable[str]] = None,
                 tags: Optional[Iterable[str]] = None, limit: int = 10) -> list[dict]:
    """
    Search the active notes by words, exact text and tags.

    A note is found if it contains any query word, any exact text or any of the tags. The score is
    the full-text rank of the words, plus 1 per exact text it contains and 0.3 per tag it has; ties
    go to the more recently updated note.

    Args:
        query: Words to look for (any of them; more and rarer matches rank higher).
        exact: Literal texts, matched as case-insensitive substrings of slug, title, description,
            tags and content.
        tags: Tags; notes with them rank higher.

    Returns:
        The best notes, each with "matched" (the ways it matched: "words", "exact", "tags").

    Raises:
        KBError: Neither query words, exact texts nor tags.
    """
    words = _query_words(query or "")
    exact = [value.strip() for value in (exact or ()) if value and value.strip()]
    tags = normalize_tags(tags)
    if not (words or exact or tags):
        raise KBError("Give at least one of query (words), exact (a literal text) or tags")

    params: dict = {"user_id": user_id, "limit": limit}
    matches, scores, columns = [], [], []
    if words:
        params["tsquery"] = _tsquery(words)
        matches.append(f"({_DOCUMENT}) @@ to_tsquery('simple', :tsquery)")
        columns.append(f"ts_rank({_DOCUMENT}, to_tsquery('simple', :tsquery)) AS word_rank")
        scores.append("word_rank")
    if exact:
        hits = []
        for i, value in enumerate(exact[:10]):
            params[f"exact{i}"] = f"%{_escape_like(value)}%"
            hits.append("(CASE WHEN " + " OR ".join(f"{field} ILIKE :exact{i}" for field in _EXACT_FIELDS)
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
            SELECT slug, title, description, tags, content, updated_at, {', '.join(columns)}
            FROM kb_notes
            WHERE user_id = :user_id AND status = 'active' AND ({' OR '.join(matches)})
        ) AS hits
        ORDER BY {' + '.join(scores)} DESC, updated_at DESC NULLS LAST
        LIMIT :limit
    """
    with db.connection() as conn:
        rows = [dict(row._mapping) for row in conn.execute(text(sql), params)]

    for row in rows:
        row["matched"] = [name for name, key in (("words", "word_rank"), ("exact", "exact_hits"), ("tags", "tag_hits"))
                          if row.get(key)]
        row["snippet"] = _snippet(row.pop("content"), exact + words)
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
    conn.execute(insert(kb_note_revisions).values(
        note_id=note["id"], action=action, title=note["title"], description=note["description"],
        tags=note["tags"], content=note["content"], status=note["status"], author=writer.author,
        conversation_id=writer.conversation_id, persona_id=writer.persona_id, reason=reason,
    ))


def _set_links(conn: Connection, note_id: int, content: str) -> None:
    conn.execute(delete(kb_links).where(kb_links.c.note_id == note_id))
    targets = link_targets(content)
    if targets:
        conn.execute(pg_insert(kb_links).values([{"note_id": note_id, "target_slug": slug} for slug in targets])
                     .on_conflict_do_nothing())


def create_note(writer: Writer, title: str, content: str, description: Optional[str] = None,
                tags: Optional[Iterable[str]] = None) -> dict:
    """
    Create a note; its slug is made from the title.

    Raises:
        KBError: Invalid fields, or a note with that slug exists already (also an archived one).
    """
    title = _clean_title(title)
    values = {
        "user_id": writer.user_id, "slug": note_slug(title), "title": title,
        "description": _clean_description(description), "tags": normalize_tags(tags),
        "content": _clean_content(content, title),
    }
    try:
        with db.connection() as conn:
            existing = _find_note(conn, writer.user_id, values["slug"])
            if existing is not None and existing["slug"] == values["slug"]:
                raise _exists(existing)
            note = dict(conn.execute(insert(kb_notes).values(**values).returning(*_NOTE_COLUMNS)).one()._mapping)
            _add_revision(conn, note, "create", writer)
            _set_links(conn, note["id"], note["content"])
    except IntegrityError:
        # The same slug, written at the same moment by a parallel tool call
        with db.connection() as conn:
            existing = _find_note(conn, writer.user_id, values["slug"])
        if existing is None:
            raise
        raise _exists(existing)
    log.info(f"Knowledge base of user {writer.user_id}: created note {note['slug']}")
    return note


def _exists(note: dict) -> KBError:
    archived = " (archived)" if note["status"] == "archived" else ""
    return KBError(f"A note with the slug '{note['slug']}' exists already{archived}: \"{note['title']}\". "
                   f"Change it with kb_update (this also restores an archived note), or choose a different title")


def update_note(writer: Writer, ref: str, content: Optional[str] = None, append: Optional[str] = None,
                title: Optional[str] = None, description: Optional[str] = None,
                tags: Optional[Iterable[str]] = None) -> tuple[dict, list[str]]:
    """
    Change a note; its slug stays. Updating an archived note restores it.

    Args:
        content: Replaces the whole content.
        append: Added at the end of the content (not together with content).
        title, description: Replace them ("" removes the description).
        tags: Replaces the list of tags ([] removes them).

    Returns:
        (the note, what changed; [] if the values were the same already)

    Raises:
        KBError: No such note, nothing to change, content and append together, invalid fields.
    """
    if content is not None and append is not None:
        raise KBError("Give either content (replaces the whole text) or append (adds to the end), not both")
    if all(value is None for value in (content, append, title, description, tags)):
        raise KBError("Nothing to change: give content, append, title, description or tags")

    with db.connection() as conn:
        note = _find_note(conn, writer.user_id, ref, lock=True)
        if note is None:
            raise _not_found(ref)
        new = dict(note)
        changes = []
        if title is not None:
            new["title"] = _clean_title(title)
        if content is not None:
            new["content"] = _clean_content(content, new["title"])
        if append is not None:
            addition = append.strip()
            if not addition:
                raise KBError("append must not be empty")
            new["content"] = _clean_content(f"{note['content'].rstrip()}\n\n{addition}", new["title"])
        if description is not None:
            new["description"] = _clean_description(description)
        if tags is not None:
            new["tags"] = normalize_tags(tags)

        if new["title"] != note["title"]:
            changes.append(f"title → \"{new['title']}\"")
        if new["content"] != note["content"]:
            changes.append(f"appended {len(append.strip())} characters" if append is not None else "content replaced")
        if new["description"] != note["description"]:
            changes.append("description changed" if new["description"] else "description removed")
        if new["tags"] != note["tags"]:
            changes.append(f"tags → [{', '.join(new['tags'])}]")
        if note["status"] == "archived":
            new["status"] = "active"
            changes.append("restored from the archive")
        if not changes:
            return note, []

        content_changed = new["content"] != note["content"]
        note = dict(conn.execute(
            update(kb_notes).where(kb_notes.c.id == note["id"])
            .values(title=new["title"], description=new["description"], tags=new["tags"],
                    content=new["content"], status=new["status"])
            .returning(*_NOTE_COLUMNS)
        ).one()._mapping)
        _add_revision(conn, note, "update", writer)
        if content_changed:
            _set_links(conn, note["id"], note["content"])
    log.info(f"Knowledge base of user {writer.user_id}: updated note {note['slug']} ({', '.join(changes)})")
    return note, changes


def archive_note(writer: Writer, ref: str, reason: Optional[str] = None) -> tuple[dict, bool]:
    """
    Archive a note: lists and searches skip it, reading it still works, an update restores it.

    Returns:
        (the note, False if it was archived already)

    Raises:
        KBError: There is no such note.
    """
    with db.connection() as conn:
        note = _find_note(conn, writer.user_id, ref, lock=True)
        if note is None:
            raise _not_found(ref)
        if note["status"] == "archived":
            return note, False
        note = dict(conn.execute(
            update(kb_notes).where(kb_notes.c.id == note["id"]).values(status="archived").returning(*_NOTE_COLUMNS)
        ).one()._mapping)
        _add_revision(conn, note, "archive", writer, reason=" ".join((reason or "").split()) or None)
    log.info(f"Knowledge base of user {writer.user_id}: archived note {note['slug']}")
    return note, True
