import { Injectable, computed, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { ApiService } from '../services/api.service';
import {
  IKBErrorDetail,
  IKBMemory,
  IKBNote,
  IKBNoteSummary,
  IKBNoteUpdate,
  IKBNoteWrite,
  IKBRevision,
  IKBSearchHit,
  IKBTagCount,
  IKBVault,
  KB_MEMORY_SLUG,
  NoteStatus
} from '../data/models/knowledge-base.model';

export type ListState = 'loading' | 'ready' | 'error' | 'forbidden';
export type NoteState = 'none' | 'loading' | 'ready' | 'not_found' | 'error';

/** The detail of a refused knowledge base request, or null for other errors. */
export function kbErrorDetail(error: unknown): IKBErrorDetail | null {
  if (error instanceof HttpErrorResponse && error.error?.detail && typeof error.error.detail === 'object'
      && typeof error.error.detail.code === 'string') {
    return error.error.detail as IKBErrorDetail;
  }
  return null;
}

/**
 * State of the Knowledge base page: the knowledge base shown (the shared one, or an agent's own),
 * its memory, the list (by status and tag, or the hits of a search), the open note, and the
 * writes. The page needs the server: the notes are only stored there.
 */
@Injectable()
export class KnowledgeBaseStore {
  // The knowledge base shown (0: the shared one) and the user's knowledge bases
  readonly vault = signal(0);
  readonly vaults = signal<IKBVault[]>([]);
  readonly currentVault = computed(() => this.vaults().find(item => item.id === this.vault()) ?? null);
  readonly memory = signal<IKBMemory | null>(null);

  // The list
  readonly status = signal<NoteStatus>('active');
  readonly tag = signal<string | null>(null);
  readonly query = signal('');
  readonly listState = signal<ListState>('loading');
  readonly notes = signal<IKBNoteSummary[]>([]);
  readonly hits = signal<IKBSearchHit[] | null>(null);  // null: no search
  readonly total = signal(0);
  readonly tags = signal<IKBTagCount[]>([]);
  readonly counts = signal({ active: 0, archived: 0 });

  // The open note
  readonly slug = signal<string | null>(null);
  readonly note = signal<IKBNote | null>(null);
  readonly noteState = signal<NoteState>('none');

  /** What the list shows: the search hits, or the notes. */
  readonly items = computed<Array<IKBNoteSummary | IKBSearchHit>>(() => this.hits() ?? this.notes());
  readonly searching = computed(() => this.hits() !== null);

  private listRequest = 0;
  private noteRequest = 0;
  private memoryRequest = 0;

  constructor(private api: ApiService) {}

  // Knowledge bases and the memory

  async loadVaults(): Promise<void> {
    try {
      this.vaults.set(await this.api.getKBVaults());
    } catch {
      // The page still works on the shared knowledge base
    }
  }

  /** Show another knowledge base: its list from the start, and its memory. */
  setVault(vault: number): void {
    if (vault === this.vault()) return;
    this.vault.set(vault);
    this.tag.set(null);
    this.query.set('');
    this.hits.set(null);
    this.memory.set(null);
    this.listState.set('loading');
    this.loadList();
  }

  async loadMemory(): Promise<void> {
    const request = ++this.memoryRequest;
    try {
      const memory = await this.api.getKBMemory(this.vault());
      if (request === this.memoryRequest) this.memory.set(memory);
    } catch {
      if (request === this.memoryRequest) this.memory.set(null);
    }
  }

  // List

  async loadList(): Promise<void> {
    const request = ++this.listRequest;
    const query = this.query().trim();
    const vault = this.vault();
    if (this.listState() !== 'ready') this.listState.set('loading');
    this.loadMemory();
    try {
      if (query) {
        // A search also brings the counts and tags up to date
        const [hits, list] = await Promise.all([
          this.api.searchKBNotes(query, this.status(), vault),
          this.api.getKBNotes(this.status(), this.tag(), vault)
        ]);
        if (request !== this.listRequest) return;
        this.applyList(list);
        this.hits.set(hits);
      } else {
        const list = await this.api.getKBNotes(this.status(), this.tag(), vault);
        if (request !== this.listRequest) return;
        this.applyList(list);
        this.hits.set(null);
      }
      this.listState.set('ready');
    } catch (error) {
      if (request !== this.listRequest) return;
      const forbidden = error instanceof HttpErrorResponse && (error.status === 401 || error.status === 403);
      this.listState.set(forbidden ? 'forbidden' : 'error');
    }
  }

  private applyList(list: { notes: IKBNoteSummary[]; total: number; tags: IKBTagCount[]; counts: { active: number; archived: number } }): void {
    this.notes.set(list.notes);
    this.total.set(list.total);
    this.counts.set(list.counts);
    // The tag chips: those in use with this status (a picked tag stays visible)
    if (!this.tag()) this.tags.set(list.tags);
  }

  setStatus(status: NoteStatus): void {
    if (status === this.status()) return;
    this.status.set(status);
    this.tag.set(null);
    this.loadList();
  }

  setTag(tag: string | null): void {
    this.tag.set(tag === this.tag() ? null : tag);
    this.query.set('');
    this.loadList();
  }

  /** Search the notes with the status (a search goes over all of them, not only a picked tag). */
  setQuery(query: string): void {
    this.query.set(query);
    if (query.trim()) this.tag.set(null);
    this.loadList();
  }

  // The open note

  async open(slug: string | null): Promise<void> {
    const request = ++this.noteRequest;
    this.slug.set(slug);
    if (!slug) {
      this.note.set(null);
      this.noteState.set('none');
      return;
    }
    if (this.note()?.slug !== slug) {
      this.note.set(null);
      this.noteState.set('loading');
    }
    try {
      const note = await this.api.getKBNote(slug, this.vault());
      if (request !== this.noteRequest) return;
      this.note.set(note);
      this.noteState.set('ready');
    } catch (error) {
      if (request !== this.noteRequest) return;
      this.note.set(null);
      this.noteState.set(kbErrorDetail(error)?.code === 'not_found' ? 'not_found' : 'error');
    }
  }

  /** Show a note the server returned after a write, and bring the list up to date. */
  private shown(note: IKBNote): IKBNote {
    this.noteRequest++;
    this.slug.set(note.slug);
    this.note.set(note);
    this.noteState.set('ready');
    this.loadList();
    return note;
  }

  // Writes (errors go to the caller, which shows them)

  async create(note: IKBNoteWrite): Promise<IKBNote> {
    return this.shown(await this.api.createKBNote(note, this.vault()));
  }

  async save(slug: string, note: IKBNoteUpdate): Promise<IKBNote> {
    return this.shown(await this.api.updateKBNote(slug, note, this.vault()));
  }

  async archive(slug: string): Promise<IKBNote> {
    return this.shown(await this.api.archiveKBNote(slug, this.vault()));
  }

  async restore(slug: string): Promise<IKBNote> {
    return this.shown(await this.api.restoreKBNote(slug, this.vault()));
  }

  async delete(slug: string): Promise<void> {
    await this.api.deleteKBNote(slug, this.vault());
    if (this.slug() === slug) {
      this.note.set(null);
      this.noteState.set('none');
    }
    this.loadList();
  }

  getRevision(slug: string, revisionId: number): Promise<IKBRevision> {
    return this.api.getKBRevision(slug, revisionId, this.vault());
  }

  async restoreRevision(slug: string, revisionId: number, baseVersion: number): Promise<IKBNote> {
    return this.shown(await this.api.restoreKBRevision(slug, revisionId, baseVersion, this.vault()));
  }

  /** Is this the memory (and not an ordinary note)? */
  isMemory(slug: string | null | undefined): boolean {
    return slug === KB_MEMORY_SLUG;
  }

  /** The zip for Obsidian, with the times in the browser's time zone (Obsidian reads them as local times). */
  exportVault(): Promise<Blob> {
    let timeZone: string | null = null;
    try {
      timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
    } catch {
      // Unknown: the server writes UTC
    }
    return this.api.exportKnowledgeBase(timeZone, this.vault());
  }
}
