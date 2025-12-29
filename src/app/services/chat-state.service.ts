// src/app/services/chat-state.service.ts
import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Observable, Subject, combineLatest, firstValueFrom, lastValueFrom, of, Subscription } from 'rxjs';
import { map, shareReplay, switchMap, takeUntil, tap, catchError, filter, timeout } from 'rxjs/operators';
import { ConversationRepository } from '../repositories/conversation.repository';
import { MessageRepository } from '../repositories/message.repository';
import { SyncEngineService } from '../repositories/sync-engine.service';
import { Conversation } from '../data/objects/conversation';
import { Message, AgentContent, AgentStep } from '../data/objects/message';
import { FilePreview, UploadStatus } from '../data/objects/file-preview';
import { ApiService } from './api.service';
import { AuthService } from '../auth/auth.service';
import { SettingsStateService } from './settings-state.service';
import { UIStateService } from './ui-state.service';
import { NotificationService } from './notification.service';
import { StreamingService, StreamEvent, MessageStartEventData, ErrorEventData } from './streaming.service';
import { environment } from '../environments/environment';
import { HttpClient } from '@angular/common/http';
import { DBService } from '../data/db.service';
import { AppSettings } from '../models/settings.model';

export interface ChatState {
  activeConversation: Conversation | null;
  messages: Message[];
  isNewConversation: boolean;
  isLoading: boolean;
  error: string | null;
  hasReachedEnd?: boolean;
  streamingMessage: Message<AgentContent> | null;
  isStreaming: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class ChatStateService implements OnDestroy {
  private destroy$ = new Subject<void>();

  // State management
  private activeConversationId$ = new BehaviorSubject<string | null>(null);
  public isNewConversation$ = new BehaviorSubject<boolean>(false);
  private isLoading$ = new BehaviorSubject<boolean>(false);
  private error$ = new BehaviorSubject<string | null>(null);
  private hasReachedEnd$ = new BehaviorSubject<boolean>(false);

  // Streaming state
  private streamingMessage$ = new BehaviorSubject<Message<AgentContent> | null>(null);
  private isStreaming$ = new BehaviorSubject<boolean>(false);
  private streamingSubscription: Subscription | null = null;

  // Current conversation stream
  public activeConversation$: Observable<Conversation | null> = this.activeConversationId$.pipe(
    switchMap(id => {
      if (id === null || id === '0') {
        return of(new Conversation('0', 0, 'New Chat', ['user', 'Assistant']));
      }
      return this.conversationRepository.getById(id);
    }),
    shareReplay(1)
  );

  // Messages for active conversation
  public messages$: Observable<Message[]> = this.activeConversationId$.pipe(
    switchMap(id => {
      if (id === null || id === '0') {
        return of([]);
      }
      return this.messageRepository.getByConversationId(id);
    }),
    map(messages => messages.sort((a, b) => {
      const timeDiff = (a.time?.getTime() || 0) - (b.time?.getTime() || 0);
      // Use ID as tie-breaker when timestamps are within 1 second
      // This fixes ordering issues caused by timestamp precision loss in SSE streaming
      if (Math.abs(timeDiff) < 1000) {
        return a.id - b.id;
      }
      return timeDiff;
    })),
    shareReplay(1)
  );

  // All conversations
  public conversations$ = this.conversationRepository.getAll().pipe(
    map(conversations => conversations.sort((a, b) => {
      const dateA = a.updatedAt || a.createdAt || new Date(0);
      const dateB = b.updatedAt || b.createdAt || new Date(0);
      return dateB.getTime() - dateA.getTime();
    })),
    shareReplay(1)
  );

  // Sync status
  public isSyncing$ = combineLatest([
    this.conversationRepository.syncing$,
    this.messageRepository.syncing$
  ]).pipe(
    map(([convSyncing, msgSyncing]) => convSyncing || msgSyncing),
    shareReplay(1)
  );

  // Complete chat state
  public state$: Observable<ChatState> = combineLatest([
    this.activeConversation$,
    this.messages$,
    this.isNewConversation$,
    this.isLoading$,
    this.error$,
    this.hasReachedEnd$,
    this.streamingMessage$,
    this.isStreaming$
  ]).pipe(
    map(([activeConversation, messages, isNewConversation, isLoading, error, hasReachedEnd, streamingMessage, isStreaming]) => ({
      activeConversation,
      messages,
      isNewConversation,
      isLoading,
      error,
      hasReachedEnd,
      streamingMessage,
      isStreaming
    })),
    shareReplay(1)
  );

  constructor(
    private conversationRepository: ConversationRepository,
    private messageRepository: MessageRepository,
    private syncEngine: SyncEngineService,
    private apiService: ApiService,
    private authService: AuthService,
    private settingsState: SettingsStateService,
    private uiState: UIStateService,
    private notificationService: NotificationService,
    private streamingService: StreamingService,
    private http: HttpClient,
    private dbService: DBService
  ) {
    this.initializeService();
    this.listenToAuthChanges();
  }

  private async initializeService(): Promise<void> {
    // Load initial conversation
    const conversations = await firstValueFrom(this.conversations$);
    if (conversations.length > 0) {
      await this.loadConversation(conversations[0].id);
    } else {
      await this.createNewConversation();
    }
  }

  private listenToAuthChanges(): void {
    // Listen for user changes (logout/login)
    this.authService.currentUser$
      .pipe(
        takeUntil(this.destroy$),
        filter(user => user !== null) // Only react to actual user changes
      )
      .subscribe(user => {
        // When user changes (after logout/login), reset to new conversation
        if (user.email.includes('guest')) {
          console.log('Guest user detected, resetting chat state');
          this.resetState();
        }
      });
  }

  /**
   * Load a specific conversation
   */
  async loadConversation(conversationId: string): Promise<void> {
    this.isLoading$.next(true);
    this.error$.next(null);
    this.hasReachedEnd$.next(false); // Reset when loading a conversation

    try {
      if (conversationId === '0') {
        this.isNewConversation$.next(true);
        this.activeConversationId$.next('0');
      } else {
        this.isNewConversation$.next(false);
        this.activeConversationId$.next(conversationId);

        // Trigger sync for this conversation if online
        if (await this.isBackendAvailable()) {
          this.conversationRepository.syncConversation(conversationId).catch(console.error);
        }
      }

      this.uiState.setActiveConversation(conversationId);
    } catch (error) {
      this.error$.next('Failed to load conversation');
      console.error('Failed to load conversation:', error);
    } finally {
      this.isLoading$.next(false);
    }
  }

  /**
   * Create a new conversation (not saved until first message)
   */
  async createNewConversation(): Promise<void> {
    this.isNewConversation$.next(true);
    this.activeConversationId$.next('0');
    this.uiState.setActiveConversation('0');
  }

  /**
   * Send a text message and stream the AI response
   */
  async sendMessage(content: string, roleName: string = 'user'): Promise<void> {
    // Create conversation if it's new
    if (this.isNewConversation$.getValue()) {
      await this.createConversationFromFirstMessage(content);
    }

    const conversationId = this.activeConversationId$.getValue()!;

    // Create and save user message
    const userMessage = Message.createText(
      {
        id: Math.floor(Date.now() / 1000),
        conversationId,
        roleName,
        time: new Date()
      },
      content
    );

    // Mark that we're sending a message to prevent immediate re-sync
    await this.conversationRepository.markMessageSent(conversationId);

    // Save user message to repository
    await this.messageRepository.save(userMessage);

    // Start streaming the AI response
    await this._streamResponse(conversationId);
  }

  /**
   * Send a message with file attachments
   */
  async sendMessageWithFiles(
    content: string,
    files: FilePreview[],
    roleName: string = 'user'
  ): Promise<void> {
    // Create conversation if needed
    if (this.isNewConversation$.getValue()) {
      const title = content.length > 30 ? content.substring(0, 27) + '...' : content || 'New conversation with files';
      await this.createConversationFromFirstMessage(title);
    }

    const conversationId = this.activeConversationId$.getValue()!;

    // Handle file uploads
    const backendAvailable = await this.isBackendAvailable();
    if (backendAvailable && files.length > 0) {
      // Check for pending files
      const pendingFiles = files.filter(f => f.uploadStatus === UploadStatus.PENDING);

      if (pendingFiles.length > 0) {
        try {
          const uploadedFileIds = await this.apiService.uploadFiles(pendingFiles);

          pendingFiles.forEach((f, index) => {
            const uploadResponse = uploadedFileIds[index];
            f.uploadStatus = UploadStatus.COMPLETED;
            f.id = uploadResponse?.fileId || `file-${Date.now()}-${Math.random()}`;
            f.transcript = uploadResponse?.transcript || f.transcript;
          });
        } catch (error) {
          console.error('Error uploading files:', error);
          pendingFiles.forEach(f => {
            f.uploadStatus = UploadStatus.FAILED;
            f.error = 'Upload failed';
          });
        }
      }
    } else if (!backendAvailable && files.length > 0) {
      // Mark files for offline storage
      files.forEach(f => {
        if (f.uploadStatus !== UploadStatus.PENDING) {
          f.uploadStatus = UploadStatus.PENDING;
          f.id = f.id || `offline-${Date.now()}-${Math.random()}`;
          f.error = 'Waiting for connection';
        }
      });
    }

    // Create user message with file attachments
    const userMessage = Message.createText(
      {
        id: Math.floor(Date.now() / 1000),
        conversationId,
        roleName,
        time: new Date()
      },
      content,
      files
    );

    // Mark that we're sending a message to prevent immediate re-sync
    await this.conversationRepository.markMessageSent(conversationId);

    // Save user message to repository
    await this.messageRepository.save(userMessage);

    // Start streaming the AI response (backend will extract file attachments)
    await this._streamResponse(conversationId);
  }

  // Track pending voice message for async updates
  private pendingVoiceMessage: Message | null = null;

  /**
   * Add a voice message locally (for immediate display while transcription is pending)
   * This creates the message and displays it but doesn't send to backend yet.
   */
  async addLocalVoiceMessage(
    placeholderText: string,
    voiceFile: FilePreview
  ): Promise<void> {
    // Create conversation if needed
    if (this.isNewConversation$.getValue()) {
      await this.createConversationFromFirstMessage('Voice message');
    }

    const conversationId = this.activeConversationId$.getValue()!;

    // Create user message with voice file attachment
    const userMessage = Message.createText(
      {
        id: Math.floor(Date.now() / 1000),
        conversationId,
        roleName: 'user',
        time: new Date()
      },
      placeholderText,
      [voiceFile]
    );

    // Store reference to update later
    this.pendingVoiceMessage = userMessage;

    // Save to local repository only (skip backend sync)
    await this.messageRepository.save(userMessage, true); // skipSync = true
  }

  /**
   * Update a pending voice message with the real transcript and trigger AI response
   */
  async updateVoiceMessageAndRespond(
    voiceFile: FilePreview,
    transcript: string
  ): Promise<void> {
    if (!this.pendingVoiceMessage) {
      console.error('No pending voice message to update');
      return;
    }

    const conversationId = this.activeConversationId$.getValue()!;

    // Update message content with real transcript
    if (this.pendingVoiceMessage.isText()) {
      (this.pendingVoiceMessage.content as any).content = transcript;
    }

    // Update attachment with transcript
    const attachments = this.pendingVoiceMessage.attachments;
    if (attachments && attachments.length > 0) {
      attachments[0].transcript = voiceFile.transcript;
      attachments[0].uploadStatus = voiceFile.uploadStatus;
      attachments[0].id = voiceFile.id;
    }

    // Mark message as modified
    this.pendingVoiceMessage.version = (this.pendingVoiceMessage.version || 1) + 1;
    this.pendingVoiceMessage.lastModified = Math.floor(Date.now() / 1000);

    // Update in local repository
    await this.messageRepository.update(this.pendingVoiceMessage);

    // Mark that we're sending a message to prevent immediate re-sync
    await this.conversationRepository.markMessageSent(conversationId);

    // Clear the pending reference
    const messageToSync = this.pendingVoiceMessage;
    this.pendingVoiceMessage = null;

    // Now sync with backend (this will send the message)
    try {
      await this.apiService.sendMessage(messageToSync);
    } catch (error) {
      console.error('Failed to sync voice message with backend:', error);
      // Continue anyway - message is saved locally
    }

    // Start streaming the AI response
    await this._streamResponse(conversationId);
  }

  /**
   * Send a message and stream the AI response using SSE.
   * @deprecated Use sendMessage() instead - it now uses streaming by default.
   */
  async sendAndStreamResponse(content: string, roleName: string = 'user'): Promise<void> {
    // Delegate to sendMessage which now uses streaming
    await this.sendMessage(content, roleName);
  }

  /**
   * Handle individual stream events
   */
  private handleStreamEvent(event: StreamEvent, message: Message<AgentContent>): void {
    switch (event.type) {
      case 'message_start':
        // Message envelope received - apply metadata immediately
        const startData = event.data as MessageStartEventData;
        message.id = startData.messageId;
        message.time = new Date(startData.time * 1000);
        message.roleName = startData.roleName;
        // Status remains 'thinking' until we get steps or tokens
        break;

      case 'step':
        // Add the new step to the message
        message.content.steps.push(event.data as AgentStep);
        message.content.status = 'thinking';
        break;

      case 'token':
        // Append the token to the response content
        message.content.content += event.data as string;
        message.content.status = 'responding';
        break;

      case 'done':
        // Mark as complete (ID should already be set from message_start)
        message.content.status = 'complete';
        break;

      case 'error':
        // Handle error
        message.content.status = 'error';
        message.content.error = (event.data as ErrorEventData).error;
        break;
    }

    // Emit the updated message (create a new reference to trigger change detection)
    this.streamingMessage$.next(message);
  }

  /**
   * Handle stream errors
   */
  private async handleStreamError(error: any, message: Message<AgentContent>): Promise<void> {
    console.error('Stream error:', error);

    // Update message to show error state
    message.content.status = 'error';
    message.content.error = error.message || 'An error occurred during streaming';

    // Save the error message to the repository
    await this.messageRepository.save(message);

    // Clean up streaming state
    this.isStreaming$.next(false);
    this.streamingMessage$.next(null);

    this.notificationService.showError('Failed to generate response');
  }

  /**
   * Handle stream completion
   */
  private async handleStreamComplete(message: Message<AgentContent>): Promise<void> {
    // Only save if the message completed successfully
    if (message.content.status === 'complete') {
      // The message was already saved on the backend by the SSE endpoint,
      // but we need to save it locally to IndexedDB
      await this.messageRepository.save(message);

      // Update conversation timestamp
      const conversation = await firstValueFrom(this.activeConversation$);
      if (conversation && conversation.id !== '0') {
        conversation.updatedAt = new Date();
        await this.conversationRepository.save(conversation);
      }

      this.notificationService.showSuccess('Response generated');
    }

    // Clean up streaming state
    this.isStreaming$.next(false);
    this.streamingMessage$.next(null);
    this.streamingSubscription = null;
  }

  /**
   * Cancel an ongoing streaming response.
   * Saves the partial response if any content was generated.
   */
  async cancelStreaming(): Promise<void> {
    // Unsubscribe first to stop receiving more tokens
    if (this.streamingSubscription) {
      this.streamingSubscription.unsubscribe();
      this.streamingSubscription = null;
    }

    // Get the current streaming message before clearing
    const streamingMessage = this.streamingMessage$.getValue();

    // Save partial response if we have any content
    if (streamingMessage && streamingMessage.content) {
      const hasContent = streamingMessage.content.content?.trim().length > 0;
      const hasSteps = streamingMessage.content.steps?.length > 0;

      if (hasContent || hasSteps) {
        // Mark as complete (user intentionally stopped it)
        streamingMessage.content.status = 'complete';

        // Save to IndexedDB
        await this.messageRepository.save(streamingMessage);

        // Update conversation timestamp
        const conversation = await firstValueFrom(this.activeConversation$);
        if (conversation && conversation.id !== '0') {
          conversation.updatedAt = new Date();
          await this.conversationRepository.save(conversation);
        }
      }
    }

    // Clean up streaming state
    this.isStreaming$.next(false);
    this.streamingMessage$.next(null);
  }

  /**
   * Internal helper to start streaming an AI response.
   * Creates a placeholder agent message and streams the response.
   */
  private async _streamResponse(conversationId: string): Promise<void> {
    // Create placeholder agent message for streaming
    const agentMessage = Message.createAgent(conversationId, [], '', 'thinking');
    this.streamingMessage$.next(agentMessage);
    this.isStreaming$.next(true);

    // Cancel any existing streaming subscription
    if (this.streamingSubscription) {
      this.streamingSubscription.unsubscribe();
    }

    // Start streaming
    this.streamingSubscription = this.streamingService
      .streamAgentResponse(conversationId, 'Assistant')
      .subscribe({
        next: (event) => this.handleStreamEvent(event, agentMessage),
        error: (error) => this.handleStreamError(error, agentMessage),
        complete: () => this.handleStreamComplete(agentMessage)
      });
  }

  /**
   * Get the current streaming message (for direct access)
   */
  getStreamingMessage(): Message<AgentContent> | null {
    return this.streamingMessage$.getValue();
  }

  /**
   * Check if streaming is currently in progress
   */
  isCurrentlyStreaming(): boolean {
    return this.isStreaming$.getValue();
  }

  /**
   * Generate AI response
   */
  async generateMessage(participant: string = 'Assistant'): Promise<void> {
    // Check backend availability
    const backendAvailable = await this.isBackendAvailable();
    if (!backendAvailable) {
      const offlineMessage = Message.createText(
        {
          id: Math.floor(Date.now() / 1000),
          conversationId: this.activeConversationId$.getValue()!,
          roleName: participant,
          time: new Date()
        },
        'Sorry, I cannot generate responses while offline. Please check your connection.'
      );
      await this.messageRepository.save(offlineMessage);
      return;
    }

    try {
      const messages = await firstValueFrom(this.messages$);
      const lastMessage = messages[messages.length - 1];
      const settings = await firstValueFrom(
        this.settingsState.settings$.pipe(
          timeout(5000), // 5 seconds timeout
          catchError(() => of(null)) // fallback to null
        )
      );

      if (!lastMessage || !settings) {
        throw new Error('No message or settings available');
      }

      const generatedMessage = await this.apiService.generateMessage(lastMessage, participant, settings);
      await this.messageRepository.save(generatedMessage);

      this.authService.setGuestLimitReached(false);
    } catch (error: any) {
      if (error.status === 429) {
        console.error('Guest limit reached:', error);
        const detail = error.error?.detail;
        let resetTimeMessage = 'Please try again later.';
        if (detail && detail.includes('after')) {
          const resetTimeISO = detail.split('after ')[1];
          if (resetTimeISO) {
            const resetDate = new Date(resetTimeISO);
            const formattedTime = resetDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            resetTimeMessage = `You have reached your request limit. You can generate more answers after ${formattedTime}.`;
          }
        }
        this.authService.setGuestLimitReached(true, resetTimeMessage);
      } else {
        console.error('Error generating message:', error);
        const errorMessage = Message.createText(
          {
            id: Math.floor(Date.now() / 1000),
            conversationId: this.activeConversationId$.getValue()!,
            roleName: participant,
            time: new Date()
          },
          'Sorry, I encountered an error while generating a response. Please try again.'
        );
        await this.messageRepository.save(errorMessage);
      }
      throw error;
    }
  }

  /**
   * Update (patch) a message with conflict resolution
   */
  async patchMessage(messageId: number, content: string, maxRetries: number = 3): Promise<void> {
    const messages = await firstValueFrom(this.messages$);
    const message = messages.find(m => m.id === messageId);

    if (!message || !message.isText()) {
      throw new Error('Message not found or not a text message');
    }

    const conversationId = this.activeConversationId$.getValue()!;
    let retryCount = 0;
    let success = false;

    while (retryCount < maxRetries && !success) {
      try {
        // Update via API if online
        if (await this.isBackendAvailable()) {
          await this.apiService.patchMessage(conversationId, messageId, content, message.version);
          success = true;
        } else {
          // Offline mode - just update locally
          success = true;
        }

        // Create updated message with incremented version
        const updatedMessage = Message.createText(
          {
            id: message.id,
            conversationId: message.conversationId,
            roleName: message.roleName,
            time: message.time,
            version: message.version + 1,
            lastModified: Math.floor(Date.now() / 1000)
          },
          content,
          message.content.attachments
        );

        await this.messageRepository.update(updatedMessage);

        // Show success notification if we had retries
        if (retryCount > 0) {
          this.notificationService.showSuccess('Message updated successfully after resolving conflicts');
        }

      } catch (error: any) {
        if (error.status === 409) {
          // Version conflict - refresh and retry
          console.warn(`Version conflict for message ${messageId}, retrying...`);
          retryCount++;

          if (retryCount < maxRetries) {
            this.notificationService.showWarning(
              `Version conflict detected. Refreshing and retrying... (Attempt ${retryCount}/${maxRetries})`
            );

            // Refresh the conversation to get latest versions
            await this.syncEngine.syncConversation(conversationId);
            const refreshedMessages = await firstValueFrom(this.messages$);
            const refreshedMessage = refreshedMessages.find(m => m.id === messageId);

            if (refreshedMessage) {
              // Update our local reference for next retry
              message.version = refreshedMessage.version;
            }
          } else {
            const errorMsg = 'Unable to update message due to version conflicts. Please refresh and try again.';
            this.error$.next(errorMsg);
            this.notificationService.showError(errorMsg);
            throw new Error(errorMsg);
          }
        } else {
          throw error;
        }
      }
    }
  }

  /**
   * Delete a message
   */
  async deleteMessage(messageId: number): Promise<void> {
    await this.messageRepository.delete(messageId);
  }

  /**
   * Regenerate a message using streaming.
   * Deletes the old AI message and streams a new response.
   */
  async regenerateMessage(message: Message): Promise<void> {
    if (!message.id || !message.conversationId) {
      throw new Error('Message ID and conversation ID are required');
    }

    // Check if it's an AI message
    if (message.roleName === 'user') {
      throw new Error('Can only regenerate AI messages');
    }

    this.error$.next(null);

    try {
      // Delete the old AI message immediately
      await this.messageRepository.delete(message.id);

      // Start streaming a new response (backend will use the last user message)
      await this._streamResponse(message.conversationId);
    } catch (error) {
      console.error('Error regenerating message:', error);
      this.error$.next('Failed to regenerate message');
      this.notificationService.showError('Failed to regenerate message');
      throw error;
    }
  }

  /**
   * Rate a message (thumbs up or thumbs down) or remove rating
   */
  async rateMessage(message: Message, rating: number | null): Promise<void> {
    if (!message.id || !message.conversationId) {
      throw new Error('Message ID and conversation ID are required');
    }

    // Validate rating value (null is allowed to remove rating)
    if (rating !== null && rating !== 0 && rating !== 1) {
      throw new Error('Rating must be 0 (thumbs down), 1 (thumbs up), or null to remove rating');
    }

    try {
      // Update the rating via repository
      await this.messageRepository.rateMessage(
        message.id,
        message.conversationId,
        rating
      );

      // The message repository will automatically update the cache and trigger
      // the messages$ observable to emit the new value

      // Show success notification
      const ratingText = rating === null ? 'rating removed' : (rating === 1 ? 'liked' : 'disliked');
      this.notificationService.showSuccess(`Message ${ratingText}`);
    } catch (error) {
      console.error('Error rating message:', error);
      this.error$.next('Failed to rate message');
      this.notificationService.showError('Failed to rate message');
      throw error;
    }
  }

  /**
   * Update conversation (e.g., rename)
   */
  async updateConversation(conversation: Conversation): Promise<void> {
    try {
      // Use the new updateConversation method that calls the API
      await this.conversationRepository.updateConversation(conversation.id, conversation.name);
      // The activeConversation$ will automatically update via the observable chain
    } catch (error) {
      console.error('Failed to update conversation:', error);
      throw error;
    }
  }

  /**
   * Delete a conversation
   */
  async deleteConversation(conversationId: string): Promise<void> {
    await this.conversationRepository.delete(conversationId);

    // If we deleted the active conversation, load a new one
    if (this.activeConversationId$.getValue() === conversationId) {
      const remaining = await firstValueFrom(this.conversations$);
      if (remaining.length > 0) {
        await this.loadConversation(remaining[0].id);
      } else {
        await this.createNewConversation();
      }
    }
  }

  /**
   * Force sync
   */
  async syncNow(): Promise<void> {
    const conversationId = this.activeConversationId$.getValue();
    if (conversationId && conversationId !== '0') {
      await this.syncEngine.syncConversation(conversationId);
    }
  }

  /**
   * Upload pending files
   */
  async uploadPendingFiles(): Promise<void> {
    await this.messageRepository.uploadPendingFiles();
  }

  /**
   * Get active conversation ID
   */
  getActiveConversationId(): string | null {
    return this.activeConversationId$.getValue();
  }

  /**
   * Load older messages for the active conversation
   */
  async loadOlderMessages(beforeTime: Date, limit: number = 20): Promise<Message[]> {
    const conversationId = this.activeConversationId$.getValue();
    if (!conversationId || conversationId === '0') {
      return [];
    }

    const messages = await this.conversationRepository.loadOlderMessages(conversationId, beforeTime, limit);

    // If we got fewer messages than requested, we've likely reached the beginning
    if (messages.length < limit) {
      this.hasReachedEnd$.next(true);
    }

    return messages;
  }

  /**
   * Helper: Create conversation from first message
   */
  private async createConversationFromFirstMessage(title: string): Promise<void> {
    const backendAvailable = await this.isBackendAvailable();
    let conversation: Conversation;

    if (!backendAvailable) {
      // Create local-only conversation with proper UUID
      conversation = new Conversation(
        this.dbService.generateUUID(),
        0,
        title,
        ['user', 'Assistant']
      );
    } else {
      // Try to create on server
      const newConvData = new Conversation('', 0, title, ['user', 'Assistant']);
      try {
        conversation = await this.apiService.createConversation(newConvData);
      } catch (error) {
        console.error('Failed to create conversation on server:', error);
        // Fallback to local with UUID
        conversation = new Conversation(
          this.dbService.generateUUID(),
          0,
          title,
          ['user', 'Assistant']
        );
      }
    }

    await this.conversationRepository.save(conversation);
    this.isNewConversation$.next(false);
    this.activeConversationId$.next(conversation.id);
    this.uiState.setActiveConversation(conversation.id);
  }

  /**
   * Helper: Check backend availability
   */
  private async isBackendAvailable(): Promise<boolean> {
    try {
      await lastValueFrom(
        this.http.get(`${environment.apiUrl}/api/auth/me`, { withCredentials: true })
      );
      return true;
    } catch (error) {
      return false;
    }
  }

  /**
   * Handle rate limit errors
   */
  private handleRateLimitError(error: string): void {
    let resetTimeMessage = 'Please try again later.';
    if (error.includes('after')) {
      const resetTimeMatch = error.match(/after\s+(\S+)/);
      if (resetTimeMatch) {
        try {
          const resetDate = new Date(resetTimeMatch[1]);
          const formattedTime = resetDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          resetTimeMessage = `You have reached your request limit. You can generate more answers after ${formattedTime}.`;
        } catch (e) {
          console.error('Error parsing reset time:', e);
        }
      }
    }
    this.authService.setGuestLimitReached(true, resetTimeMessage);
  }

  /**
   * Reset all state - used during logout
   */
  resetState(): void {
    console.log('Resetting chat state...');
    // Reset to new conversation state
    this.activeConversationId$.next('0');
    this.isNewConversation$.next(true);
    this.isLoading$.next(false);
    this.error$.next(null);

    // Clear any existing conversation/messages by triggering the observables
    // The observables will automatically emit empty arrays for conversation '0'
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();

    // Cancel any ongoing streaming
    this.cancelStreaming();
  }
}
