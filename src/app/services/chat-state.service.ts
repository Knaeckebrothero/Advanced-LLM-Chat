import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Observable, Subject, combineLatest, firstValueFrom, lastValueFrom, from, of } from 'rxjs';
import { map, shareReplay, switchMap, takeUntil, tap, catchError, filter } from 'rxjs/operators';
import { ConversationRepository } from '../repositories/conversation.repository';
import { MessageRepository } from '../repositories/message.repository';
import { SyncEngineService } from '../repositories/sync-engine.service';
import { Conversation } from '../data/objects/conversation';
import { Message } from '../data/objects/message';
import { FilePreview, UploadStatus } from '../data/objects/file-preview';
import { ApiService } from './api.service';
import { AuthService } from '../auth/auth.service';
import { SettingsStateService } from './settings-state.service';
import { UIStateService } from './ui-state.service';
import { environment } from '../environments/environment';
import { HttpClient } from '@angular/common/http';

export interface ChatState {
  activeConversation: Conversation | null;
  messages: Message[];
  isNewConversation: boolean;
  isLoading: boolean;
  error: string | null;
}

@Injectable({
  providedIn: 'root'
})
export class ChatStateService implements OnDestroy {
  private destroy$ = new Subject<void>();
  
  // State management
  private activeConversationId$ = new BehaviorSubject<string | null>(null);
  private isNewConversation$ = new BehaviorSubject<boolean>(false);
  private isLoading$ = new BehaviorSubject<boolean>(false);
  private error$ = new BehaviorSubject<string | null>(null);
  
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
    map(messages => messages.sort((a, b) => (a.time?.getTime() || 0) - (b.time?.getTime() || 0))),
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
    this.error$
  ]).pipe(
    map(([activeConversation, messages, isNewConversation, isLoading, error]) => ({
      activeConversation,
      messages,
      isNewConversation,
      isLoading,
      error
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
    private http: HttpClient
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
   * Send a text message
   */
  async sendMessage(content: string, roleName: string = 'user'): Promise<void> {
    const activeConversation = await firstValueFrom(this.activeConversation$);
    
    // Create conversation if it's new
    if (this.isNewConversation$.getValue()) {
      await this.createConversationFromFirstMessage(content);
    }
    
    const conversationId = this.activeConversationId$.getValue()!;
    
    // Create message
    const message = Message.createText(
      {
        id: Math.floor(Date.now() / 1000),
        conversationId,
        roleName,
        time: new Date()
      },
      content
    );
    
    // Get settings for AI generation
    const settings = await firstValueFrom(this.settingsState.settings);
    
    // Use the new combined send and generate method
    const aiMessage = await this.messageRepository.sendAndGenerate(message, true, settings);
    
    // Update conversation timestamp
    const conversation = await firstValueFrom(this.activeConversation$);
    if (conversation && conversation.id !== '0') {
      conversation.updatedAt = new Date();
      await this.conversationRepository.save(conversation);
    }
    
    // Handle guest limit if AI generation failed
    if (!aiMessage && await this.isBackendAvailable()) {
      // Check if it's a rate limit issue
      const error = (message as any).syncError;
      if (error && error.includes('429')) {
        this.handleRateLimitError(error);
      }
    }
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
            f.uploadStatus = UploadStatus.COMPLETED;
            f.id = uploadedFileIds[index] || `file-${Date.now()}-${Math.random()}`;
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
    
    // Create and save message
    const message = Message.createText(
      {
        id: Math.floor(Date.now() / 1000),
        conversationId,
        roleName,
        time: new Date()
      },
      content,
      files
    );
    
    await this.messageRepository.save(message);
    
    // Update conversation
    const conversation = await firstValueFrom(this.activeConversation$);
    if (conversation && conversation.id !== '0') {
      conversation.updatedAt = new Date();
      await this.conversationRepository.save(conversation);
    }
  }
  
  /**
   * Send a voice message
   */
  async sendVoiceMessage(
    audioBlob: Blob,
    duration: number,
    mimeType: string = 'audio/webm',
    roleName: string = 'user'
  ): Promise<void> {
    // Create conversation if needed
    if (this.isNewConversation$.getValue()) {
      await this.createConversationFromFirstMessage('Voice conversation');
    }
    
    const conversationId = this.activeConversationId$.getValue()!;
    
    // Convert blob to base64
    const base64Audio = await this.blobToBase64(audioBlob);
    
    // Create and save message
    const message = Message.createVoice(
      {
        id: Math.floor(Date.now() / 1000),
        conversationId,
        roleName,
        time: new Date()
      },
      base64Audio,
      duration,
      mimeType
    );
    
    await this.messageRepository.save(message);
    
    // Update conversation
    const conversation = await firstValueFrom(this.activeConversation$);
    if (conversation && conversation.id !== '0') {
      conversation.updatedAt = new Date();
      await this.conversationRepository.save(conversation);
    }
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
      const settings = await firstValueFrom(this.settingsState.settings);
      
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
   * Update (patch) a message
   */
  async patchMessage(messageId: number, content: string): Promise<void> {
    const messages = await firstValueFrom(this.messages$);
    const message = messages.find(m => m.id === messageId);
    
    if (!message || !message.isText()) {
      throw new Error('Message not found or not a text message');
    }
    
    const conversationId = this.activeConversationId$.getValue()!;
    
    // Update via API if online
    if (await this.isBackendAvailable()) {
      await this.apiService.patchMessage(conversationId, messageId, content);
    }
    
    // Create updated message
    const updatedMessage = Message.createText(
      {
        id: message.id,
        conversationId: message.conversationId,
        roleName: message.roleName,
        time: message.time
      },
      content,
      message.content.attachments
    );
    
    await this.messageRepository.update(updatedMessage);
  }
  
  /**
   * Delete a message
   */
  async deleteMessage(messageId: number): Promise<void> {
    await this.messageRepository.delete(messageId);
  }
  
  /**
   * Regenerate a message
   */
  async regenerateMessage(message: Message): Promise<void> {
    const messages = await firstValueFrom(this.messages$);
    const messageIndex = messages.findIndex(m => m.id === message.id);
    
    if (messageIndex === -1) {
      throw new Error('Message not found');
    }
    
    // Delete this message and all after it
    const messagesToDelete = messages.slice(messageIndex);
    
    for (const msg of messagesToDelete) {
      await this.deleteMessage(msg.id);
    }
    
    // Generate new response
    await this.generateMessage(message.roleName);
  }
  
  /**
   * Update conversation (e.g., rename)
   */
  async updateConversation(conversation: Conversation): Promise<void> {
    conversation.updatedAt = new Date();
    await this.conversationRepository.save(conversation);
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
   * Helper: Create conversation from first message
   */
  private async createConversationFromFirstMessage(title: string): Promise<void> {
    const backendAvailable = await this.isBackendAvailable();
    
    let conversation: Conversation;
    
    if (!backendAvailable) {
      // Create local-only conversation with timestamp-based UUID
      conversation = new Conversation(
        `local-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
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
          `local-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
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
      const response = await lastValueFrom(
        this.http.get(`${environment.apiUrl}/api/llms`, { withCredentials: true })
      );
      return true;
    } catch (error) {
      console.warn('Backend not available:', error);
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
   * Helper: Convert blob to base64
   */
  private blobToBase64(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const base64String = reader.result as string;
        const base64Data = base64String.split(',')[1];
        resolve(base64Data);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
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
  }
}