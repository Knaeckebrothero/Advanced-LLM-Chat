/**
 * The knowledge base as the API returns it (backend/models/knowledge_base.py, docs/knowledge_base.md):
 * the Markdown notes that agents keep for a signed-in user. A note's slug is its id; its version is
 * the id of its newest revision, which an edit sends back as baseVersion.
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
  author: 'agent' | 'user';
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
