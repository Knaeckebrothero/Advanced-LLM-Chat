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
   */
  async save(message: MessageWithSyncStatus): Promise<MessageWithSyncStatus> {
    try {
      // Handle file uploads if message has attachments
      if (message.isText() && message.attachments?.length) {
        await this.handleFileAttachments(message);
      }
      
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
          await this.syncMessage(message);
          message.syncStatus = 'synced';
        } catch (error) {
          message.syncStatus = 'failed';
          message.syncError = error instanceof Error ? error.message : 'Unknown error';
        }
      }
      
      return message;
    } catch (error) {
      console.error('Failed to save message:', error);
      throw error;
    }
  }

  /**
   * Update an existing message
   */
  async update(message: MessageWithSyncStatus): Promise<MessageWithSyncStatus> {
    try {
      await this.dbService.updateMessage(message);
      
      // Update cache
      const conversationId = message.conversationId;
      if (this.conversationCaches.has(conversationId)) {
        const cache = this.conversationCaches.get(conversationId)!;
        const current = cache.getValue();
        const index = current.findIndex(m => m.id === message.id);
        if (index >= 0) {
          current[index] = message;
          cache.next([...current]);
        }
      }
      
      // Sync with backend if online
      if (await this.isOnline() && message.syncStatus === 'pending') {
        await this.syncMessage(message);
      }
      
      return message;
    } catch (error) {
      console.error('Failed to update message:', error);
      throw error;
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
      
      await this.dbService.deleteMessage(numId);
      
      // Update cache
      const conversationId = message.conversationId;
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
        } catch (error) {
          console.error('Failed to sync message deletion:', error);
        }
      }
    } catch (error) {
      console.error('Failed to delete message:', error);
      throw error;
    }
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
          f.uploadStatus = UploadStatus.COMPLETED;
          f.id = uploadedFileIds[index] || f.id;
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
          f.uploadStatus = UploadStatus.COMPLETED;
          f.id = uploadedFileIds[index] || f.id;
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
      const serverId = await this.apiService.sendMessage(message);
      
      // Update the message ID with the server-assigned ID if it's different
      if (serverId && serverId !== message.id) {
        const oldId = message.id;
        message.id = serverId;
        
        // Update in IndexedDB with new ID
        await this.dbService.deleteMessage(oldId);
        await this.dbService.addMessage(message);
        
        // Update cache
        const conversationId = message.conversationId;
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
          const result = await this.apiService.sendAndGenerateMessage(message, generateResponse, settings);
          
          // Update user message ID if different
          if (result.userMessageId && result.userMessageId !== message.id) {
            const oldId = message.id;
            message.id = result.userMessageId;
            
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
            await this.save(aiMessage);
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
}