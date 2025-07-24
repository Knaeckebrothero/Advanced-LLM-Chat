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
}

@Injectable({
  providedIn: 'root'
})
export class ConversationRepository extends BaseRepository<Conversation> {
  private syncMetadata = new Map<string, ConversationSyncMetadata>();
  
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
      await this.dbService.deleteConversation(id);
      
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
    const metadata = this.syncMetadata.get(conversationId);
    
    try {
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
        // Just update expiration date
        await this.updateConversationExpiration(conversationId);
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
      await this.mergeMessages(conversationId, localMessages, serverMessages, pendingMessages);
      
      // Update conversation expiration date (30 days from now)
      await this.updateConversationExpiration(conversationId);
      
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
        // Existing conversation - update timestamp from server
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
  }

  /**
   * Merge local and server messages with conflict resolution
   * Server-first strategy but preserves pending messages
   */
  private async mergeMessages(
    conversationId: string,
    localMessages: Message[],
    serverMessages: Message[],
    pendingMessages: Message[]
  ): Promise<void> {
    // Create maps for efficient lookup
    const serverMessageMap = new Map(serverMessages.map(msg => [msg.id, msg]));
    const pendingMessageIds = new Set(pendingMessages.map(msg => msg.id));
    
    // Log only in debug mode or when there are issues
    if (pendingMessages.length > 0 || localMessages.length > 100) {
      console.log(`Merging messages for conversation ${conversationId}:`);
      console.log(`- Local messages: ${localMessages.length}`);
      console.log(`- Server messages: ${serverMessages.length}`);
      console.log(`- Pending messages: ${pendingMessages.length}`);
    }
    
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
    
    for (const localMsg of localMessages) {
      const msgTime = new Date(localMsg.time).getTime();
      // Check if it's older than server messages AND not already in server response AND not pending
      if (msgTime < oldestServerMessageTime && 
          !serverMessageMap.has(localMsg.id) && 
          !pendingMessageIds.has(localMsg.id)) {
        mergedMessages.push(localMsg);
      }
    }
    
    // Sort messages by time
    mergedMessages.sort((a, b) => 
      new Date(a.time).getTime() - new Date(b.time).getTime()
    );
    
    // Check for duplicates
    const messageIds = new Set<number>();
    const duplicates: number[] = [];
    for (const msg of mergedMessages) {
      if (messageIds.has(msg.id)) {
        duplicates.push(msg.id);
      }
      messageIds.add(msg.id);
    }
    if (duplicates.length > 0) {
      console.error(`WARNING: Found duplicate message IDs in merge: ${duplicates.join(', ')}`);
      // Remove duplicates, keeping the first occurrence
      const uniqueMessages: Message[] = [];
      const seenIds = new Set<number>();
      for (const msg of mergedMessages) {
        if (!seenIds.has(msg.id)) {
          uniqueMessages.push(msg);
          seenIds.add(msg.id);
        }
      }
      mergedMessages.length = 0;
      mergedMessages.push(...uniqueMessages);
    }
    
    // Update database with merged messages using transaction for atomicity
    try {
      await this.dbService.replaceConversationMessages(conversationId, mergedMessages);
    } catch (error) {
      console.error('Failed to replace messages in database:', error);
      console.error('Merged messages:', mergedMessages);
      throw error;
    }
  }

  /**
   * Update conversation expiration date
   */
  private async updateConversationExpiration(conversationId: string): Promise<void> {
    const conversation = await this.dbService.getConversation(conversationId);
    if (conversation) {
      // Update the updatedAt timestamp which serves as activity indicator
      conversation.updatedAt = new Date();
      await this.save(conversation);
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
      
      // Add older messages to local database
      for (const msg of olderServerMessages) {
        await this.dbService.addMessage(msg);
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