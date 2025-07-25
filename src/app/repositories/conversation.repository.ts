import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable, from, of } from 'rxjs';
import { map, catchError } from 'rxjs/operators';
import { BaseRepository, SyncResult } from './base.repository';
import { DBService } from '../data/db.service';
import { ApiService } from '../services/api.service';
import { Conversation } from '../data/objects/conversation';
import { Message } from '../data/objects/message';
import { MessageRepository } from './message.repository';

export interface ConversationSyncMetadata {
  id: string;
  lastSynced: Date;
  messageCount: number;
  hash: number;
  lastMessageTimestamp?: Date;
  expiresAt?: Date;
  lastMessageSent?: Date;  // Track when we last sent a message
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

  async delete(id: string): Promise<void> {
    try {
      // Use transactional delete to remove conversation and all messages atomically
      await this.dbService.deleteConversationWithMessages(id);
      
      const conversations = this.cache$.getValue();
      const filtered = conversations.filter(c => c.id !== id);
      this.updateCache(filtered);
      
      this.syncMetadata.delete(id);
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
      
      // Sort by updated date descending (most recent first) and take top N
      const recentConversations = serverConversations
        .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
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
    
    // Create backup before sync operation
    let backup: { conversation: Conversation | undefined; messages: Message[] } | null = null;
    
    try {
      // Backup current state before any modifications
      backup = await this.dbService.backupConversationData(conversationId);
      // Get local conversation
      let localConv = await this.dbService.getConversation(conversationId);
      
      // If conversation doesn't exist locally, we need to fetch it from server first
      if (!localConv) {
        const serverConversations = await this.apiService.getConversations();
        const serverConvData = serverConversations.find(c => c.id === conversationId);
        
        if (!serverConvData) {
          console.error(`Conversation ${conversationId} not found on server`);
          return false;
        }
        
        // Create local conversation from server data
        localConv = Conversation.fromApiResponse(serverConvData);
        await this.dbService.addConversation(localConv);
      }
      
      // Get all local messages for this conversation
      const localMessages = await this.dbService.getMessagesByConversationId(conversationId);
      
      // Identify messages with pending sync status
      const pendingMessages = localMessages.filter(msg => {
        // Check if message has sync metadata (from MessageRepository)
        const msgWithStatus = msg as any;
        return msgWithStatus.syncStatus === 'pending' || msgWithStatus.syncStatus === 'failed';
      });
      
      // Get server conversation data
      const serverConversations = await this.apiService.getConversations();
      const serverConv = serverConversations.find(c => c.id === conversationId);
      
      if (!serverConv) return false;
      
      // Compute local hash for comparison
      const localHash = await localConv.computeHash(this.dbService);
      const hasNoMessages = localMessages.length === 0;
      
      // Determine if we need to sync
      const needsSync = hasNoMessages || 
                       localHash !== serverConv.hashsum ||
                       (metadata && await this.isConversationStale(metadata));
      
      if (!needsSync) {
        // Just update expiration date without changing updatedAt
        await this.updateConversationExpiration(conversationId, false);
        return false;
      }
      
      console.log(`Syncing conversation ${conversationId} (no messages: ${hasNoMessages}, hash mismatch: ${localHash !== serverConv.hashsum})`);
      
      // Fetch recent messages from server (using the caching limit)
      const serverMessages = await this.apiService.getConversationMessages(
        conversationId,
        messageLimit
      );
      
      console.log(`Fetched ${serverMessages.length} messages from server for conversation ${conversationId}`);
      
      // Merge messages using server-first strategy but preserve pending
      const messagesChanged = await this.mergeMessages(conversationId, localMessages, serverMessages, pendingMessages);
      
      // Update conversation expiration date (30 days from now)
      // Only update timestamp if messages actually changed
      await this.updateConversationExpiration(conversationId, messagesChanged);
      
      // Refresh the message repository cache to trigger UI update
      await this.messageRepository.refreshConversationCache(conversationId);
      
      // Update sync metadata with enhanced information
      const lastServerMessage = serverMessages.length > 0 ? 
        serverMessages[serverMessages.length - 1] : null;
      
      this.syncMetadata.set(conversationId, {
        id: conversationId,
        lastSynced: new Date(),
        messageCount: serverMessages.length,
        hash: serverConv.hashsum || 0,
        lastMessageTimestamp: lastServerMessage ? new Date(lastServerMessage.time) : undefined,
        expiresAt: this.calculateExpirationDate()
      });
      
      return true;
    } catch (error) {
      console.error(`Failed to sync conversation ${conversationId}:`, error);
      
      // Restore from backup if sync failed and we have a backup
      if (backup) {
        try {
          console.log(`Restoring conversation ${conversationId} from backup after sync failure`);
          await this.dbService.restoreConversationData(conversationId, backup);
          console.log(`Successfully restored conversation ${conversationId} from backup`);
        } catch (restoreError) {
          console.error(`Failed to restore conversation ${conversationId} from backup:`, restoreError);
        }
      }
      
      return false;
    }
  }

  /**
   * Check if a conversation is stale (older than 24 hours)
   */
  private async isConversationStale(metadata: ConversationSyncMetadata): Promise<boolean> {
    const now = new Date();
    const diffHours = (now.getTime() - metadata.lastSynced.getTime()) / (1000 * 60 * 60);
    return diffHours > 24;
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
        if (serverConv.updatedAt && new Date(serverConv.updatedAt) > new Date(localConv.updatedAt)) {
          localConv.updatedAt = new Date(serverConv.updatedAt);
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
   * Clear all cached data
   * Used during logout to ensure clean state
   */
  clearCache(): void {
    this.updateCache([]);
    this.syncMetadata.clear();
    this.activeSyncs.clear();
  }

  /**
   * Merge local and server messages with conflict resolution
   * Server-first strategy but preserves pending messages
   * @returns true if messages were actually changed
   */
  private async mergeMessages(
    conversationId: string,
    localMessages: Message[],
    serverMessages: Message[],
    pendingMessages: Message[]
  ): Promise<boolean> {
    // Create maps for efficient lookup
    const serverMessageMap = new Map(serverMessages.map(msg => [msg.id, msg]));
    const pendingMessageIds = new Set(pendingMessages.map(msg => msg.id));
    
    // Log merge details
    console.log(`Merging messages for conversation ${conversationId}:`);
    console.log(`- Local messages: ${localMessages.length}`);
    console.log(`- Server messages: ${serverMessages.length} (limit: ${serverMessages.length > 0 ? '20 most recent' : 'N/A'})`);
    console.log(`- Pending messages: ${pendingMessages.length}`);
    
    // Messages to keep
    const mergedMessages: Message[] = [];
    
    // 1. Add all server messages (these are authoritative)
    mergedMessages.push(...serverMessages);
    
    // 2. Add pending messages that aren't in server response
    for (const pendingMsg of pendingMessages) {
      if (!serverMessageMap.has(pendingMsg.id)) {
        mergedMessages.push(pendingMsg);
      }
    }
    
    // 3. Keep older local messages that aren't in the server response
    // (these might be messages beyond the messageLimit we fetched)
    const oldestServerMessageTime = serverMessages.length > 0 
      ? new Date(serverMessages[0].time).getTime()
      : Number.MAX_SAFE_INTEGER;
    
    let preservedOlderMessages = 0;
    for (const localMsg of localMessages) {
      const msgTime = new Date(localMsg.time).getTime();
      // Check if it's older than server messages AND not already in server response AND not pending
      if (msgTime < oldestServerMessageTime && 
          !serverMessageMap.has(localMsg.id) && 
          !pendingMessageIds.has(localMsg.id)) {
        mergedMessages.push(localMsg);
        preservedOlderMessages++;
      }
    }
    
    if (preservedOlderMessages > 0) {
      console.log(`- Preserved ${preservedOlderMessages} older messages from local storage`);
    }
    
    // Sort messages by time
    mergedMessages.sort((a, b) => 
      new Date(a.time).getTime() - new Date(b.time).getTime()
    );
    
    // Remove duplicates - this is critical to prevent duplicate messages in UI
    const uniqueMessages: Message[] = [];
    const seenIds = new Set<number>();
    const seenContents = new Map<string, Message>(); // Track by content+time for better dedup
    let duplicateCount = 0;
    
    for (const msg of mergedMessages) {
      // Create a unique key based on message content and time
      const contentKey = `${msg.time.toISOString()}_${msg.roleName}_${msg.getDisplayContent()}`;
      
      if (!seenIds.has(msg.id)) {
        // Check if we've seen this exact content at this exact time
        const existingMsg = seenContents.get(contentKey);
        if (existingMsg) {
          // Prefer the message with server ID (higher ID typically)
          if (msg.id > existingMsg.id) {
            // Remove the old one and add the new one
            const idx = uniqueMessages.findIndex(m => m.id === existingMsg.id);
            if (idx >= 0) {
              uniqueMessages[idx] = msg;
              seenIds.delete(existingMsg.id);
              seenIds.add(msg.id);
              seenContents.set(contentKey, msg);
            }
          }
          duplicateCount++;
        } else {
          uniqueMessages.push(msg);
          seenIds.add(msg.id);
          seenContents.set(contentKey, msg);
        }
      } else {
        duplicateCount++;
      }
    }
    
    if (duplicateCount > 0) {
      console.warn(`Removed ${duplicateCount} duplicate messages during merge for conversation ${conversationId}`);
    }
    
    // Sort both arrays by time for accurate comparison
    const sortedLocal = [...localMessages].sort((a, b) => 
      new Date(a.time).getTime() - new Date(b.time).getTime()
    );
    const sortedUnique = [...uniqueMessages].sort((a, b) => 
      new Date(a.time).getTime() - new Date(b.time).getTime()
    );
    
    // Check if messages actually changed
    const messagesChanged = sortedUnique.length !== sortedLocal.length ||
      !sortedUnique.every((msg, idx) => 
        sortedLocal[idx] && 
        msg.id === sortedLocal[idx].id &&
        msg.getDisplayContent() === sortedLocal[idx].getDisplayContent()
      );
    
    console.log(`- Merged result: ${uniqueMessages.length} messages (changed: ${messagesChanged})`);
    
    // Update database with merged messages using transaction for atomicity
    if (messagesChanged) {
      try {
        await this.dbService.replaceConversationMessages(conversationId, uniqueMessages);
      } catch (error) {
        console.error('Failed to replace messages in database:', error);
        console.error('Merged messages:', mergedMessages);
        throw error;
      }
    }
    
    return messagesChanged;
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
    
    // Get latest messages using the built-in method
    return conversation.getLatestMessages(this.dbService, limit);
  }

  /**
   * Load older messages for pagination (when user scrolls up)
   * @param conversationId - The conversation ID
   * @param beforeTimestamp - Load messages before this timestamp
   * @param limit - Number of messages to load
   */
  async loadOlderMessages(
    conversationId: string, 
    beforeTimestamp: Date, 
    limit: number = 20
  ): Promise<Message[]> {
    const allMessages = await this.dbService.getMessagesByConversationId(conversationId);
    
    // Filter messages before the timestamp
    const olderMessages = allMessages
      .filter(msg => new Date(msg.time) < beforeTimestamp)
      .sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime())
      .slice(0, limit);
    
    // Return in chronological order
    return olderMessages.reverse();
  }

  /**
   * Mark that we just sent a message to prevent immediate re-sync
   */
  markMessageSent(conversationId: string): void {
    const metadata = this.syncMetadata.get(conversationId);
    if (metadata) {
      metadata.lastMessageSent = new Date();
    } else {
      this.syncMetadata.set(conversationId, {
        id: conversationId,
        lastSynced: new Date(),
        messageCount: 0,
        hash: 0,
        lastMessageSent: new Date()
      });
    }
  }

  /**
   * Check if conversation needs to sync older messages from server
   * This happens when user scrolls to messages we don't have locally
   */
  async checkAndSyncOlderMessages(
    conversationId: string,
    oldestLocalTimestamp: Date
  ): Promise<boolean> {
    try {
      // Fetch older messages from server
      const olderServerMessages = await this.apiService.getConversationMessages(
        conversationId,
        20,
        oldestLocalTimestamp
      );
      
      if (olderServerMessages.length === 0) {
        return false;
      }
      
      // Add older messages to local database in a single transaction
      if (olderServerMessages.length > 0) {
        await this.dbService.addMessagesTransactional(olderServerMessages);
      }
      
      // Refresh the message repository cache
      await this.messageRepository.refreshConversationCache(conversationId);
      
      return true;
    } catch (error) {
      console.error(`Failed to sync older messages for ${conversationId}:`, error);
      return false;
    }
  }
}