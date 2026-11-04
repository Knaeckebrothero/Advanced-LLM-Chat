/**
 * The knowledge base as the API returns it (backend/models/knowledge_base.py, docs/knowledge_base.md):
 * the Markdown notes that agents keep for a signed-in user. A note's slug is its id; its version is
 * the id of its newest revision, which an edit sends back as baseVersion. A user has a shared
 * knowledge base (vault 0) and one per agent with its own memory (vault: the agent's id); the note
 * "memory" of each is the agent's memory, part of every answer.
 */

export type NoteStatus = 'active' | 'archived';

export interface IKBNoteSummary {
  slug: string;
  title: string;
  description: string | null;
  tags: string[];
  status: NoteStatus;
  updatedAt: string | null;
}

export interface IKBTagCount {
  tag: string;
  count: number;
}

export interface IKBNoteList {
  notes: IKBNoteSummary[];
  total: number;
  tags: IKBTagCount[];
  counts: { active: number; archived: number };
}

export interface IKBSearchHit extends IKBNoteSummary {
  snippet: string;
  matched: string[];
}

export interface IKBLink {
  slug: string;
  title: string | null;  // null: there is no such note (yet)
  status: NoteStatus | null;
}

export type RevisionAction = 'create' | 'update' | 'archive' | 'restore';

export interface IKBRevisionSummary {
  id: number;
  action: RevisionAction;
  title: string;
  status: NoteStatus;
  author: 'agent' | 'review' | 'dream' | 'user';  // review: the memory review after a conversation; dream: the nightly consolidation
  conversationId: string | null;
  conversationName: string | null;  // null: no conversation, or it was deleted
  personaId: number | null;
  personaName: string | null;
  reason: string | null;
  createdAt: string | null;
}

export interface IKBRevision extends IKBRevisionSummary {
  description: string | null;
  tags: string[];
  content: string;
}

export interface IKBNote extends IKBNoteSummary {
  content: string;
  createdAt: string | null;
  version: number;
  links: IKBLink[];
  backlinks: IKBLink[];
  revisions: IKBRevisionSummary[];  // Newest first
}

export interface IKBNoteWrite {
  title: string;
  content: string;
  description: string | null;
  tags: string[];
}

export interface IKBNoteUpdate extends IKBNoteWrite {
  baseVersion: number | null;
}

/** A knowledge base of the user: the shared one (id 0) or an agent's own one. */
export interface IKBVault {
  id: number;
  personaId: number | null;
  personaName: string | null;  // null for the shared one, or if the agent was deleted
  available: boolean;  // false: the agent is gone or no longer has its own memory; its notes stay
  active: number;
  archived: number;
  memoryLines: number;
}

/** The memory of a knowledge base; note is null while it is empty. */
export interface IKBMemory {
  note: IKBNote | null;
  lines: number;
  chars: number;
  maxLines: number;
  maxChars: number;
}

export interface IKBReviewChange {
  tool: string;
  title: string;
  content: string;
  note: string | null;
  vault: number;
}

/** What a memory review on request did (POST /api/kb/review). */
export interface IKBReviewResult {
  status: 'done' | 'nothing_new' | 'not_available' | 'failed';
  detail: string;
  modelName: string | null;
  changes: IKBReviewChange[];
  reviewedUntil: number | null;
}

/** The memory's slug in every knowledge base */
export const KB_MEMORY_SLUG = 'memory';

/** The detail of a refused request: not_found, exists (slug, status), conflict (version), invalid, guest. */
export interface IKBErrorDetail {
  code: 'not_found' | 'exists' | 'conflict' | 'invalid' | 'guest';
  message: string;
  slug?: string;
  status?: NoteStatus;
  version?: number;
}

// Limits of the backend (backend/services/knowledge_base.py)
export const KB_MAX_TITLE_CHARS = 200;
export const KB_MAX_DESCRIPTION_CHARS = 300;
export const KB_MAX_CONTENT_CHARS = 50_000;
export const KB_MAX_TAGS = 20;
export const KB_MAX_TAG_CHARS = 50;
