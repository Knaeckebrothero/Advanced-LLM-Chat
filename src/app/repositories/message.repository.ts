import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, from } from 'rxjs';
import { map, switchMap } from 'rxjs/operators';
import { BaseRepository, SyncResult } from './base.repository';
import { DBService } from '../data/db.service';
import { ApiService } from '../services/api.service';
import { Message } from '../data/objects/message';
import { FilePreview, UploadStatus } from '../data/objects/file-preview';
import { environment } from '../environments/environment';

export interface MessageWithSyncStatus extends Message {
  syncStatus?: 'pending' | 'synced' | 'failed';
  syncError?: string;
}

@Injectable({
  providedIn: 'root'
})
export class MessageRepository extends BaseRepository<MessageWithSyncStatus> {
  // Separate cache for each conversation
  private conversationCaches = new Map<string, BehaviorSubject<MessageWithSyncStatus[]>>();
  /** When this browser last changed a message of a conversation itself (its own clock). */
  private localChanges = new Map<string, number>();
  private pendingUploads = new Map<string, FilePreview[]>();

  constructor(
    dbService: DBService,
    apiService: ApiService
  ) {
    super(dbService, apiService);
  }

  /**
   * Get all messages (across all conversations)
   */
  getAll(): Observable<MessageWithSyncStatus[]> {
    return from(this.dbService.getAllMessages()).pipe(
      map(messages => messages as MessageWithSyncStatus[])
    );
  }

  /**
   * Get message by ID
   */
  getById(id: string | number): Observable<MessageWithSyncStatus | null> {
    const numId = typeof id === 'string' ? parseInt(id, 10) : id;
    return from(this.dbService.getMessage(numId)).pipe(
      map(message => message as MessageWithSyncStatus | null)
    );
  }

  /**
   * Get messages for a specific conversation
   */
  getByConversationId(conversationId: string): Observable<MessageWithSyncStatus[]> {
    // Create cache for conversation if it doesn't exist
    if (!this.conversationCaches.has(conversationId)) {
      const cache = new BehaviorSubject<MessageWithSyncStatus[]>([]);
      this.conversationCaches.set(conversationId, cache);

      // Load initial data
      this.loadConversationMessages(conversationId);
    }

    return this.conversationCaches.get(conversationId)!.asObservable();
  }

  /**
   * Save a new message
   * @param message - The message to save
   * @param skipSync - Skip backend sync (used for agent messages already saved by SSE endpoint)
   */
  async save(message: MessageWithSyncStatus, skipSync: boolean = false): Promise<MessageWithSyncStatus> {
    this.noteLocalChange(message.conversationId);
    try {
      // Being sent from the start: the chat shows a message of the user's that only this browser
      // has, and isn't being sent, as not sent
      if (!skipSync && !message.isAgent()) {
        message.syncStatus = 'pending';
      }

      // Handle file uploads if message has attachments
      if (message.isText() && message.attachments?.length) {
        await this.handleFileAttachments(message);
      }

      // Save to IndexedDB first. A sync may have brought the server's copy of it a moment ago
      // (an answer is stored on the server before its stream ends), so it replaces a copy
      await this.dbService.saveMessage(message);
      this.putInCache(message);

      // Skip sync for agent messages (already saved by backend during streaming)
      // or when explicitly requested
      if (skipSync || message.isAgent()) {
        message.syncStatus = 'synced';
        return message;
      }

      // Mark as pending sync
      message.syncStatus = 'pending';

      // Attempt to sync with backend if online. Nothing sends it later (no outbox): a message
      // the server didn't take is 'failed' and stays in this browser until it is sent again
      // (resend()) or deleted.
      if (await this.isOnline()) {
        try {
          await this.syncMessage(message);
          message.syncStatus = 'synced';
        } catch (error) {
          message.syncStatus = 'failed';
          message.syncError = error instanceof Error ? error.message : 'Unknown error';
        }
      } else {
        message.syncStatus = 'failed';
        message.syncError = 'The server is not reachable';
      }

      return message;
    } catch (error) {
      console.error('Failed to save message:', error);
      throw error;
    } finally {
      this.noteLocalChange(message.conversationId);
    }
  }

  /**
   * Store a changed message of this browser as it is. Its version stays: the server counts the
   * versions of the messages it has (see patch()).
   */
  async update(message: MessageWithSyncStatus): Promise<MessageWithSyncStatus> {
    this.noteLocalChange(message.conversationId);
    try {
      await this.dbService.saveMessage(message);
      this.replaceInCache(message);

      // Sync with backend if online
      if (await this.isOnline() && message.syncStatus === 'pending') {
        await this.syncMessage(message);
      }

      return message;
    } catch (error) {
      console.error('Failed to update message:', error);
      throw error;
    } finally {
      this.noteLocalChange(message.conversationId);
    }
  }

  /**
   * Save the edited text of a stored message on the server and in this browser. A text message
   * keeps its attachments, an answer its steps.
   *
   * The server counts a version per message and takes an edit only of the version it has. It
   * answers with the new version, which this browser's copy takes. The browser never counts
   * versions itself: its copy would run ahead of the server's, and the next edit be refused.
   *
   * If the server has another version (the message was edited on another device since the last
   * sync, or this browser's copy is from an app version that counted itself), the edit is saved
   * once more on the version the server has: the text the user just wrote is the newest.
   *
   * Throws when the server doesn't take the edit; the message then stays as it was.
   * @param deleteFollowing - Also delete the messages after it on the server, so it can be answered again
   */
  async patch(
    message: MessageWithSyncStatus, content: string, deleteFollowing = false
  ): Promise<MessageWithSyncStatus> {
    const { conversationId, id } = message;
    this.noteLocalChange(conversationId);
    try {
      let stored: Message;
      try {
        stored = await this.apiService.patchMessage(conversationId, id, content, message.version, deleteFollowing);
      } catch (error: any) {
        if (error?.status !== 409) throw error;
        // The newest message up to this one: the message itself, as the server has it
        const [current] = await this.apiService.getConversationMessages(conversationId, 1, id + 1);
        if (current?.id !== id) throw error;
        stored = await this.apiService.patchMessage(conversationId, id, content, current.version, deleteFollowing);
      }

      const updated: MessageWithSyncStatus = new Message(
        { ...message.metadata, version: stored.version, lastModified: stored.lastModified },
        { ...message.content, content }
      );
      await this.dbService.saveMessage(updated);
      this.replaceInCache(updated);
      return updated;
    } finally {
      this.noteLocalChange(conversationId);
    }
  }

  /**
   * Delete a message
   */
  async delete(id: string | number): Promise<void> {
    const numId = typeof id === 'string' ? parseInt(id, 10) : id;

    try {
      // Get message to find conversation ID
      const message = await this.dbService.getMessage(numId);
      if (!message) return;

      const conversationId = message.conversationId;
      this.noteLocalChange(conversationId);
      await this.dbService.deleteMessage(numId);

      // Update cache
      if (this.conversationCaches.has(conversationId)) {
        const cache = this.conversationCaches.get(conversationId)!;
        const current = cache.getValue();
        const filtered = current.filter(m => m.id !== numId);
        cache.next(filtered);
      }

      // Sync deletion with backend if online
      if (await this.isOnline()) {
        try {
          await this.apiService.deleteMessage(conversationId, numId);
        } catch (error: any) {
          // Don't log 404 errors - message might already be deleted on backend
          if (error.status !== 404) {
            console.error('Failed to sync message deletion:', error);
          }
        }
      }
      this.noteLocalChange(conversationId);
    } catch (error) {
      console.error('Failed to delete message:', error);
      throw error;
    }
  }

  /**
   * Send a message that only this browser has (its sending failed) to the server again. It takes
   * the id and time the server gives it, so it moves to the end of the stored messages.
   * Throws if the server doesn't take it; the message stays as it was ('failed').
   */
  async resend(message: MessageWithSyncStatus): Promise<MessageWithSyncStatus> {
    if (!message.isLocal) {
      return message;
    }
    if (message.isText() && message.attachments?.length) {
      await this.handleFileAttachments(message);
    }
    message.syncStatus = 'pending';
    this.noteLocalChange(message.conversationId);
    try {
      await this.syncMessage(message);
    } finally {
      this.noteLocalChange(message.conversationId);
    }
    return message;
  }

  /**
   * Compute hash for messages
   */
  async computeHash(messages: MessageWithSyncStatus[]): Promise<string> {
    const data = messages
      .map(m => ({
        id: m.id,
        conversationId: m.conversationId,
        roleName: m.roleName,
        content: m.getDisplayContent(),
        time: m.time?.toISOString()
      }))
      .sort((a, b) => (a.id || 0) - (b.id || 0));

    return this.computeHashFromString(JSON.stringify(data));
  }

  /**
   * Sync messages - handled by ConversationRepository
   */
  async sync(): Promise<SyncResult> {
    // Message sync is handled at the conversation level
    // This could sync pending messages or handle conflict resolution
    return {
      success: true,
      itemsUpdated: 0
    };
  }

  /**
   * Get messages with pending uploads
   */
  async getMessagesWithPendingUploads(): Promise<MessageWithSyncStatus[]> {
    const allMessages = await this.dbService.getAllMessages();
    return allMessages.filter(msg =>
      msg.isText() &&
      msg.attachments?.some(f => f.uploadStatus === UploadStatus.PENDING)
    ) as MessageWithSyncStatus[];
  }

  /**
   * Upload pending files
   */
  async uploadPendingFiles(): Promise<void> {
    const messagesWithPending = await this.getMessagesWithPendingUploads();

    for (const message of messagesWithPending) {
      if (!message.attachments) continue;

      const pendingFiles = message.attachments.filter(f => f.uploadStatus === UploadStatus.PENDING);
      if (pendingFiles.length === 0) continue;

      try {
        const uploadedFileIds = await this.apiService.uploadFiles(pendingFiles);

        // Update file statuses
        pendingFiles.forEach((f, index) => {
          const uploadResponse = uploadedFileIds[index];
          f.uploadStatus = UploadStatus.COMPLETED;
          f.id = uploadResponse?.fileId || f.id;
          f.transcript = uploadResponse?.transcript || f.transcript;
          f.error = undefined;
        });

        await this.update(message);
      } catch (error) {
        console.error(`Failed to upload files for message ${message.id}:`, error);

        pendingFiles.forEach(f => {
          f.uploadStatus = UploadStatus.FAILED;
          f.error = 'Upload failed';
        });

        await this.update(message);
      }
    }
  }

  /**
   * Clear cache for a conversation
   */
  clearConversationCache(conversationId: string): void {
    if (this.conversationCaches.has(conversationId)) {
      this.conversationCaches.get(conversationId)!.complete();
      this.conversationCaches.delete(conversationId);
    }
  }

  /**
   * Remove messages from this browser only, e.g. the ones the server deleted after an edited message.
   */
  async removeLocally(conversationId: string, ids: number[]): Promise<void> {
    if (ids.length === 0) return;
    this.noteLocalChange(conversationId);
    for (const id of ids) {
      await this.dbService.deleteMessage(id);
    }
    const cache = this.conversationCaches.get(conversationId);
    if (cache) {
      const removed = new Set(ids);
      cache.next(cache.getValue().filter(m => !removed.has(m.id)));
    }
  }

  /**
   * Whether this browser changed a message of the conversation itself (sent, edited, deleted or
   * rated one) since the given time of its clock. A sync that asked the server before then got
   * an answer older than the change, and leaves the conversation to the next sync.
   */
  changedLocallySince(conversationId: string, time: number): boolean {
    return (this.localChanges.get(conversationId) ?? 0) >= time;
  }

  /** A message of the conversation is being changed here, or the server just took the change. */
  private noteLocalChange(conversationId: string): void {
    this.localChanges.set(conversationId, Date.now());
  }

  /**
   * Put a message into its conversation's cache, in place of the copies it replaces: one with
   * its own id, and the one with the id it had before the server gave it its own.
   */
  private putInCache(message: MessageWithSyncStatus, previousId: number = message.id): void {
    const cache = this.conversationCaches.get(message.conversationId);
    if (!cache) return;
    const others = cache.getValue().filter(m => m.id !== message.id && m.id !== previousId);
    cache.next([...others, message]);
  }

  /** Put a changed message in the place of its copy in the conversation's cache. */
  private replaceInCache(message: MessageWithSyncStatus): void {
    const cache = this.conversationCaches.get(message.conversationId);
    if (!cache) return;
    const current = cache.getValue();
    const index = current.findIndex(m => m.id === message.id);
    if (index >= 0) {
      current[index] = message;
      cache.next([...current]);
    }
  }

  /**
   * Refresh cache after external database updates (e.g., after sync)
   */
  async refreshConversationCache(conversationId: string): Promise<void> {
    const cache = this.conversationCaches.get(conversationId);
    if (cache) {
      // Reload messages from database
      const messages = await this.dbService.getMessagesByConversationId(conversationId);
      cache.next(messages as MessageWithSyncStatus[]);
    }
  }

  /**
   * Load messages for a conversation from IndexedDB
   */
  private async loadConversationMessages(conversationId: string): Promise<void> {
    try {
      const messages = await this.dbService.getMessagesByConversationId(conversationId);
      const cache = this.conversationCaches.get(conversationId);
      if (cache) {
        cache.next(messages as MessageWithSyncStatus[]);
      }
    } catch (error) {
      console.error(`Failed to load messages for conversation ${conversationId}:`, error);
    }
  }

  /**
   * Handle file attachments
   */
  private async handleFileAttachments(message: MessageWithSyncStatus): Promise<void> {
    if (!message.isText() || !message.attachments) return;

    const pendingFiles = message.attachments.filter(f => f.uploadStatus === UploadStatus.PENDING);
    if (pendingFiles.length === 0) return;

    // Store pending uploads for later retry
    this.pendingUploads.set(message.conversationId, pendingFiles);

    // Try to upload if online
    if (await this.isOnline()) {
      try {
        const uploadedFileIds = await this.apiService.uploadFiles(pendingFiles);

        pendingFiles.forEach((f, index) => {
          const uploadResponse = uploadedFileIds[index];
          f.uploadStatus = UploadStatus.COMPLETED;
          f.id = uploadResponse?.fileId || f.id;
          f.transcript = uploadResponse?.transcript || f.transcript;
        });

        this.pendingUploads.delete(message.conversationId);
      } catch (error) {
        console.error('Failed to upload files:', error);
        pendingFiles.forEach(f => {
          f.uploadStatus = UploadStatus.FAILED;
          f.error = 'Upload failed';
        });
      }
    }
  }

  /**
   * Sync a single message with backend (used for updates/patches)
   */
  private async syncMessage(message: MessageWithSyncStatus): Promise<void> {
    if (!message.conversationId) {
      throw new Error('Cannot sync message without conversation ID');
    }

    try {
      // For now, just use the regular send message endpoint
      // In the future, this could handle updates differently
      const stored = await this.apiService.sendMessage(message);

      // Take the id and time the server gave it: they decide its place in the conversation
      if (stored.id && stored.id !== message.id) {
        const oldId = message.id;
        message.id = stored.id;
        if (stored.time) message.time = new Date(stored.time * 1000);

        // Update in IndexedDB with new ID (a sync may have stored the server's copy already)
        await this.dbService.deleteMessage(oldId);
        await this.dbService.saveMessage(message);
        this.putInCache(message, oldId);
      }

      message.syncStatus = 'synced';
    } catch (error) {
      console.error('Failed to sync message with backend:', error);
      message.syncStatus = 'failed';
      message.syncError = error instanceof Error ? error.message : 'Unknown error';
      throw error;
    }
  }

  /**
   * Send message and optionally generate AI response
   */
  async sendAndGenerate(
    message: MessageWithSyncStatus,
    generateResponse: boolean = true,
    settings?: any
  ): Promise<MessageWithSyncStatus | null> {
    try {
      // Save to IndexedDB first
      await this.dbService.addMessage(message);

      // Update cache
      const conversationId = message.conversationId;
      if (this.conversationCaches.has(conversationId)) {
        const cache = this.conversationCaches.get(conversationId)!;
        const current = cache.getValue();
        cache.next([...current, message]);
      }

      // Mark as pending sync
      message.syncStatus = 'pending';

      // Attempt to sync with backend if online
      if (await this.isOnline()) {
        try {
          const result = await this.apiService.sendAndGenerateMessage(message, generateResponse);

          // Take the id and time the server gave the user message
          if (result.userMessageId && result.userMessageId !== message.id) {
            const oldId = message.id;
            message.id = result.userMessageId;
            if (result.userMessageTime) message.time = new Date(result.userMessageTime * 1000);

            // Update in IndexedDB
            await this.dbService.deleteMessage(oldId);
            await this.dbService.addMessage(message);

            // Update cache
            if (this.conversationCaches.has(conversationId)) {
              const cache = this.conversationCaches.get(conversationId)!;
              const current = cache.getValue();
              const index = current.findIndex(m => m.id === oldId);
              if (index >= 0) {
                current[index] = message;
                cache.next([...current]);
              }
            }
          }

          message.syncStatus = 'synced';

          // If AI message was generated, save it too
          if (result.aiMessage) {
            const aiMessage = result.aiMessage as MessageWithSyncStatus;
            aiMessage.syncStatus = 'synced';

            // Save directly to avoid duplicate sync attempt
            await this.dbService.addMessage(aiMessage);

            // Update cache
            if (this.conversationCaches.has(conversationId)) {
              const cache = this.conversationCaches.get(conversationId)!;
              const current = cache.getValue();
              cache.next([...current, aiMessage]);
            }

            return aiMessage;
          }
        } catch (error) {
          message.syncStatus = 'failed';
          message.syncError = error instanceof Error ? error.message : 'Unknown error';
          console.error('Failed to sync with backend:', error);
          // Don't throw - message is saved locally
        }
      }

      return null;
    } catch (error) {
      console.error('Failed to save message:', error);
      throw error;
    }
  }

  /**
   * Rate a message (thumbs up or thumbs down)
   */
  async rateMessage(messageId: number, conversationId: string, rating: number | null): Promise<MessageWithSyncStatus> {
    try {
      // Update in backend
      this.noteLocalChange(conversationId);
      const rated = await this.apiService.rateMessage(messageId, conversationId, rating);
      this.noteLocalChange(conversationId);

      // The server's answer to a rating has the message's text only: this browser's copy keeps
      // its steps, model and attachments, and takes the rating and the version the server has
      const local = this.conversationCaches.get(conversationId)?.getValue().find(m => m.id === messageId)
        ?? await this.dbService.getMessage(messageId);
      const messageWithSync: MessageWithSyncStatus = local
        ? new Message({ ...local.metadata, rating: rated.rating, version: rated.version }, local.content)
        : rated;
      messageWithSync.syncStatus = 'synced';

      await this.dbService.saveMessage(messageWithSync);
      this.replaceInCache(messageWithSync);

      return messageWithSync;
    } catch (error) {
      console.error('Failed to rate message:', error);
      throw error;
    }
  }

  /**
   * Regenerate an AI message
   */
  async regenerateMessage(messageId: number, conversationId: string): Promise<MessageWithSyncStatus> {
    try {
      // Regenerate in backend
      this.noteLocalChange(conversationId);
      const regeneratedMessage = await this.apiService.regenerateMessage(messageId, conversationId);
      this.noteLocalChange(conversationId);

      // Convert to MessageWithSyncStatus
      const messageWithSync: MessageWithSyncStatus = Object.assign(
        Object.create(Object.getPrototypeOf(regeneratedMessage)),
        regeneratedMessage,
        { syncStatus: 'synced' as const }
      );

      // The server's copy, with the version it has now
      await this.dbService.saveMessage(messageWithSync);
      this.replaceInCache(messageWithSync);

      return messageWithSync;
    } catch (error) {
      console.error('Failed to regenerate message:', error);
      throw error;
    }
  }

  /**
   * Check if backend is available
   */
  private async isOnline(): Promise<boolean> {
    try {
      const response = await fetch(`${environment.apiUrl}/api/auth/me`, {
        method: 'GET',
        credentials: 'include'
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  /**
   * Clear all cached data
   * Used during logout to ensure clean state
   */
  clearAllCaches(): void {
    // Complete and clear all conversation caches
    this.conversationCaches.forEach((cache, conversationId) => {
      cache.complete();
    });
    this.conversationCaches.clear();
    this.pendingUploads.clear();
  }
}
