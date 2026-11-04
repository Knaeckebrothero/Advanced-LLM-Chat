"""
Knowledge base API endpoints: the Knowledge base page, where a signed-in user browses, searches,
edits and exports the notes their agents keep (backend/services/knowledge_base.py,
docs/knowledge_base.md). Guests have no knowledge base.

Edits made here are revisions with author "user". An edit or a restored version sends the version
it was made on (baseVersion) and gets 409 with code "conflict" if the note changed since, e.g.
because an agent wrote to it meanwhile. Deleting a note for good is only possible here; the agent
can only archive. The export is a zip that opens as an Obsidian vault.

Errors carry {"code", "message"} as detail: not_found (404), exists (409, with the existing
note's slug and status), conflict (409, with the note's version now) and invalid (400).
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from backend.models.knowledge_base import (
    KBArchiveRequest,
    KBCounts,
    KBLink,
    KBNote,
    KBNoteList,
    KBNoteSummary,
    KBNoteUpdate,
    KBNoteWrite,
    KBRestoreRevisionRequest,
    KBRevision,
    KBRevisionSummary,
    KBSearchHit,
    KBTagCount,
    NoteStatus,
)
from backend.security.auth import get_current_user
from backend.security.logging import crud_logger
from backend.services import knowledge_base as kb
from backend.services import knowledge_base_export
from backend.services.knowledge_base import KBConflict, KBError, KBExists, KBNotFound, Writer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/kb", tags=["Knowledge base"])

MAX_LIST = 2000
MAX_SEARCH = 100
# Search terms from this length on also match as a literal part of a note (like Obsidian's search)
MIN_EXACT_CHARS = 3


async def require_member(current_user: dict = Depends(get_current_user)) -> dict:
    """A signed-in user: guests have no knowledge base (their data ends with their session)."""
    if current_user.get("is_guest"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail={"code": "guest", "message": "Guests have no knowledge base"})
    return current_user


def _writer(user: dict) -> Writer:
    return Writer(user_id=user["user_id"], author="user")


def _error(error: KBError) -> HTTPException:
    """The HTTP error for a request the knowledge base refuses."""
    if isinstance(error, KBNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": str(error)})
    if isinstance(error, KBExists):
        return HTTPException(status.HTTP_409_CONFLICT, detail={
            "code": "exists", "message": str(error), "slug": error.note["slug"], "status": error.note["status"]})
    if isinstance(error, KBConflict):
        return HTTPException(status.HTTP_409_CONFLICT,
                             detail={"code": "conflict", "message": str(error), "version": error.version})
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "invalid", "message": str(error)})


def _note(user_id: int, slug: str) -> KBNote:
    """A note in full, with its links and versions."""
    note = kb.get_note(user_id, slug)
    revisions = kb.list_revisions(user_id, note["slug"])
    return KBNote(
        slug=note["slug"], title=note["title"], description=note["description"], tags=note["tags"] or [],
        status=note["status"], content=note["content"], createdAt=note["created_at"],
        updatedAt=note["updated_at"], version=note["version"],
        links=[KBLink(**link) for link in note["links"]],
        backlinks=[KBLink(slug=link["slug"], title=link["title"], status="active") for link in note["backlinks"]],
        revisions=[KBRevisionSummary.from_row(row) for row in revisions],
    )


# The endpoints are plain functions: FastAPI runs them in a worker thread, as the store blocks

@router.get("/notes", response_model=KBNoteList)
def list_notes(status_: NoteStatus = Query("active", alias="status"), tag: Optional[str] = None,
               limit: int = Query(MAX_LIST, ge=1, le=MAX_LIST), user: dict = Depends(require_member)):
    """The notes with a status, most recently updated first, with the tags in use and the counts."""
    try:
        result = kb.list_notes(user["user_id"], tag=tag, limit=limit, status=status_)
    except KBError as e:
        raise _error(e)
    return KBNoteList(
        notes=[KBNoteSummary.from_row(row) for row in result["notes"]],
        total=result["total"],
        tags=[KBTagCount(tag=name, count=count) for name, count in result["tags"]],
        counts=KBCounts(**kb.count_notes(user["user_id"])),
    )


@router.get("/search", response_model=List[KBSearchHit])
def search_notes(q: str = Query(..., min_length=1, max_length=500), status_: NoteStatus = Query("active", alias="status"),
                 limit: int = Query(50, ge=1, le=MAX_SEARCH), user: dict = Depends(require_member)):
    """
    Search the notes with a status by the words of q (as the agent does: any word, longer ones also
    as prefixes) and, from three characters on, q as a literal part of a note.
    """
    text = q.strip()
    try:
        hits = kb.search_notes(user["user_id"], query=text, exact=[text] if len(text) >= MIN_EXACT_CHARS else None,
                               limit=limit, status=status_)
    except KBError:
        return []  # Nothing to search for (e.g. only punctuation)
    return [KBSearchHit(**KBNoteSummary.from_row(hit).model_dump(), snippet=hit["snippet"], matched=hit["matched"])
            for hit in hits]


@router.get("/export")
def export_notes(tz: Optional[str] = Query(None, max_length=64), user: dict = Depends(require_member)):
    """
    All notes as a zip that opens as an Obsidian vault (knowledge_base_export), with the times in
    the time zone tz (the browser's, e.g. Europe/Berlin; UTC without one or for an unknown one).
    """
    zone = knowledge_base_export.time_zone(tz)
    content, count = knowledge_base_export.export_vault(user["user_id"], zone)
    name = knowledge_base_export.file_name(zone)
    crud_logger.info(f"Knowledge base exported by user {user['user_id']} ({count} notes)")
    return Response(content=content, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/notes/{slug}", response_model=KBNote)
def get_note(slug: str, user: dict = Depends(require_member)):
    try:
        return _note(user["user_id"], slug)
    except KBError as e:
        raise _error(e)


@router.post("/notes", response_model=KBNote, status_code=status.HTTP_201_CREATED)
def create_note(body: KBNoteWrite, user: dict = Depends(require_member)):
    """A new note; its slug is made from the title. 409 "exists" if a note has that slug already."""
    try:
        note = kb.create_note(_writer(user), body.title, body.content, description=body.description, tags=body.tags)
        crud_logger.info(f"Note {note['slug']} created by user {user['user_id']}")
        return _note(user["user_id"], note["slug"])
    except KBError as e:
        raise _error(e)


@router.put("/notes/{slug}", response_model=KBNote)
def update_note(slug: str, body: KBNoteUpdate, user: dict = Depends(require_member)):
    """
    Replace a note's title, description, tags and content (the slug stays). An archived note is
    restored. 409 "conflict" if it changed since baseVersion.
    """
    try:
        note, changes = kb.update_note(_writer(user), slug, content=body.content, title=body.title,
                                       description=body.description or "", tags=body.tags,
                                       base_version=body.baseVersion)
        if changes:
            crud_logger.info(f"Note {note['slug']} changed by user {user['user_id']}")
        return _note(user["user_id"], note["slug"])
    except KBError as e:
        raise _error(e)


@router.post("/notes/{slug}/archive", response_model=KBNote)
def archive_note(slug: str, body: Optional[KBArchiveRequest] = None, user: dict = Depends(require_member)):
    """Hide a note from the lists and searches (also the agent's); nothing is deleted."""
    try:
        note, _ = kb.archive_note(_writer(user), slug, reason=body.reason if body else None)
        return _note(user["user_id"], note["slug"])
    except KBError as e:
        raise _error(e)


@router.post("/notes/{slug}/restore", response_model=KBNote)
def restore_note(slug: str, user: dict = Depends(require_member)):
    """Bring an archived note back, unchanged."""
    try:
        note, _ = kb.restore_note(_writer(user), slug)
        return _note(user["user_id"], note["slug"])
    except KBError as e:
        raise _error(e)


@router.delete("/notes/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(slug: str, user: dict = Depends(require_member)):
    """Delete a note for good, with all its versions."""
    try:
        deleted = kb.delete_note(user["user_id"], slug)
    except KBError as e:
        raise _error(e)
    crud_logger.info(f"Note {deleted} deleted for good by user {user['user_id']}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/notes/{slug}/revisions/{revision_id}", response_model=KBRevision)
def get_revision(slug: str, revision_id: int, user: dict = Depends(require_member)):
    """One version of a note, with its content."""
    try:
        return KBRevision.from_row(kb.get_revision(user["user_id"], slug, revision_id))
    except KBError as e:
        raise _error(e)


@router.post("/notes/{slug}/revisions/{revision_id}/restore", response_model=KBNote)
def restore_revision(slug: str, revision_id: int, body: Optional[KBRestoreRevisionRequest] = None,
                     user: dict = Depends(require_member)):
    """Make an earlier version the current one, as a new version. 409 "conflict" if it changed since baseVersion."""
    try:
        note, changes = kb.restore_revision(_writer(user), slug, revision_id,
                                            base_version=body.baseVersion if body else None)
        if changes:
            crud_logger.info(f"Note {note['slug']}: version {revision_id} restored by user {user['user_id']}")
        return _note(user["user_id"], note["slug"])
    except KBError as e:
        raise _error(e)
