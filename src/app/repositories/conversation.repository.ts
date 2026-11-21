import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, from, of } from 'rxjs';
import { map, catchError } from 'rxjs/operators';
import { BaseRepository, SyncResult } from './base.repository';
import { DBService } from '../data/db.service';
import { ApiService } from '../services/api.service';
import { Conversation } from '../data/objects/conversation';
import { Message } from '../data/objects/message';
import { IConversationSelection } from '../data/models/catalog.model';
import { IConversationFile } from '../data/models/api.model';
import { MessageRepository } from './message.repository';

// Import from db-schema instead of defining here
import { ConversationSyncMetadata } from '../data/db-schema';

/**
 * The ids of the messages the server deleted since the last sync: the ones it had then
 * (`knownIds`, its newest messages at that time) and doesn't return now, although they are not
 * older than what it returns (a message that only moved out of the newest ones is still there).
 * A message the server never had (not sent, or an answer stopped before the server stored it)
 * is not among the known ids, so it stays in this browser.
 */
export function removedOnServer(knownIds: number[], serverMessages: Message[]): number[] {
  const serverIds = new Set(serverMessages.map(m => m.id));
  const oldestId = serverMessages.reduce((oldest, m) => Math.min(oldest, m.id), Number.POSITIVE_INFINITY);
  return knownIds.filter(id => !serverIds.has(id) && (serverMessages.length === 0 || id > oldestId));
}

/**
 * What to store in this browser for a message the server returned: the server's copy, or null
 * if the browser's copy says the same (nothing is written then, so the chat doesn't render it
 * again). The server's copy keeps what only this browser has of an attachment: a voice
 * message's audio for offline playback and its transcript.
 */
export function mergeServerMessage(server: Message, local: Message | undefined): Message | null {
  if (!local) {
    return server;
  }
  if (serverView(local) === serverView(server)) {
    return null;
  }
  if (server.isText() && local.isText() && server.attachments && local.attachments) {
    for (const serverAttachment of server.attachments) {
      const localAttachment = local.attachments.find(a => a.id === serverAttachment.id);
      if (localAttachment?.base64Data && !serverAttachment.base64Data) {
        serverAttachment.base64Data = localAttachment.base64Data;
      }
      if (localAttachment?.transcript && !serverAttachment.transcript) {
        serverAttachment.transcript = localAttachment.transcript;
      }
    }
  }
  return server;
}

/** What the server stores of a message, as one string: equal for two copies that say the same. */
function serverView(message: Message): string {
  const content = message.content as any;
  const view: Record<string, unknown> = {
    roleName: message.roleName,
    time: message.time.getTime(),
    version: message.version ?? 1,
    rating: message.rating ?? null,
    alternatives: message.alternatives,
    type: content.type,
    text: content.content ?? ''
  };
  if (content.type === 'agent') {
    view['steps'] = content.steps ?? [];
    view['status'] = content.status;
    view['error'] = content.error ?? null;
    view['modelId'] = content.modelId ?? null;
    view['modelName'] = content.modelName ?? null;
    view['usage'] = content.usage ?? null;
  } else {
    view['attachments'] = (content.attachments ?? []).map((a: { id: string }) => a.id);
  }
  return stableStringify(view);
}

/** JSON with the keys of every object in order: the server stores JSON with its own key order. */
function stableStringify(value: unknown): string {
  return JSON.stringify(value, (_key, item) => {
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      return Object.keys(item).sort().reduce((sorted: Record<string, unknown>, key) => {
        // null and a missing key mean the same in a step's or a usage's fields
        if (item[key] !== null && item[key] !== undefined) {
          sorted[key] = item[key];
        }
        return sorted;
      }, {});
    }
    return item;
  });
}

@Injectable({
  providedIn: 'root'
})
export class ConversationRepository extends BaseRepository<Conversation> {
  private syncMetadata = new Map<string, ConversationSyncMetadata>();
  private activeSyncs = new Map<string, Promise<boolean>>();
  
  constructor(
    dbService: DBService,
    apiService: ApiService,
    private messageRepository: MessageRepository
  ) {
    super(dbService, apiService);
    this.loadConversations();
    this.loadSyncMetadata();
  }

  getAll(): Observable<Conversation[]> {
    return this.cache$.asObservable();
  }

  getById(id: string): Observable<Conversation | null> {
    return this.cache$.pipe(
      map(conversations => conversations.find(c => c.id === id) || null)
    );
  }

  async save(conversation: Conversation): Promise<Conversation> {
    try {
      // Use updateConversation instead of addConversation to handle existing conversations
      await this.dbService.updateConversation(conversation);
      
      const conversations = this.cache$.getValue();
      const index = conversations.findIndex(c => c.id === conversation.id);
      
      if (index >= 0) {
        conversations[index] = conversation;
      } else {
        conversations.push(conversation);
      }
      
      this.updateCache([...conversations]);
      return conversation;
    } catch (error) {
      console.error('Failed to save conversation:', error);
      throw error;
    }
  }

  /**
   * Save a conversation returned by the backend (rename, title generation). If the response
   * leaves out the model fields, the local selection is kept.
   */
  async saveFromServer(conversation: Conversation): Promise<Conversation> {
    this.keepLocalState(conversation);
    return this.save(conversation);
  }

  /**
   * A message the server stored (its id is the server's clock): the conversation moves up in
   * the sidebar right away, before the next sync brings the server's lastMessageAt.
   */
  async recordMessage(conversationId: string, messageId: number): Promise<void> {
    const conversation = this.cache$.getValue().find(c => c.id === conversationId);
    if (conversation?.recordMessage(messageId)) {
      await this.save(conversation);
    }
  }

  /**
   * Keep what the local copy knows better than a conversation the backend returned: a later
   * newest message (the response may have been written before it), and the selection if the
   * response leaves out the model fields or it still has to be sent.
   */
  private keepLocalState(incoming: Conversation): void {
    const local = this.cache$.getValue().find(c => c.id === incoming.id);
    if (!local) return;
    incoming.mergeLastMessageAt(local.lastMessageAt);
    if (local.hiddenPending || incoming.hidden === undefined) {
      incoming.hidden = local.hidden;
      incoming.hiddenBy = local.hiddenBy;
      incoming.hiddenPending = local.hiddenPending;
    }
    if (local.selectionPending || (incoming.modelId === undefined && incoming.personaId === undefined)) {
      incoming.modelId = local.modelId;
      incoming.personaId = local.personaId;
      incoming.personaValues = local.personaValues;
      incoming.selectionPending = local.selectionPending;
    }
  }

  /** A conversation with all its messages as a conversation file (the backend has all of them). */
  exportConversation(id: string): Promise<IConversationFile> {
    return this.apiService.exportConversation(id);
  }

  /** Imports a conversation file as a new conversation; its messages load when it opens. */
  async importConversation(file: IConversationFile): Promise<Conversation> {
    const conversation = await this.apiService.importConversation(file);
    return this.save(conversation);
  }

  async updateConversation(id: string, name: string): Promise<Conversation> {
    try {
      // Call API to update conversation on backend
      const local = this.cache$.getValue().find(c => c.id === id);
      const knownSelection = local && local.modelId !== undefined ? local.selection : undefined;
      const updatedConversation = await this.apiService.updateConversationName(id, name, knownSelection);
      this.keepLocalState(updatedConversation);
      
      // Update local database
      await this.dbService.updateConversation(updatedConversation);
      
      // Update cache
      const conversations = this.cache$.getValue();
      const index = conversations.findIndex(c => c.id === id);
      if (index >= 0) {
        conversations[index] = updatedConversation;
        this.updateCache([...conversations]);
      }
      
      return updatedConversation;
    } catch (error) {
      console.error('Failed to update conversation:', error);
      throw error;
    }
  }

  /**
   * Change a conversation's model and/or persona: saved locally first, then sent to the backend.
   * If the backend can't be reached, the change is marked pending and sent with the next sync.
   */
  async updateSelection(id: string, changes: Partial<IConversationSelection>): Promise<Conversation | null> {
    const conversation = this.cache$.getValue().find(c => c.id === id)
      ?? await this.dbService.getConversation(id);
    if (!conversation) return null;

    if (changes.modelId !== undefined) conversation.modelId = changes.modelId;
    if (changes.personaId !== undefined) conversation.personaId = changes.personaId;
    if (changes.personaValues !== undefined) conversation.personaValues = changes.personaValues;
    conversation.selectionPending = true;
    await this.save(conversation);

    await this.pushSelection(conversation);
    return conversation;
  }

  /**
   * Hide a conversation or unhide it: saved locally first, so a device
   * that is in family mode hides it at once, then sent to the backend (with the next sync if
   * it can't be reached now).
   */
  async setHidden(id: string, hidden: boolean): Promise<Conversation | null> {
    const conversation = this.cache$.getValue().find(c => c.id === id)
      ?? await this.dbService.getConversation(id);
    if (!conversation) return null;
    conversation.hidden = hidden;
    conversation.hiddenBy = 'user';  // The user's decision: agents leave it alone from now on
    conversation.hiddenPending = true;
    await this.save(conversation);
    await this.pushHidden(conversation);
    return conversation;
  }

  /** An agent marked a conversation (or took its mark back) while answering; the server has it already. */
  async applyAgentHidden(id: string, hidden: boolean): Promise<Conversation | null> {
    const conversation = this.cache$.getValue().find(c => c.id === id)
      ?? await this.dbService.getConversation(id);
    if (!conversation || conversation.hiddenPending) return null;
    conversation.hidden = hidden;
    conversation.hiddenBy = 'agent';
    await this.save(conversation);
    return conversation;
  }

  private async pushHidden(conversation: Conversation): Promise<boolean> {
    try {
      await this.apiService.updateConversationHidden(conversation.id, conversation.name, !!conversation.hidden);
      conversation.hiddenPending = false;
      await this.save(conversation);
      return true;
    } catch (error) {
      console.warn(`Could not send the hidden mark of conversation ${conversation.id}, will retry:`, error);
      return false;
    }
  }

  /** Send a conversation's selection to the backend; clears the pending flag on success. */
  private async pushSelection(conversation: Conversation): Promise<boolean> {
    try {
      await this.apiService.updateConversationSelection(conversation.id, conversation.name, conversation.selection);
      // A backend without the catalog accepts the request without storing the fields;
      // the selection then stays local, there is nothing to retry.
      conversation.selectionPending = false;
      await this.save(conversation);
      return true;
    } catch (error) {
      console.warn(`Could not send the model selection of conversation ${conversation.id}, will retry:`, error);
      return false;
    }
  }

  /**
   * Take the model, the persona and the hidden mark from the server's copy of a conversation, or
   * send ours if they changed offline. Returns true when the local conversation was changed.
   */
  private async mergeSelection(localConv: Conversation, serverConv: Conversation): Promise<boolean> {
    let hiddenChanged = false;
    if (localConv.hiddenPending) {
      await this.pushHidden(localConv);
    } else if (serverConv.hidden !== undefined
               && (serverConv.hidden !== localConv.hidden || (serverConv.hiddenBy ?? null) !== (localConv.hiddenBy ?? null))) {
      localConv.hidden = serverConv.hidden;
      localConv.hiddenBy = serverConv.hiddenBy ?? null;
      hiddenChanged = true;
    }
    return await this.mergeModelSelection(localConv, serverConv) || hiddenChanged;
  }

  private async mergeModelSelection(localConv: Conversation, serverConv: Conversation): Promise<boolean> {
    if (localConv.selectionPending) {
      await this.pushSelection(localConv);
      return false;
    }

    // undefined: the backend doesn't know the fields (no catalog yet)
    if (serverConv.modelId === undefined && serverConv.personaId === undefined && serverConv.personaValues === undefined) {
      return false;
    }

    const server = serverConv.selection;
    const local = localConv.selection;
    const changed = server.modelId !== local.modelId ||
      server.personaId !== local.personaId ||
      JSON.stringify(server.personaValues) !== JSON.stringify(local.personaValues);
    if (!changed) return false;

    localConv.modelId = server.modelId;
    localConv.personaId = server.personaId;
    localConv.personaValues = server.personaValues;
    return true;
  }

  async delete(id: string): Promise<void> {
    try {
      // Call API to delete conversation on backend
      await this.apiService.deleteConversation(id);
      
      // Use transactional delete to remove conversation and all messages atomically from local DB
      await this.dbService.deleteConversationWithMessages(id);
      
      const conversations = this.cache$.getValue();
      const filtered = conversations.filter(c => c.id !== id);
      this.updateCache(filtered);
      
      // Delete sync metadata from memory and database
      this.syncMetadata.delete(id);
      await this.dbService.deleteSyncMetadata(id);
    } catch (error) {
      console.error('Failed to delete conversation:', error);
      throw error;
    }
  }

  async computeHash(conversations: Conversation[]): Promise<string> {
    const data = conversations
      .map(c => ({
        id: c.id,
        name: c.name,
        participants: c.participants,
        updatedAt: c.updatedAt
      }))
      .sort((a, b) => new Date(a.updatedAt).getTime() - new Date(b.updatedAt).getTime());
    
    return this.computeHashFromString(JSON.stringify(data));
  }

  async sync(): Promise<SyncResult> {
    return this.syncRecent(5);
  }

  /**
   * Sync the most recent N conversations with message caching
   */
  async syncRecent(count: number, messageLimit: number = 20): Promise<SyncResult> {
    this.isSyncing$.next(true);
    
    try {
      const serverConversations = await this.apiService.getConversations();
      
      if (serverConversations.length === 0) {
        return {
          success: true,
          itemsUpdated: 0
        };
      }
      
      // The N with the newest messages
      const recentConversations = [...serverConversations]
        .sort(Conversation.compareByActivity)
        .slice(0, count);
      
      let itemsUpdated = 0;
      
      for (const serverConv of recentConversations) {
        const updated = await this.syncConversation(serverConv.id, messageLimit);
        if (updated) itemsUpdated++;
      }
      
      // Update local conversation list
      await this.mergeServerConversations(serverConversations);
      
      this.lastSyncTime = new Date();
      
      return {
        success: true,
        itemsUpdated
      };
    } catch (error) {
      console.error('Conversation sync failed:', error);
      return {
        success: false,
        itemsUpdated: 0,
        errors: [error instanceof Error ? error.message : 'Unknown error']
      };
    } finally {
      this.isSyncing$.next(false);
    }
  }

  /**
   * Sync a specific conversation with smart caching
   * @param conversationId - The conversation to sync
   * @param messageLimit - Number of recent messages to keep in cache (default: 20)
   */
  async syncConversation(conversationId: string, messageLimit: number = 20): Promise<boolean> {
    // Check if sync is already in progress for this conversation
    const existingSync = this.activeSyncs.get(conversationId);
    if (existingSync) {
      console.log(`Sync already in progress for conversation ${conversationId}, waiting...`);
      return existingSync;
    }

    // Create sync promise and store it
    const syncPromise = this.performSync(conversationId, messageLimit);
    this.activeSyncs.set(conversationId, syncPromise);

    try {
      const result = await syncPromise;
      return result;
    } finally {
      // Clean up after sync completes
      this.activeSyncs.delete(conversationId);
    }
  }

  /**
   * Bring a conversation in this browser up to what the server has: its model, agent and marks,
   * and its newest messages, merged by id.
   *
   * It asks for the newest messages every time, not for "the ones after my newest": an answer
   * carries the second its generation started in (the same as the message it answers) and is
   * stored only when it is complete, so a browser that synced in between never got it.
   * Merging by id also brings what another device edited, and removes what it deleted.
   */
  private async performSync(conversationId: string, messageLimit: number): Promise<boolean> {
    const metadata = this.syncMetadata.get(conversationId);

    // Skip sync if we just sent a message (within last 5 seconds)
    if (metadata?.lastMessageSent) {
      const timeSinceLastMessage = Date.now() - metadata.lastMessageSent.getTime();
      if (timeSinceLastMessage < 5000) {
        console.log(`Skipping sync for ${conversationId} - message sent ${timeSinceLastMessage}ms ago`);
        return false;
      }
    }

    try {
      const serverConversations = await this.apiService.getConversations();
      const serverConv = serverConversations.find(c => c.id === conversationId);
      if (!serverConv) {
        return false;
      }

      // A conversation this browser doesn't have yet (started on another device)
      let localConv = await this.dbService.getConversation(conversationId);
      if (!localConv) {
        localConv = Conversation.fromApiResponse(serverConv);
        await this.dbService.addConversation(localConv);
      }

      // Model and persona may have been switched, messages written on another device
      const selectionChanged = await this.mergeSelection(localConv, serverConv);
      if (localConv.mergeLastMessageAt(serverConv.lastMessageAt) || selectionChanged) {
        await this.save(localConv);
      }

      const requestedAt = Date.now();
      const serverMessages = await this.apiService.getConversationMessages(conversationId, messageLimit);

      // What this browser changed itself while the request ran is newer than the answer: the
      // next sync merges, this one would put back a deleted message or an edited one's old text
      if (this.messageRepository.changedLocallySince(conversationId, requestedAt)) {
        console.log(`Skipping the merge for ${conversationId} - messages changed here meanwhile`);
        return false;
      }

      const removedIds = removedOnServer(metadata?.serverMessageIds ?? [], serverMessages);
      const changed = await this.dbService.applyServerMessages(
        conversationId, serverMessages, removedIds, mergeServerMessage
      );

      const updatedMetadata: ConversationSyncMetadata = {
        id: conversationId,
        lastSynced: new Date(),
        serverMessageIds: serverMessages.map(m => m.id),
        expiresAt: this.calculateExpirationDate(),
        // Read again: a message may have been sent while the request ran
        lastMessageSent: this.syncMetadata.get(conversationId)?.lastMessageSent
      };
      this.syncMetadata.set(conversationId, updatedMetadata);
      await this.dbService.saveSyncMetadata(updatedMetadata);

      if (changed) {
        await this.updateConversationExpiration(conversationId, true);
        await this.messageRepository.refreshConversationCache(conversationId);
      }
      return changed;
    } catch (error) {
      // Nothing was written: the merge is one transaction
      console.error(`Failed to sync conversation ${conversationId}:`, error);
      return false;
    }
  }

  /**
   * Merge server conversations with local ones
   */
  private async mergeServerConversations(serverConversations: any[]): Promise<void> {
    const localConversations = await this.dbService.getAllConversations();
    const localConvMap = new Map(localConversations.map(c => [c.id, c]));
    
    const merged: Conversation[] = [];
    
    // Add or update conversations from server
    for (const serverConv of serverConversations) {
      const localConv = localConvMap.get(serverConv.id);
      
      if (!localConv) {
        // New conversation from server
        const newConv = Conversation.fromApiResponse(serverConv);
        try {
          await this.dbService.addConversation(newConv);
          merged.push(newConv);
        } catch (error) {
          // If it already exists (can happen during sync), try to get it
          const existingConv = await this.dbService.getConversation(newConv.id);
          if (existingConv) {
            merged.push(existingConv);
          } else {
            console.error(`Failed to add conversation ${newConv.id}:`, error);
          }
        }
      } else {
        // Existing conversation - only update timestamp if server has newer timestamp
        // This prevents updating just from viewing/syncing
        let changed = await this.mergeSelection(localConv, serverConv);
        // Messages written on another device move it up
        if (localConv.mergeLastMessageAt(serverConv.lastMessageAt)) {
          changed = true;
        }
        if (serverConv.updatedAt && new Date(serverConv.updatedAt) > new Date(localConv.updatedAt)) {
          localConv.updatedAt = new Date(serverConv.updatedAt);
          changed = true;
        }
        if (changed) {
          await this.dbService.updateConversation(localConv);
        }
        merged.push(localConv);
      }
    }
    
    // Keep local-only conversations (not on server)
    for (const localConv of localConversations) {
      if (!serverConversations.some(s => s.id === localConv.id)) {
        merged.push(localConv);
      }
    }
    
    this.updateCache(merged);
  }

  /**
   * Load conversations from IndexedDB on startup
   */
  private async loadConversations(): Promise<void> {
    try {
      const conversations = await this.dbService.getAllConversations();
      this.updateCache(conversations);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  }

  /**
   * Load sync metadata from IndexedDB on startup
   */
  private async loadSyncMetadata(): Promise<void> {
    try {
      const metadataList = await this.dbService.getAllSyncMetadata();
      this.syncMetadata.clear();
      for (const metadata of metadataList) {
        this.syncMetadata.set(metadata.id, metadata);
      }
      console.log(`Loaded sync metadata for ${metadataList.length} conversations`);
    } catch (error) {
      console.error('Failed to load sync metadata:', error);
    }
  }

  /**
   * Clear all cached data
   * Used during logout to ensure clean state
   */
  clearCache(): void {
    this.updateCache([]);
    this.syncMetadata.clear();
    this.activeSyncs.clear();
    // Note: We don't clear persistent sync metadata here
    // It will be cleared when user data is cleared from DB
  }

  /**
   * Update conversation expiration date
   * @param updateTimestamp - Whether to update the updatedAt timestamp (only for actual changes)
   */
  private async updateConversationExpiration(conversationId: string, updateTimestamp: boolean = false): Promise<void> {
    const conversation = await this.dbService.getConversation(conversationId);
    if (conversation) {
      // Only update the updatedAt timestamp if there were actual changes
      if (updateTimestamp) {
        conversation.updatedAt = new Date();
      }
      // Always update in DB to persist any sync metadata changes
      await this.dbService.updateConversation(conversation);
    }
  }

  /**
   * Calculate expiration date (30 days from now)
   */
  private calculateExpirationDate(): Date {
    const expirationDate = new Date();
    expirationDate.setDate(expirationDate.getDate() + 30);
    return expirationDate;
  }

  /**
   * Clean up expired conversations
   */
  async cleanupExpiredConversations(): Promise<number> {
    const now = new Date();
    let deletedCount = 0;
    
    for (const [convId, metadata] of this.syncMetadata) {
      if (metadata.expiresAt && metadata.expiresAt < now) {
        await this.delete(convId);
        deletedCount++;
      }
    }
    
    return deletedCount;
  }

  /**
   * Load messages for a conversation with caching limit
   * This method is used by UI to load only recent messages into memory
   */
  async loadConversationMessages(conversationId: string, limit: number = 20): Promise<Message[]> {
    const conversation = await this.dbService.getConversation(conversationId);
    if (!conversation) return [];

    // Get latest messages directly from DB
    try {
      const messages = await this.dbService.getMessagesByConversationId(conversationId);
      if (messages !== undefined) {
        messages.sort(Message.compare);
        return [...messages.slice(-limit)];
      }
      return [];
    } catch (error) {
      console.error('Error getting messages:', error);
      return [];
    }
  }

  /**
   * The messages before a message, for scrolling up: the ones this browser has, and the page
   * before its oldest from the server once it has no more.
   * @param conversationId - The conversation ID
   * @param beforeId - The id of the oldest message the chat shows (the id is the order)
   * @param limit - Number of messages to load
   */
  async loadOlderMessages(
    conversationId: string,
    beforeId: number,
    limit: number = 20
  ): Promise<Message[]> {
    // The messages the server stored, oldest first (the ones only this browser has come last)
    const stored = (await this.dbService.getMessagesByConversationId(conversationId))
      .filter(msg => !msg.isLocal)
      .sort(Message.compare);

    const olderMessages = stored.filter(msg => msg.id < beforeId).slice(-limit);

    // If we found fewer messages than requested, try to fetch more from server
    if (olderMessages.length < limit && stored.length > 0) {
      const fetchedMore = await this.fetchOlderMessages(conversationId, stored[0].id);
      if (fetchedMore) {
        // Recursively call to get the newly fetched messages
        return this.loadOlderMessages(conversationId, beforeId, limit);
      }
    }

    return olderMessages;
  }

  /**
   * Mark that we just sent a message to prevent immediate re-sync
   */
  async markMessageSent(conversationId: string): Promise<void> {
    const metadata = this.syncMetadata.get(conversationId);
    const now = new Date();
    
    if (metadata) {
      metadata.lastMessageSent = now;
      await this.dbService.saveSyncMetadata(metadata);
    } else {
      const newMetadata: ConversationSyncMetadata = {
        id: conversationId,
        lastSynced: now,
        lastMessageSent: now
      };
      this.syncMetadata.set(conversationId, newMetadata);
      await this.dbService.saveSyncMetadata(newMetadata);
    }
  }

  /**
   * Fetch the page of messages before a message from the server (the user scrolled up to
   * messages this browser doesn't have).
   * @returns whether the server had any
   */
  private async fetchOlderMessages(conversationId: string, beforeId: number): Promise<boolean> {
    try {
      const messages = await this.apiService.getConversationMessages(conversationId, 20, beforeId);
      if (messages.length === 0) {
        return false;
      }

      await this.dbService.applyServerMessages(conversationId, messages, [], mergeServerMessage);

      // Refresh the message repository cache
      await this.messageRepository.refreshConversationCache(conversationId);

      return true;
    } catch (error) {
      console.error(`Failed to sync older messages for ${conversationId}:`, error);
      return false;
    }
  }
}