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
  id: number;
  lastSynced: Date;
  messageCount: number;
  hash: number;
}

@Injectable({
  providedIn: 'root'
})
export class ConversationRepository extends BaseRepository<Conversation> {
  private syncMetadata = new Map<string | number, ConversationSyncMetadata>();
  
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

  getById(id: string | number): Observable<Conversation | null> {
    return this.cache$.pipe(
      map(conversations => conversations.find(c => c.id === id) || null)
    );
  }

  async save(conversation: Conversation): Promise<Conversation> {
    try {
      await this.dbService.addConversation(conversation);
      
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

  async delete(id: string | number): Promise<void> {
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
        participants: c.participants
      }))
      .sort((a, b) => a.id - b.id);
    
    return this.computeHashFromString(JSON.stringify(data));
  }

  async sync(): Promise<SyncResult> {
    return this.syncRecent(5);
  }

  /**
   * Sync the most recent N conversations
   */
  async syncRecent(count: number): Promise<SyncResult> {
    this.isSyncing$.next(true);
    
    try {
      const serverConversations = await this.apiService.getConversations();
      
      if (serverConversations.length === 0) {
        return {
          success: true,
          itemsUpdated: 0
        };
      }
      
      // Sort by ID descending (most recent first) and take top N
      const recentConversations = serverConversations
        .sort((a, b) => b.id - a.id)
        .slice(0, count);
      
      let itemsUpdated = 0;
      
      for (const serverConv of recentConversations) {
        const updated = await this.syncConversation(serverConv.id);
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
   * Sync a specific conversation if it's stale
   */
  async syncConversation(conversationId: string | number): Promise<boolean> {
    const metadata = this.syncMetadata.get(conversationId);
    
    // Check if conversation needs sync (older than 24 hours)
    if (metadata && !await this.isConversationStale(metadata)) {
      return false;
    }
    
    try {
      // Get local conversation to compute hash
      const localConv = await this.dbService.getConversation(conversationId);
      if (!localConv) return false;
      
      const localHash = await localConv.computeHash(this.dbService);
      
      // Get server conversation data
      const serverConversations = await this.apiService.getConversations();
      const serverConv = serverConversations.find(c => c.id === conversationId);
      
      if (!serverConv) return false;
      
      // Compare hashes
      if (localHash !== serverConv.hashsum) {
        console.log(`Syncing messages for conversation ${conversationId}`);
        
        // Fetch messages from server
        const serverMessages = await this.apiService.getConversationMessages(
          conversationId,
          50 // Get last 50 messages
        );
        
        // Update local database
        await this.dbService.deleteMessagesByConversationId(conversationId);
        for (const msg of serverMessages) {
          await this.dbService.addMessage(msg);
        }
        
        // Update sync metadata
        this.syncMetadata.set(conversationId, {
          id: conversationId,
          lastSynced: new Date(),
          messageCount: serverMessages.length,
          hash: serverConv.hashsum || 0
        });
        
        return true;
      }
      
      // Update sync time even if no changes
      this.syncMetadata.set(conversationId, {
        id: conversationId,
        lastSynced: new Date(),
        messageCount: 0,
        hash: localHash
      });
      
      return false;
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
        await this.dbService.addConversation(newConv);
        merged.push(newConv);
      } else {
        // Existing conversation
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
}