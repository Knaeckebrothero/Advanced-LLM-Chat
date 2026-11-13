"""
Knowledge base API models (the Knowledge base page, backend/api/knowledge_base.py).

A note's slug is its id in every path, within a vault (the query parameter vault: 0 for the
user's shared knowledge base, else the id of an agent with its own). "version" is the id of its
newest revision: an edit sends the version it was made on (baseVersion) and is refused with 409 if
the note changed since. Times are sent as UTC with a Z (UtcDatetime).
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from backend.models.common import UtcDatetime
from backend.services.knowledge_base import (MAX_DESCRIPTION_CHARS, MAX_TAGS, MAX_TITLE_CHARS, MEMORY_MAX_CHARS,
                                             MEMORY_MAX_LINES)

NoteStatus = Literal["active", "archived"]


class KBNoteSummary(BaseModel):
    """A note in the list, without its content."""
    slug: str
    title: str
    description: Optional[str] = None
    tags: List[str] = []
    status: NoteStatus
    updatedAt: Optional[UtcDatetime] = None
    hidden: bool = False  # Hidden
    hiddenBy: Optional[str] = None  # Who set hidden: "user" or "agent" (agents leave the user's decision alone)

    @classmethod
    def from_row(cls, row: dict) -> "KBNoteSummary":
        return cls(slug=row["slug"], title=row["title"], description=row["description"], tags=row["tags"] or [],
                   status=row["status"], updatedAt=row["updated_at"], hidden=bool(row.get("hidden")),
                   hiddenBy=row.get("hidden_by"))


class KBTagCount(BaseModel):
    tag: str
    count: int


class KBCounts(BaseModel):
    active: int = 0
    archived: int = 0


class KBNoteList(BaseModel):
    notes: List[KBNoteSummary]
    total: int  # Notes with the status (and tag); more than `notes` if the list was cut
    tags: List[KBTagCount]  # The 20 most used tags of the notes with the status
    counts: KBCounts  # All of the user's notes per status


class KBSearchHit(KBNoteSummary):
    snippet: str  # The passage around the match
    matched: List[str]  # "words", "exact", "tags"


class KBLink(BaseModel):
    slug: str
    title: Optional[str] = None  # None: there is no such note (yet)
    status: Optional[NoteStatus] = None


class KBRevisionSummary(BaseModel):
    """One version of a note, without its content."""
    id: int
    action: str  # 'create' | 'update' | 'archive' | 'restore'
    title: str
    status: NoteStatus
    author: str  # 'agent' | 'review' (the memory review) | 'dream' (the nightly consolidation) | 'user'
    conversationId: Optional[str] = None
    conversationName: Optional[str] = None  # None: no conversation, or it was deleted
    personaId: Optional[int] = None
    personaName: Optional[str] = None
    reason: Optional[str] = None
    createdAt: Optional[UtcDatetime] = None

    @classmethod
    def from_row(cls, row: dict) -> "KBRevisionSummary":
        return cls(id=row["id"], action=row["action"], title=row["title"], status=row["status"],
                   author=row["author"], conversationId=row["conversation_id"],
                   conversationName=row["conversation_name"], personaId=row["persona_id"],
                   personaName=row["persona_name"], reason=row["reason"], createdAt=row["created_at"])


class KBRevision(KBRevisionSummary):
    description: Optional[str] = None
    tags: List[str] = []
    content: str

    @classmethod
    def from_row(cls, row: dict) -> "KBRevision":
        summary = KBRevisionSummary.from_row(row)
        return cls(**summary.model_dump(), description=row["description"], tags=row["tags"] or [],
                   content=row["content"])


class KBNote(KBNoteSummary):
    """A note in full, with its links and versions."""
    content: str
    createdAt: Optional[UtcDatetime] = None
    version: int
    links: List[KBLink] = []  # The notes it links to, also ones that don't exist
    backlinks: List[KBLink] = []  # The active notes that link to it
    revisions: List[KBRevisionSummary] = []  # Newest first


class KBNoteWrite(BaseModel):
    """A new note, or all fields of an edited one (the slug stays when the title changes)."""
    title: str = Field(max_length=MAX_TITLE_CHARS)
    content: str
    description: Optional[str] = Field(None, max_length=MAX_DESCRIPTION_CHARS)
    tags: List[str] = Field(default_factory=list, max_length=MAX_TAGS)
    hidden: Optional[bool] = None  # Hide the note or not; None keeps it


class KBNoteUpdate(KBNoteWrite):
    baseVersion: Optional[int] = None  # The version the edit was made on; None skips the check


class KBArchiveRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


class KBRestoreRevisionRequest(BaseModel):
    baseVersion: Optional[int] = None


class KBVault(BaseModel):
    """A knowledge base of the user: the shared one (id 0) or an agent's own one."""
    id: int
    personaId: Optional[int] = None  # The agent whose own knowledge base it is; None for the shared one
    personaName: Optional[str] = None  # None for the shared one, or if the agent was deleted
    available: bool = True  # The agent exists, has own_memory and the knowledge base, and the user may use it
    active: int = 0
    archived: int = 0
    memoryLines: int = 0


class KBMemory(BaseModel):
    """The memory of a vault (its note "memory") with how full it is; note None while it is empty."""
    note: Optional["KBNote"] = None
    lines: int = 0
    chars: int = 0
    maxLines: int = MEMORY_MAX_LINES
    maxChars: int = MEMORY_MAX_CHARS


class KBReviewRequest(BaseModel):
    conversationId: str


class KBReviewChange(BaseModel):
    tool: str  # kb_write, kb_update, kb_archive, memory_add, memory_replace, memory_remove
    title: str
    content: str
    note: Optional[str] = None  # The note's slug ("memory" for the memory)
    vault: int = 0


class KBReviewResult(BaseModel):
    """What a memory review on request did."""
    status: Literal["done", "nothing_new", "not_available", "failed"]
    detail: str = ""
    modelName: Optional[str] = None
    changes: List[KBReviewChange] = []
    reviewedUntil: Optional[int] = None


KBMemory.model_rebuild()
