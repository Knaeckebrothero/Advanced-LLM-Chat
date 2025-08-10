// src/app/services/chat-state.service.ts
import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Observable, Subject, combineLatest, firstValueFrom, lastValueFrom, from, of } from 'rxjs';
import { map, shareReplay, switchMap, takeUntil, tap, catchError, filter, timeout } from 'rxjs/operators';
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
import { NotificationService } from './notification.service';
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
}

@Injectable({
  providedIn: 'root'
})
export class ChatStateService implements OnDestroy {
  private destroy$ = new Subject<void>();

  private activeConversationId$ = new BehaviorSubject<string | null>(null);
  private isNewConversation$ = new BehaviorSubject<boolean>(false);
  private isLoading$ = new BehaviorSubject<boolean>(false);
  private error$ = new BehaviorSubject<string | null>(null);
  private hasReachedEnd$ = new BehaviorSubject<boolean>(false);

  public activeConversation$: Observable<Conversation | null> = this.activeConversationId$.pipe(
    switchMap(id => {
      if (id === null || id === '0') {
        return of(new Conversation('0', 0, 'New Chat', ['user', 'Assistant']));
      }
      return this.conversationRepository.getById(id);
    }),
    shareReplay(1)
  );

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

  public conversations$ = this.conversationRepository.getAll().pipe(
    map(conversations => conversations.sort((a, b) => {
      const dateA = a.updatedAt || a.createdAt || new Date(0);
      const dateB = b.updatedAt || b.createdAt || new Date(0);
      return dateB.getTime() - dateA.getTime();
    })),
    shareReplay(1)
  );

  public isSyncing$ = combineLatest([
    this.conversationRepository.syncing$,
    this.messageRepository.syncing$
  ]).pipe(
    map(([convSyncing, msgSyncing]) => convSyncing || msgSyncing),
    shareReplay(1)
  );

  public state$: Observable<ChatState> = combineLatest([
    this.activeConversation$,
    this.messages$,
    this.isNewConversation$,
    this.isLoading$,
    this.error$,
    this.hasReachedEnd$
  ]).pipe(
    map(([activeConversation, messages, isNewConversation, isLoading, error, hasReachedEnd]) => ({
      activeConversation,
      messages,
      isNewConversation,
      isLoading,
      error,
      hasReachedEnd
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
    private http: HttpClient,
    private dbService: DBService
  ) {
    this.initializeService();
    this.listenToAuthChanges();
  }

  private async initializeService(): Promise<void> {
    const conversations = await firstValueFrom(this.conversations$);
    if (conversations.length > 0) {
      await this.loadConversation(conversations[0].id);
    } else {
      await this.createNewConversation();
    }
  }

  private listenToAuthChanges(): void {
    this.authService.currentUser$
      .pipe(
        takeUntil(this.destroy$),
        filter(user => user !== null)
      )
      .subscribe(user => {
        if (user.email.includes('guest')) {
          this.resetState();
        }
      });
  }

  async loadConversation(conversationId: string): Promise<void> {
    this.isLoading$.next(true);
    this.error$.next(null);
    this.hasReachedEnd$.next(false);
    try {
      if (conversationId === '0') {
        this.isNewConversation$.next(true);
        this.activeConversationId$.next('0');
      } else {
        this.isNewConversation$.next(false);
        this.activeConversationId$.next(conversationId);
        if (await this.isBackendAvailable()) {
          this.conversationRepository.syncConversation(conversationId).catch(console.error);
        }
      }
      this.uiState.setActiveConversation(conversationId);
    } catch (error) {
      this.error$.next('Failed to load conversation');
    } finally {
      this.isLoading$.next(false);
    }
  }

  async createNewConversation(): Promise<void> {
    this.isNewConversation$.next(true);
    this.activeConversationId$.next('0');
    this.uiState.setActiveConversation('0');
  }

  async sendMessageWithFiles(
    content: string,
    files: FilePreview[],
    roleName: string = 'user'
  ): Promise<void> {
    // 1. Handle new conversation creation
    if (this.isNewConversation$.getValue()) {
      const title = content.length > 30 ? content.substring(0, 27) + '...' : content || 'New conversation';
      await this.createConversationFromFirstMessage(title);
    }
    const conversationId = this.activeConversationId$.getValue()!;

    // 2. Handle file uploads (if any)
    if (await this.isBackendAvailable() && files.length > 0) {
      const pendingFiles = files.filter(f => f.uploadStatus === UploadStatus.PENDING);
      if (pendingFiles.length > 0) {
        try {
          const uploadedFileIds = await this.apiService.uploadFiles(pendingFiles);
          pendingFiles.forEach((f, index) => {
            f.uploadStatus = UploadStatus.COMPLETED;
            f.id = uploadedFileIds[index] || `file-${Date.now()}-${Math.random()}`;
          });
        } catch (error) {
          pendingFiles.forEach(f => {
            f.uploadStatus = UploadStatus.FAILED;
            f.error = 'Upload failed';
          });
        }
      }
    }

    // 3. Create the message object
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

    // 4. Send the message and generate a response
    await this.conversationRepository.markMessageSent(conversationId);
    const aiMessage = await this.messageRepository.sendAndGenerate(message, true);

    // 5. Update conversation timestamp
    const conversation = await firstValueFrom(this.activeConversation$);
    if (conversation && conversation.id !== '0') {
      conversation.updatedAt = new Date();
      await this.conversationRepository.save(conversation);
    }

    // 6. Handle rate limit errors
    if (!aiMessage && await this.isBackendAvailable()) {
      const error = (message as any).syncError;
      if (error && error.includes('429')) {
        this.handleRateLimitError(error);
      }
    }
  }

  async sendVoiceMessage(
    audioBlob: Blob,
    duration: number,
    mimeType: string = 'audio/webm',
    roleName: string = 'user'
  ): Promise<void> {
    if (this.isNewConversation$.getValue()) {
      await this.createConversationFromFirstMessage('Voice conversation');
    }
    const conversationId = this.activeConversationId$.getValue()!;
    const base64Audio = await this.blobToBase64(audioBlob);
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
    const conversation = await firstValueFrom(this.activeConversation$);
    if (conversation && conversation.id !== '0') {
      conversation.updatedAt = new Date();
      await this.conversationRepository.save(conversation);
    }
  }

  async generateMessage(participant: string = 'Assistant'): Promise<void> {
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
        this.settingsState.settings$.pipe(timeout(5000), catchError(() => of(null)))
      );
      if (!lastMessage || !settings) {
        throw new Error('No message or settings available');
      }
      const generatedMessage = await this.apiService.generateMessage(lastMessage, participant, settings);
      await this.messageRepository.save(generatedMessage);
      this.authService.setGuestLimitReached(false);
    } catch (error: any) {
      if (error.status === 429) {
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
        if (await this.isBackendAvailable()) {
          await this.apiService.patchMessage(conversationId, messageId, content, message.version);
          success = true;
        } else {
          success = true;
        }
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
        if (retryCount > 0) {
          this.notificationService.showSuccess('Message updated successfully after resolving conflicts');
        }
      } catch (error: any) {
        if (error.status === 409) {
          retryCount++;
          if (retryCount < maxRetries) {
            this.notificationService.showWarning(`Version conflict detected. Refreshing and retrying... (Attempt ${retryCount}/${maxRetries})`);
            await this.syncEngine.syncConversation(conversationId);
            const refreshedMessages = await firstValueFrom(this.messages$);
            const refreshedMessage = refreshedMessages.find(m => m.id === messageId);
            if (refreshedMessage) {
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

  async deleteMessage(messageId: number): Promise<void> {
    await this.messageRepository.delete(messageId);
  }

  async regenerateMessage(message: Message): Promise<void> {
    if (!message.id || !message.conversationId) {
      throw new Error('Message ID and conversation ID are required');
    }
    if (message.roleName === 'user') {
      throw new Error('Can only regenerate AI messages');
    }
    this.isLoading$.next(true);
    this.error$.next(null);
    try {
      await this.messageRepository.regenerateMessage(message.id, message.conversationId);
      this.notificationService.showSuccess('Message regenerated successfully');
    } catch (error) {
      this.error$.next('Failed to regenerate message');
      this.notificationService.showError('Failed to regenerate message');
      throw error;
    } finally {
      this.isLoading$.next(false);
    }
  }

  async rateMessage(message: Message, rating: number | null): Promise<void> {
    if (!message.id || !message.conversationId) {
      throw new Error('Message ID and conversation ID are required');
    }
    if (rating !== null && rating !== 0 && rating !== 1) {
      throw new Error('Rating must be 0 (thumbs down), 1 (thumbs up), or null to remove rating');
    }
    try {
      await this.messageRepository.rateMessage(message.id, message.conversationId, rating);
      const ratingText = rating === null ? 'rating removed' : (rating === 1 ? 'liked' : 'disliked');
      this.notificationService.showSuccess(`Message ${ratingText}`);
    } catch (error) {
      this.error$.next('Failed to rate message');
      this.notificationService.showError('Failed to rate message');
      throw error;
    }
  }

  async updateConversation(conversation: Conversation): Promise<void> {
    try {
      await this.conversationRepository.updateConversation(conversation.id, conversation.name);
    } catch (error) {
      console.error('Failed to update conversation:', error);
      throw error;
    }
  }

  async deleteConversation(conversationId: string): Promise<void> {
    await this.conversationRepository.delete(conversationId);
    if (this.activeConversationId$.getValue() === conversationId) {
      const remaining = await firstValueFrom(this.conversations$);
      if (remaining.length > 0) {
        await this.loadConversation(remaining[0].id);
      } else {
        await this.createNewConversation();
      }
    }
  }

  async syncNow(): Promise<void> {
    const conversationId = this.activeConversationId$.getValue();
    if (conversationId && conversationId !== '0') {
      await this.syncEngine.syncConversation(conversationId);
    }
  }

  async uploadPendingFiles(): Promise<void> {
    await this.messageRepository.uploadPendingFiles();
  }

  getActiveConversationId(): string | null {
    return this.activeConversationId$.getValue();
  }

  async loadOlderMessages(beforeTime: Date, limit: number = 20): Promise<Message[]> {
    const conversationId = this.activeConversationId$.getValue();
    if (!conversationId || conversationId === '0') {
      return [];
    }
    const messages = await this.conversationRepository.loadOlderMessages(conversationId, beforeTime, limit);
    if (messages.length < limit) {
      this.hasReachedEnd$.next(true);
    }
    return messages;
  }

  private async createConversationFromFirstMessage(title: string): Promise<void> {
    const backendAvailable = await this.isBackendAvailable();
    let conversation: Conversation;
    if (!backendAvailable) {
      conversation = new Conversation(this.dbService.generateUUID(), 0, title, ['user', 'Assistant']);
    } else {
      const newConvData = new Conversation('', 0, title, ['user', 'Assistant']);
      try {
        conversation = await this.apiService.createConversation(newConvData);
      } catch (error) {
        conversation = new Conversation(this.dbService.generateUUID(), 0, title, ['user', 'Assistant']);
      }
    }
    await this.conversationRepository.save(conversation);
    this.isNewConversation$.next(false);
    this.activeConversationId$.next(conversation.id);
    this.uiState.setActiveConversation(conversation.id);
  }

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

  private blobToBase64(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        resolve((reader.result as string).split(',')[1]);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  resetState(): void {
    this.activeConversationId$.next('0');
    this.isNewConversation$.next(true);
    this.isLoading$.next(false);
    this.error$.next(null);
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}
