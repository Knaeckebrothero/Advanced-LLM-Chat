"""
Knowledge base API endpoints: the Knowledge base page, where a signed-in user browses, searches,
edits and exports the notes their agents keep (backend/services/knowledge_base.py,
docs/knowledge_base.md). Guests have no knowledge base.

Every endpoint works on one knowledge base, the query parameter vault: 0 (the default) for the
user's shared one, else the id of an agent with its own (GET /vaults lists them). The memory of a
knowledge base is its note "memory": GET /memory reads it, PUT /notes/memory edits it like any note;
lists and searches leave it out.

Edits made here are revisions with author "user". An edit or a restored version sends the version
it was made on (baseVersion) and gets 409 with code "conflict" if the note changed since, e.g.
because an agent wrote to it meanwhile. Deleting a note for good is only possible here; the agent
can only archive. The export is a zip that opens as an Obsidian vault. POST /review runs the memory
review of a conversation now (backend/services/memory_review.py).

A device in family mode (the header X-Family-Mode) gets every answer without
hidden notes, the tagged lines and the own knowledge bases of hidden agents, as if they didn't exist; a
save from it keeps the lines it didn't see.

Errors carry {"code", "message"} as detail: not_found (404), exists (409, with the existing
note's slug and status), conflict (409, with the note's version now) and invalid (400).
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from backend.catalog.resolver import persona_usable
from backend.database import db
from backend.models.knowledge_base import (
    KBArchiveRequest,
    KBCounts,
    KBLink,
    KBMemory,
    KBNote,
    KBNoteList,
    KBNoteSummary,
    KBNoteUpdate,
    KBNoteWrite,
    KBRestoreRevisionRequest,
    KBReviewChange,
    KBReviewRequest,
    KBReviewResult,
    KBRevision,
    KBRevisionSummary,
    KBSearchHit,
    KBTagCount,
    KBVault,
    NoteStatus,
)
from backend.security.auth import get_current_user, verify_conversation_ownership
from backend.security.logging import crud_logger
from backend.services import knowledge_base as kb
from backend.services import knowledge_base_export, memory_review
from backend.services.knowledge_base import KBConflict, KBError, KBExists, KBNotFound, Writer
from backend.services.hidden_content import family_mode, hidden_conversations

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


def _own_memory_agent(persona: Optional[dict], user: dict) -> bool:
    """The persona has its own knowledge base for the user: own_memory, the knowledge base, usable."""
    return bool(persona and persona.get("own_memory") and "knowledge_base" in (persona.get("tools") or [])
                and persona_usable(persona, user))


def _vaults(user: dict, hide: bool = False) -> List[KBVault]:
    """
    The user's knowledge bases: the shared one first, then those of the agents with their own one
    that the user may use, and those of other agents that still have notes (by name). With hide,
    not those of hidden agents.
    """
    stored = {row["vault"]: row for row in kb.list_vaults(user["user_id"], family_mode=hide)}
    shared = stored.get(0, {})
    vaults = [KBVault(id=0, active=shared.get("active", 0), archived=shared.get("archived", 0),
                      memoryLines=shared.get("memory_lines", 0))]
    personas = {persona["id"]: persona for persona in db.get_personas()}
    ids = {persona_id for persona_id, persona in personas.items() if _own_memory_agent(persona, user)}
    ids |= {vault for vault in stored if vault != 0}
    if hide:
        ids = {vault for vault in ids if not (personas.get(vault) or {}).get("hidden")}
    agents = []
    for vault in ids:
        persona = personas.get(vault)
        row = stored.get(vault, {})
        agents.append(KBVault(id=vault, personaId=vault, personaName=persona["name"] if persona else None,
                              available=_own_memory_agent(persona, user), active=row.get("active", 0),
                              archived=row.get("archived", 0), memoryLines=row.get("memory_lines", 0)))
    agents.sort(key=lambda item: ((item.personaName or "").lower(), item.id))
    return vaults + agents


def _vault(vault: int = Query(0, ge=0, description="0: the shared knowledge base, else an agent's own"),
           user: dict = Depends(require_member), hide: bool = Depends(family_mode)) -> int:
    """The vault of a request; 404 if the user has no such knowledge base (or it is hidden)."""
    if vault != 0 and vault not in {item.id for item in _vaults(user, hide)}:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": f"There is no knowledge base {vault}"})
    return vault


def _writer(user: dict, vault: int = 0, hide: bool = False) -> Writer:
    return Writer(user_id=user["user_id"], author="user", vault=vault, family_mode=hide)


def _revision_summaries(user_id: int, rows: list[dict], hide: bool) -> List[KBRevisionSummary]:
    """The versions of a note; with hide, a version written in a hidden chat doesn't name it."""
    hidden = hidden_conversations(user_id) if hide else set()
    summaries = [KBRevisionSummary.from_row(row) for row in rows]
    for summary in summaries:
        if summary.conversationId in hidden:
            summary.conversationId = summary.conversationName = None
    return summaries


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


def _note(user_id: int, slug: str, vault: int = 0, hide: bool = False) -> KBNote:
    """A note in full, with its links and versions; in family mode without what is hidden."""
    note = kb.get_note(user_id, slug, vault=vault, family_mode=hide)
    revisions = kb.list_revisions(user_id, note["slug"], vault=vault, family_mode=hide)
    return KBNote(
        slug=note["slug"], title=note["title"], description=note["description"], tags=note["tags"] or [],
        status=note["status"], content=note["content"], createdAt=note["created_at"],
        updatedAt=note["updated_at"], version=note["version"], hidden=bool(note["hidden"]), hiddenBy=note.get("hidden_by"),
        links=[KBLink(**link) for link in note["links"]],
        backlinks=[KBLink(slug=link["slug"], title=link["title"], status="active") for link in note["backlinks"]],
        revisions=_revision_summaries(user_id, revisions, hide),
    )


def _written(user_id: int, note: dict, vault: int, hide: bool) -> KBNote:
    """
    A note just written from the page. One the user hidden on a device that hides it comes
    back once in full (with hidden true), so the page can tell it is hidden from now on.
    """
    return _note(user_id, note["slug"], vault, hide and not note["hidden"])


# The endpoints are plain functions: FastAPI runs them in a worker thread, as the store blocks

@router.get("/notes", response_model=KBNoteList)
def list_notes(status_: NoteStatus = Query("active", alias="status"), tag: Optional[str] = None,
               limit: int = Query(MAX_LIST, ge=1, le=MAX_LIST), vault: int = Depends(_vault),
               user: dict = Depends(require_member), hide: bool = Depends(family_mode)):
    """The notes with a status, most recently updated first, with the tags in use and the counts (without the memory)."""
    try:
        result = kb.list_notes(user["user_id"], tag=tag, limit=limit, status=status_, vault=vault, family_mode=hide)
    except KBError as e:
        raise _error(e)
    return KBNoteList(
        notes=[KBNoteSummary.from_row(row) for row in result["notes"]],
        total=result["total"],
        tags=[KBTagCount(tag=name, count=count) for name, count in result["tags"]],
        counts=KBCounts(**kb.count_notes(user["user_id"], vault, family_mode=hide)),
    )


@router.get("/vaults", response_model=List[KBVault])
def list_vaults(user: dict = Depends(require_member), hide: bool = Depends(family_mode)):
    """The user's knowledge bases: the shared one and the agents' own ones, with their counts."""
    return _vaults(user, hide)


@router.get("/memory", response_model=KBMemory)
def get_memory(vault: int = Depends(_vault), user: dict = Depends(require_member), hide: bool = Depends(family_mode)):
    """
    The memory of a knowledge base and how full it is (all of it, also the lines that are hidden);
    note is null while it is empty.
    """
    memory = kb.get_memory(user["user_id"], vault)
    if memory is None:
        return KBMemory()
    lines, chars = kb.memory_usage(memory["content"])
    return KBMemory(note=_note(user["user_id"], kb.MEMORY_SLUG, vault, hide), lines=lines, chars=chars)


@router.post("/review", response_model=KBReviewResult)
async def review_conversation(body: KBReviewRequest, user: dict = Depends(require_member)):
    """
    Review a conversation for the memory now (as the memory review does once it is quiet): its
    model saves what matters from the messages since the last review. Waits for a running review.
    """
    if not verify_conversation_ownership(body.conversationId, user["user_id"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            detail={"code": "not_found", "message": "There is no such conversation"})
    result = await memory_review.review_conversation(body.conversationId)
    crud_logger.info(f"Memory review of conversation {body.conversationId} requested by user {user['user_id']}: "
                     f"{result.status}, {len(result.changes)} change(s)")
    return KBReviewResult(status=result.status, detail=result.detail, modelName=result.model_name,
                          changes=[KBReviewChange(**change) for change in result.changes],
                          reviewedUntil=result.reviewed_until)


@router.get("/search", response_model=List[KBSearchHit])
def search_notes(q: str = Query(..., min_length=1, max_length=500), status_: NoteStatus = Query("active", alias="status"),
                 limit: int = Query(50, ge=1, le=MAX_SEARCH), vault: int = Depends(_vault),
                 user: dict = Depends(require_member), hide: bool = Depends(family_mode)):
    """
    Search the notes with a status by the words of q (as the agent does: any word, longer ones also
    as prefixes) and, from three characters on, q as a literal part of a note.
    """
    text = q.strip()
    try:
        hits = kb.search_notes(user["user_id"], query=text, exact=[text] if len(text) >= MIN_EXACT_CHARS else None,
                               limit=limit, status=status_, vault=vault, family_mode=hide)
    except KBError:
        return []  # Nothing to search for (e.g. only punctuation)
    return [KBSearchHit(**KBNoteSummary.from_row(hit).model_dump(), snippet=hit["snippet"], matched=hit["matched"])
            for hit in hits]


@router.get("/export")
def export_notes(tz: Optional[str] = Query(None, max_length=64), vault: int = Depends(_vault),
                 user: dict = Depends(require_member), hide: bool = Depends(family_mode)):
    """
    All notes of a knowledge base (and its memory) as a zip that opens as an Obsidian vault
    (knowledge_base_export), with the times in the time zone tz (the browser's, e.g. Europe/Berlin;
    UTC without one or for an unknown one).
    """
    zone = knowledge_base_export.time_zone(tz)
    content, count = knowledge_base_export.export_vault(user["user_id"], zone, vault, family_mode=hide)
    agent = None
    if vault:
        agent = next((item.personaName or "" for item in _vaults(user, hide) if item.id == vault), "")
    name = knowledge_base_export.file_name(zone, agent)
    crud_logger.info(f"Knowledge base exported by user {user['user_id']} ({count} notes)")
    return Response(content=content, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/notes/{slug}", response_model=KBNote)
def get_note(slug: str, vault: int = Depends(_vault), user: dict = Depends(require_member),
             hide: bool = Depends(family_mode)):
    try:
        return _note(user["user_id"], slug, vault, hide)
    except KBError as e:
        raise _error(e)


@router.post("/notes", response_model=KBNote, status_code=status.HTTP_201_CREATED)
def create_note(body: KBNoteWrite, vault: int = Depends(_vault), user: dict = Depends(require_member),
                hide: bool = Depends(family_mode)):
    """A new note; its slug is made from the title. 409 "exists" if a note has that slug already."""
    try:
        note = kb.create_note(_writer(user, vault, hide), body.title, body.content, description=body.description,
                              tags=body.tags, hidden_note=bool(body.hidden))
        crud_logger.info(f"Note {note['slug']} created by user {user['user_id']} (vault {vault})")
        return _written(user["user_id"], note, vault, hide)
    except KBError as e:
        raise _error(e)


@router.put("/notes/{slug}", response_model=KBNote)
def update_note(slug: str, body: KBNoteUpdate, vault: int = Depends(_vault), user: dict = Depends(require_member),
                hide: bool = Depends(family_mode)):
    """
    Replace a note's title, description, tags and content (the slug stays), and its hidden mark if
    sent. An archived note is restored. 409 "conflict" if it changed since baseVersion. From a
    device that is in family mode, the lines it didn't see are kept.
    """
    try:
        note, changes = kb.update_note(_writer(user, vault, hide), slug, content=body.content, title=body.title,
                                       description=body.description or "", tags=body.tags,
                                       base_version=body.baseVersion, hidden_note=body.hidden)
        if changes:
            crud_logger.info(f"Note {note['slug']} changed by user {user['user_id']} (vault {vault})")
        return _written(user["user_id"], note, vault, hide)
    except KBError as e:
        raise _error(e)


@router.post("/notes/{slug}/archive", response_model=KBNote)
def archive_note(slug: str, body: Optional[KBArchiveRequest] = None, vault: int = Depends(_vault),
                 user: dict = Depends(require_member), hide: bool = Depends(family_mode)):
    """Hide a note from the lists and searches (also the agent's); nothing is deleted. Not the memory."""
    try:
        note, _ = kb.archive_note(_writer(user, vault, hide), slug, reason=body.reason if body else None)
        return _note(user["user_id"], note["slug"], vault, hide)
    except KBError as e:
        raise _error(e)


@router.post("/notes/{slug}/restore", response_model=KBNote)
def restore_note(slug: str, vault: int = Depends(_vault), user: dict = Depends(require_member),
                 hide: bool = Depends(family_mode)):
    """Bring an archived note back, unchanged."""
    try:
        note, _ = kb.restore_note(_writer(user, vault, hide), slug)
        return _note(user["user_id"], note["slug"], vault, hide)
    except KBError as e:
        raise _error(e)


@router.delete("/notes/{slug}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(slug: str, vault: int = Depends(_vault), user: dict = Depends(require_member),
                hide: bool = Depends(family_mode)):
    """Delete a note for good, with all its versions (the memory too: it starts empty again)."""
    try:
        deleted = kb.delete_note(user["user_id"], slug, vault, family_mode=hide)
    except KBError as e:
        raise _error(e)
    crud_logger.info(f"Note {deleted} deleted for good by user {user['user_id']} (vault {vault})")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/notes/{slug}/revisions/{revision_id}", response_model=KBRevision)
def get_revision(slug: str, revision_id: int, vault: int = Depends(_vault), user: dict = Depends(require_member),
                 hide: bool = Depends(family_mode)):
    """One version of a note, with its content."""
    try:
        revision = KBRevision.from_row(kb.get_revision(user["user_id"], slug, revision_id, vault, family_mode=hide))
        if hide and revision.conversationId in hidden_conversations(user["user_id"]):
            revision.conversationId = revision.conversationName = None
        return revision
    except KBError as e:
        raise _error(e)


@router.post("/notes/{slug}/revisions/{revision_id}/restore", response_model=KBNote)
def restore_revision(slug: str, revision_id: int, body: Optional[KBRestoreRevisionRequest] = None,
                     vault: int = Depends(_vault), user: dict = Depends(require_member),
                     hide: bool = Depends(family_mode)):
    """Make an earlier version the current one, as a new version. 409 "conflict" if it changed since baseVersion."""
    try:
        note, changes = kb.restore_revision(_writer(user, vault, hide), slug, revision_id,
                                            base_version=body.baseVersion if body else None)
        if changes:
            crud_logger.info(f"Note {note['slug']}: version {revision_id} restored by user {user['user_id']}")
        return _note(user["user_id"], note["slug"], vault, hide)
    except KBError as e:
        raise _error(e)
