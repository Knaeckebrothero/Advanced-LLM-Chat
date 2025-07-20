import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { Message } from '../data/objects/message';
import { Conversation } from '../data/objects/conversation';
import { DBService } from '../data/db.service';
import { ApiService } from './api.service';
import { DisplayService } from '../sidebar/service/display.service';
import { FilePreview, UploadStatus } from '../data/objects/file-preview';
import { environment } from '../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class SyncService {
  // Sync state tracking
  private isSyncingSubject = new BehaviorSubject<boolean>(false);
  public isSyncing$ = this.isSyncingSubject.asObservable();

  private syncPromise: Promise<void> | null = null;

  // Connection monitoring
  private connectionCheckInterval: any;
  private lastConnectionState: boolean = true;

  constructor(
    private dbService: DBService,
    private apiService: ApiService,
    private displayService: DisplayService
  ) {
    // Set up connection monitoring for pending file uploads
    this.setupConnectionMonitoring();
  }

  /**
   * Sync with server in background (don't await)
   */
  public async syncInBackground() {
    // Check if backend is available first
    const backendAvailable = await this.isBackendAvailable();
    if (!backendAvailable) {
      console.log('Backend not available, skipping sync');
      return;
    }

    // Prevent concurrent syncs
    if (this.syncPromise) {
      console.log('Sync already in progress, waiting for completion');
      return this.syncPromise;
    }

    this.syncPromise = this.performSync();
    try {
      await this.syncPromise;
    } finally {
      this.syncPromise = null;
    }
  }

  /**
   * Main sync logic - move this to a separate sync service!
   */
  private async performSync() {
    this.isSyncingSubject.next(true);

    try {
      const serverConversationsData = await this.apiService.getConversations();

      // Convert plain objects to Conversation instances
      const serverConversations = serverConversationsData.map(data =>
        Conversation.fromApiResponse(data)
      );

      if (serverConversations.length === 0) {
        console.log('No conversations on server');
        return;
      }

      // Update conversation list if different
      await this.mergeServerConversations(serverConversations);

      // Only sync current conversation's messages
      const currentConvId = this.displayService.activeConversationId$.value;
      if (currentConvId && currentConvId !== 0) {
        const serverConv = serverConversations.find(c => c.id === currentConvId);
        if (serverConv) {
          await this.syncConversationIfNeeded(serverConv, currentConvId);
        }
      }
    } catch (error) {
      console.error('Background sync failed:', error);
      // Don't throw - we have local data
    } finally {
      this.isSyncingSubject.next(false);
    }
  }

  private async mergeServerConversations(serverConversations: Conversation[]) {
    // Get local conversations
    const localConversations = await this.dbService.getAllConversations();
    const localConvMap = new Map(localConversations.map(c => [c.id, c]));

    let hasChanges = false;

    // Check for new conversations from server
    for (const serverConv of serverConversations) {
      if (!localConvMap.has(serverConv.id)) {
        // This is a new conversation from server - we need to fetch its details
        // For now, we'll create a placeholder. In a real app, you'd fetch full details
        const newConv = new Conversation(
          serverConv.id,
          this.displayService.activeConversationId$.value || 1, // Use current user ID
          `Conversation ${serverConv.id}`,
          ['user', 'Assistant']
        );
        await this.dbService.addConversation(newConv);
        hasChanges = true;
      }
    }

    return hasChanges;
  }

  private async syncConversationIfNeeded(serverConv: any, currentConvId: number): Promise<Message[]> {
    // Get current conversation to compute hash
    const currentConversation = await this.dbService.getConversation(currentConvId);
    if (!currentConversation) {
      console.log('Current conversation not found in local DB');
      return [];
    }

    const localHash = await currentConversation.computeHash(this.dbService);

    if (localHash !== serverConv.hashsum) {
      console.log('Syncing messages for conversation:', serverConv.id);

      // Get server messages
      const serverMessages = await this.apiService.getConversationMessages(
        serverConv.id,
        50 // Get more messages during sync
      );

      // Update local database
      await this.dbService.deleteMessagesByConversationId(serverConv.id);
      for (const msg of serverMessages) {
        await this.dbService.addMessage(msg);
      }

      // Return the synced messages
      serverMessages.sort((a, b) => a.time!.getTime()! - b.time!.getTime());
      return serverMessages;
    }

    return [];
  }

  /**
   * Public method for manual sync of current conversation
   */
  public async syncCurrentConversation(): Promise<Message[]> {
    const currentConvId = this.displayService.activeConversationId$.value;
    if (currentConvId && currentConvId !== 0) {
      await this.syncInBackground();

      // Return current messages after sync
      const messages = await this.dbService.getMessagesByConversationId(currentConvId);
      return messages.sort((a, b) => a.time!.getTime()! - b.time!.getTime());
    }
    return [];
  }

  /**
   * Check if backend is available
   */
  private async isBackendAvailable(): Promise<boolean> {
    try {
      const response = await fetch(`${environment.apiUrl}/api/auth/me`, {
        method: 'GET',
        credentials: 'include'
      });
      return response.ok;
    } catch (error) {
      return false;
    }
  }

  /**
   * Set up connection monitoring for pending file uploads
   */
  private setupConnectionMonitoring() {
    this.connectionCheckInterval = setInterval(async () => {
      const isConnected = await this.isBackendAvailable();

      if (isConnected && !this.lastConnectionState) {
        console.log('Connection restored, checking for pending file uploads and triggering sync');
        await this.uploadPendingFiles();
        // Also trigger a sync
        this.syncInBackground();
      }

      this.lastConnectionState = isConnected;
    }, 30000);
  }

  /**
   * Check and upload any pending offline files when connection is restored
   */
  public async uploadPendingFiles(): Promise<void> {
    const backendAvailable = await this.isBackendAvailable();
    if (!backendAvailable) {
      console.log('Backend still not available, skipping pending file uploads');
      return;
    }

    // Get all messages with pending file uploads
    const allMessages = await this.dbService.getAllMessages();
    const messagesWithPendingFiles = allMessages.filter(msg =>
      msg.isText() &&
      msg.attachments?.some(f => f.uploadStatus === UploadStatus.PENDING)
    );

    console.log(`Found ${messagesWithPendingFiles.length} messages with pending file uploads`);

    for (const message of messagesWithPendingFiles) {
      if (!message.attachments) continue;

      const pendingFiles = message.attachments.filter(f => f.uploadStatus === UploadStatus.PENDING);
      if (pendingFiles.length === 0) continue;

      try {
        // Try to upload the pending files
        const uploadedFileIds = await this.apiService.uploadFiles(pendingFiles);

        // Update the message with new file IDs and status
        pendingFiles.forEach((f, index) => {
          f.uploadStatus = UploadStatus.COMPLETED;
          f.id = uploadedFileIds[index] || f.id;
          f.error = undefined;
        });

        // Update the message in the database
        await this.dbService.updateMessage(message);

        console.log(`Successfully uploaded files for message ${message.id}`);
      } catch (error) {
        console.error(`Failed to upload files for message ${message.id}:`, error);
        // Mark files as failed
        pendingFiles.forEach(f => {
          f.uploadStatus = UploadStatus.FAILED;
          f.error = 'Upload failed after retry';
        });
        await this.dbService.updateMessage(message);
      }
    }
  }

  /**
   * Cleanup resources
   */
  public destroy() {
    if (this.connectionCheckInterval) {
      clearInterval(this.connectionCheckInterval);
    }
  }
}
