import { Injectable } from '@angular/core';
import { IFileRef } from '../data/models/file.model';
import { ApiService } from './api.service';

// Conversations whose files are kept in memory; the oldest go first
const MAX_CONVERSATIONS = 30;
// A list that hasn't arrived after this long counts as not reachable
const LOAD_TIMEOUT_MS = 20000;

/**
 * The files of conversations (GET /api/files?conversationId=...), for the files an answer
 * places in its text (docs/files.md): the files of the answer itself are in its steps, any
 * other file it names (an upload, a file of an earlier answer) is found here.
 *
 * A list is loaded when an answer first needs it, and once more for a name it doesn't have,
 * since the file may be newer than the list.
 */
@Injectable({ providedIn: 'root' })
export class ConversationFilesService {
  /** Counts up whenever a list arrives: what was worked out from the lists is worked out again. */
  version = 0;

  private lists = new Map<string, IFileRef[]>();
  private loading = new Map<string, Promise<void>>();
  // Per conversation, the references a list was already loaded again for
  private asked = new Map<string, Set<string>>();

  constructor(private api: ApiService) {}

  /** The conversation's files as far as known; undefined until its list has arrived. */
  files(conversationId: string): IFileRef[] | undefined {
    if (!this.stored(conversationId)) return [];
    const files = this.lists.get(conversationId);
    if (!files) void this.load(conversationId);
    return files;
  }

  /**
   * A reference the list has no file for: the list is loaded again, once per reference.
   * @returns Whether a list is on its way, so the file may still turn up.
   */
  retry(conversationId: string, reference: string): boolean {
    if (!this.stored(conversationId)) return false;
    let asked = this.asked.get(conversationId);
    if (!asked) this.asked.set(conversationId, asked = new Set());
    if (!asked.has(reference)) {
      asked.add(reference);
      void this.load(conversationId);
    }
    return this.loading.has(conversationId);
  }

  /** A conversation the server has: a new one has no ID yet. */
  private stored(conversationId: string): boolean {
    return !!conversationId && conversationId !== '0';
  }

  private load(conversationId: string): Promise<void> {
    let loading = this.loading.get(conversationId);
    if (!loading) {
      const late = new Promise<never>((_resolve, reject) => setTimeout(() => reject(new Error('timeout')), LOAD_TIMEOUT_MS));
      loading = Promise.race([this.api.getConversationFiles(conversationId), late])
        // Not reachable: what is known stays, and the answer shows what it can
        .catch(() => this.lists.get(conversationId) ?? [])
        .then(files => {
          this.lists.delete(conversationId);
          this.lists.set(conversationId, files);
          this.loading.delete(conversationId);
          this.version++;
          this.trim();
        });
      this.loading.set(conversationId, loading);
    }
    return loading;
  }

  private trim(): void {
    while (this.lists.size > MAX_CONVERSATIONS) {
      const oldest = this.lists.keys().next().value!;
      this.lists.delete(oldest);
      this.asked.delete(oldest);
    }
  }
}
