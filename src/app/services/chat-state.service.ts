// src/app/services/chat-state.service.ts
import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Observable, Subject, combineLatest, firstValueFrom, lastValueFrom, of, Subscription } from 'rxjs';
import { map, shareReplay, switchMap, takeUntil, tap, catchError, filter, timeout, distinctUntilChanged } from 'rxjs/operators';
import { ConversationRepository } from '../repositories/conversation.repository';
import { MessageRepository, MessageWithSyncStatus } from '../repositories/message.repository';
import { SyncEngineService } from '../repositories/sync-engine.service';
import { Conversation } from '../data/objects/conversation';
import { Message, AgentContent, AgentStep } from '../data/objects/message';
import { FilePreview, UploadStatus } from '../data/objects/file-preview';
import { ApiService } from './api.service';
import { AuthService } from '../auth/auth.service';
import { SettingsStateService } from './settings-state.service';
import { UIStateService } from './ui-state.service';
import { NotificationService } from './notification.service';
import {
  StreamingService,
  StreamEvent,
  MessageStartEventData,
  ErrorEventData,
  StepDeltaEventData,
  DoneEventData
} from './streaming.service';
import { CatalogService } from './catalog.service';
import { FamilyModeService } from './family-mode.service';
import {
  IConversationSelection,
  IPublicModel,
  IPublicPersona,
  PersonaValues
} from '../data/models/catalog.model';
import { IConversationFile } from '../data/models/api.model';
import { IConversationSummary } from '../data/models/conversation.model';
import { IKBReviewResult } from '../data/models/knowledge-base.model';
import { environment } from '../environments/environment';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { DBService } from '../data/db.service';
import { AppSettings } from '../models/settings.model';
import { describeHttpError } from '../catalog-admin/catalog-admin.utils';
import { TranslateService } from '@ngx-translate/core';

/** Model and persona for a new conversation, kept until it is created with the first message. */
const EMPTY_DRAFT: IConversationSelection = { modelId: null, personaId: null, personaValues: null };

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

  // Model catalog selection
  private draftSelection$ = new BehaviorSubject<IConversationSelection>(EMPTY_DRAFT);

  // The summary the model gets instead of the active conversation's oldest messages (kept on the server only)
  private summary$ = new BehaviorSubject<IConversationSummary | null>(null);
  public conversationSummary$: Observable<IConversationSummary | null> = this.summary$.asObservable();

  // Summaries being written at the user's request, by conversation (summarizeConversation())
  private summaryRequests = new Map<string, Promise<IConversationSummary>>();
  private summarizingIds$ = new BehaviorSubject<ReadonlySet<string>>(new Set());
  /** Whether a summary of the active conversation is being written at the user's request. */
  public isSummarizing$: Observable<boolean> = combineLatest([this.activeConversationId$, this.summarizingIds$]).pipe(
    map(([id, ids]) => id !== null && ids.has(id)),
    distinctUntilChanged()
  );

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
    map(messages => messages.sort(Message.compare)),
    shareReplay(1)
  );

  /** Model and persona of the active conversation (the draft for a new conversation). */
  public selection$: Observable<IConversationSelection> = combineLatest([
    this.activeConversation$,
    this.draftSelection$
  ]).pipe(
    map(([conversation, draft]) => {
      if (!conversation || conversation.id === '0') {
        return draft;
      }
      return conversation.selection;
    }),
    shareReplay(1)
  );

  /** The catalog model that will answer in the active conversation; null without a catalog. */
  public effectiveModel$: Observable<IPublicModel | null> = combineLatest([
    this.selection$,
    this.catalogService.models$,
    this.settingsState.settings$
  ]).pipe(
    map(([selection, models, settings]) =>
      this.catalogService.resolveModel(selection.modelId, settings?.defaultModelId, models)
    ),
    shareReplay(1)
  );

  /** The persona of the active conversation, if it is (still) in the catalog. */
  public activePersona$: Observable<IPublicPersona | null> = combineLatest([
    this.selection$,
    this.catalogService.personas$
  ]).pipe(
    map(([selection, personas]) => personas.find(p => p.id === selection.personaId) ?? null),
    shareReplay(1)
  );

  // All conversations
  public conversations$ = this.conversationRepository.getAll().pipe(
    map(conversations => [...conversations].sort(Conversation.compareByActivity)),
    shareReplay(1)
  );

  /**
   * The open conversation its agent hidden during an answer: it stays open and listed while the
   * user is in it, even where hidden content is hidden, and is hidden once they leave it.
   */
  private keptOpenHidden$ = new BehaviorSubject<string | null>(null);

  /** An agent hid a conversation, or took its mark back, while answering (the chat offers Undo). */
  public readonly agentHideMarks$ = new Subject<{ conversationId: string; hidden: boolean }>();

  /** The conversations to show: without the hidden ones while this device is in family mode. */
  public visibleConversations$: Observable<Conversation[]> = combineLatest([
    this.conversations$, this.familyMode.active$, this.catalogService.hiddenPersonaIds$, this.keptOpenHidden$
  ]).pipe(
    map(([conversations, hide, hiddenPersonas, keptOpen]) => hide
      ? conversations.filter(conversation => conversation.id === keptOpen
          || !FamilyModeService.isConversationHidden(conversation, hiddenPersonas))
      : conversations),
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
    private dbService: DBService,
    private catalogService: CatalogService,
    private translate: TranslateService,
    private familyMode: FamilyModeService
  ) {
    this.initializeService();
    this.listenToAuthChanges();
    this.watchSummary();
    this.closeHiddenConversation();
  }

  private async initializeService(): Promise<void> {
    // Load initial conversation
    const conversations = await firstValueFrom(this.visibleConversations$);
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
        if (this.authService.isGuest) {
          console.log('Guest user detected, resetting chat state');
          this.resetState();
        } else {
          // The first conversation may have been opened before there was a session
          this.loadSummary(this.activeConversationId$.getValue());
        }
      });
  }

  /**
   * An open hidden conversation closes into a new chat once this device is in family mode: when
   * the switch goes off, when the chat (or its agent) is marked, or when a link opens one. A new
   * chat's hidden agent is dropped the same way.
   */
  private closeHiddenConversation(): void {
    // A conversation kept open after its agent marked it is hidden once the user opens another
    this.activeConversationId$.pipe(distinctUntilChanged(), takeUntil(this.destroy$)).subscribe(id => {
      if (this.keptOpenHidden$.getValue() !== null && id !== this.keptOpenHidden$.getValue()) {
        this.keptOpenHidden$.next(null);
      }
    });
    combineLatest([this.activeConversation$, this.draftSelection$, this.familyMode.active$,
                   this.catalogService.hiddenPersonaIds$])
      .pipe(takeUntil(this.destroy$))
      .subscribe(([conversation, draft, hide, hiddenPersonas]) => {
        if (!hide || !conversation || conversation.id === this.keptOpenHidden$.getValue()) return;
        if (conversation.id !== '0' && conversation.id === this.activeConversationId$.getValue()
            && FamilyModeService.isConversationHidden(conversation, hiddenPersonas)) {
          // After this emission: switching the active conversation from inside a stream that
          // derives from it would let the old conversation's values arrive last
          const id = conversation.id;
          queueMicrotask(() => {
            if (this.activeConversationId$.getValue() === id) void this.createNewConversation();
          });
        } else if (conversation.id === '0' && draft.personaId != null && hiddenPersonas.has(draft.personaId)) {
          this.draftSelection$.next(EMPTY_DRAFT);
        }
      });
  }

  /**
   * An answer's tool result says its agent hid the conversation (hide_chat) or took the mark
   * back: take it over at once, keep the open conversation open, and let the chat offer Undo.
   */
  private async onAgentHide(conversationId: string, hidden: boolean): Promise<void> {
    if (hidden && conversationId === this.activeConversationId$.getValue()) {
      this.keptOpenHidden$.next(conversationId);
    }
    if (await this.conversationRepository.applyAgentHidden(conversationId, hidden)) {
      this.agentHideMarks$.next({ conversationId, hidden });
    }
  }

  /** Hide a conversation or unhide it; hidden at once if this device is in family mode. */
  async setConversationHidden(conversationId: string, hidden: boolean): Promise<void> {
    await this.conversationRepository.setHidden(conversationId, hidden);
  }

  /** Load the summary of every conversation that becomes active (a new one has none). */
  private watchSummary(): void {
    this.activeConversationId$
      .pipe(distinctUntilChanged(), takeUntil(this.destroy$))
      .subscribe(id => {
        this.summary$.next(null);
        this.loadSummary(id);
      });
  }

  /** Fetch a conversation's summary; offline, or for a conversation the server doesn't know, there is none. */
  private async loadSummary(conversationId: string | null): Promise<void> {
    if (!conversationId || conversationId === '0') return;
    try {
      // Also makes sure there is a session: a 401 would open the login page
      if (!(await this.isBackendAvailable())) return;
      const summary = await this.apiService.getConversationSummary(conversationId);
      if (this.activeConversationId$.getValue() === conversationId) {
        this.summary$.next(summary);
      }
    } catch (error: any) {
      if (error?.status !== 404) {
        console.warn('Could not load the summary of the conversation:', error);
      }
    }
  }

  /**
   * The server drops the summary when a message it covers changes; so does this browser.
   * Not for a system message: it goes into the system prompt, never into the summary.
   */
  private dropSummaryCovering(messageId: number, roleName?: string): void {
    const summary = this.summary$.getValue();
    if (summary && roleName !== 'system' && messageId > 0 && messageId <= summary.coversUntil) {
      this.summary$.next(null);
    }
  }

  /** Whether a summary of this conversation is being written at the user's request. */
  isSummarizing(conversationId: string): boolean {
    return this.summaryRequests.has(conversationId);
  }

  /**
   * Fold all messages of a conversation so far into its summary now, rather than once they nearly
   * fill the model's context window: the next answer gets the summary and only the newer messages.
   * The conversation's model writes it on the server, which takes a while; a second call meanwhile
   * gets the same result.
   *
   * @throws HttpErrorResponse: 409 nothing new to summarize, 422 too short, 429 guest limit (shown in
   *   the chat), 502 the model failed
   */
  summarizeConversation(conversationId: string): Promise<IConversationSummary> {
    const running = this.summaryRequests.get(conversationId);
    if (running) return running;
    const request = this.writeSummary(conversationId).finally(() => {
      this.summaryRequests.delete(conversationId);
      this.summarizingIds$.next(new Set(this.summaryRequests.keys()));
    });
    this.summaryRequests.set(conversationId, request);
    this.summarizingIds$.next(new Set(this.summaryRequests.keys()));
    return request;
  }

  /**
   * Review a conversation for its agent's memory now, as the server does once it has been quiet
   * for a while: the memory model saves what matters from the messages since the last review.
   */
  reviewMemory(conversationId: string): Promise<IKBReviewResult> {
    return this.apiService.reviewConversationMemory(conversationId);
  }

  private async writeSummary(conversationId: string): Promise<IConversationSummary> {
    try {
      const summary = await this.apiService.summarizeConversation(conversationId);
      if (this.activeConversationId$.getValue() === conversationId) {
        this.summary$.next(summary);
      }
      return summary;
    } catch (error) {
      if (error instanceof HttpErrorResponse && error.status === 429) {
        this.handleRateLimitError(describeHttpError(error));
      }
      throw error;
    }
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
    // A new conversation starts with the default model and no persona
    this.draftSelection$.next(EMPTY_DRAFT);
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
        id: Message.localId(),
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
    if (userMessage.isLocal) {
      this.reportNotSent(userMessage);
      return;
    }
    await this.conversationRepository.recordMessage(conversationId, userMessage.id);

    // Start streaming the AI response
    await this._streamResponse(conversationId);
  }

  /**
   * Send a message again that the server didn't take (only this browser has it), and answer it.
   * The server stores it now, so it moves to the end of the conversation.
   */
  async resendMessage(messageId: number): Promise<void> {
    if (this.isStreaming$.getValue()) {
      throw new Error('Wait until the answer is complete');
    }
    const message = (await firstValueFrom(this.messages$)).find(m => m.id === messageId);
    if (!message || !message.isLocal || !message.isText()) {
      return;
    }
    const conversationId = message.conversationId;
    this.error$.next(null);
    await this.conversationRepository.markMessageSent(conversationId);
    try {
      await this.messageRepository.resend(message);
    } catch {
      this.reportNotSent(message);
      return;
    }
    await this.conversationRepository.recordMessage(conversationId, message.id);
    await this._streamResponse(conversationId);
  }

  /**
   * The server didn't take the user's message: nothing answers it (the server would answer the
   * conversation without it). It stays in this browser, and the chat shows it as not sent, with
   * a button to send it again (resendMessage()); it can also be deleted.
   */
  private reportNotSent(message: MessageWithSyncStatus): void {
    message.syncStatus = 'failed';
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
        id: Message.localId(),
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
    if (userMessage.isLocal) {
      this.reportNotSent(userMessage);
      return;
    }
    await this.conversationRepository.recordMessage(conversationId, userMessage.id);

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
        id: Message.localId(),
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

    // Mark that we're sending a message to prevent immediate re-sync
    await this.conversationRepository.markMessageSent(conversationId);

    // Clear the pending reference
    const messageToSync: MessageWithSyncStatus = this.pendingVoiceMessage;
    this.pendingVoiceMessage = null;

    // Update it locally and send it to the backend, which gives it its id and time
    messageToSync.syncStatus = 'pending';
    try {
      await this.messageRepository.update(messageToSync);
      await this.conversationRepository.recordMessage(conversationId, messageToSync.id);
    } catch (error) {
      console.error('Failed to sync voice message with backend:', error);
    }
    if (messageToSync.isLocal) {
      this.reportNotSent(messageToSync);
      return;
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
        // Which model answers (modelId null = the environment model)
        if (startData.modelId !== undefined) message.content.modelId = startData.modelId;
        if (startData.modelName !== undefined) message.content.modelName = startData.modelName;
        // Status remains 'thinking' until we get steps or tokens
        break;

      case 'step': {
        // A step with a known id replaces the earlier one (e.g. the reasoning step, sent
        // empty at its start and complete at its end); otherwise it is a new step
        const step = event.data as AgentStep;
        // The agent hid its conversation, or took the mark back 
        const hiddenChat = (step.metadata as Record<string, unknown> | undefined)?.['hiddenChat'];
        if (typeof hiddenChat === 'boolean' && message.conversationId) {
          void this.onAgentHide(message.conversationId, hiddenChat);
        }
        const steps = message.content.steps;
        const index = steps.findIndex(s => s.id === step.id);
        if (index >= 0) {
          steps[index] = step;
        } else {
          steps.push(step);
          message.content.status = 'thinking';
        }
        break;
      }

      case 'step_delta': {
        // Live reasoning text for an earlier step
        const delta = event.data as StepDeltaEventData;
        const step = message.content.steps.find(s => s.id === delta.id);
        if (step) {
          step.content = (step.content || '') + delta.delta;
        }
        break;
      }

      case 'token':
        // Append the token to the response content
        message.content.content += event.data as string;
        message.content.status = 'responding';
        break;

      case 'summary': {
        // The oldest messages were summarized before the answer
        const summary = event.data as IConversationSummary;
        if (summary.conversationId === this.activeConversationId$.getValue()) {
          this.summary$.next(summary);
        }
        break;
      }

      case 'done': {
        // Mark as complete (ID should already be set from message_start)
        const doneData = event.data as DoneEventData;
        if (doneData.modelId !== undefined) message.content.modelId = doneData.modelId;
        if (doneData.modelName !== undefined) message.content.modelName = doneData.modelName;
        if (doneData.usage !== undefined) message.content.usage = doneData.usage;
        message.content.status = 'complete';
        break;
      }

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

    // Save the error message to the repository (the server stored it too if it had started it)
    await this.messageRepository.save(message);
    await this.conversationRepository.recordMessage(message.conversationId, message.id);

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

      // The conversation moves up in the sidebar
      await this.conversationRepository.recordMessage(message.conversationId, message.id);

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

        // The conversation moves up in the sidebar
        await this.conversationRepository.recordMessage(streamingMessage.conversationId, streamingMessage.id);
      }
    }

    // Clean up streaming state
    this.isStreaming$.next(false);
    this.streamingMessage$.next(null);
  }

  /**
   * Internal helper to start streaming an AI response.
   * Creates a placeholder agent message and streams the response.
   * @param modelId - Answer with this catalog model instead of the conversation's model
   */
  private async _streamResponse(conversationId: string, modelId?: number): Promise<void> {
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
      .streamAgentResponse(conversationId, 'Assistant', modelId)
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
          id: Message.localId(),
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
        const resetTimeISO = detail && detail.includes('after') ? detail.split('after ')[1] : undefined;
        this.authService.setGuestLimitReached(true, this.guestLimitMessage(resetTimeISO));
      } else {
        console.error('Error generating message:', error);
        const errorMessage = Message.createText(
          {
            id: Message.localId(),
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
   * Update (patch) a message's text with conflict resolution: a text message keeps its
   * attachments, an agent message its steps.
   * @param deleteFollowing - Also delete the messages after it (only online), so it can be answered again
   */
  async patchMessage(messageId: number, content: string, maxRetries: number = 3, deleteFollowing = false): Promise<void> {
    const messages = await firstValueFrom(this.messages$);
    const message = messages.find(m => m.id === messageId);

    if (!message || !(message.isText() || message.isAgent())) {
      throw new Error('Message not found or not a text or agent message');
    }

    const conversationId = this.activeConversationId$.getValue()!;
    let retryCount = 0;
    let success = false;

    while (retryCount < maxRetries && !success) {
      try {
        // Update via API if online
        if (await this.isBackendAvailable()) {
          await this.apiService.patchMessage(conversationId, messageId, content, message.version, deleteFollowing);
          success = true;
        } else if (deleteFollowing) {
          throw new Error('The server is not reachable');
        } else {
          // Offline mode - just update locally
          success = true;
        }

        // The same message (rating, model, steps) with the new text and an incremented version
        const updatedMessage = new Message(
          { ...message.metadata, version: message.version + 1, lastModified: Math.floor(Date.now() / 1000) },
          { ...message.content, content }
        );

        await this.messageRepository.update(updatedMessage);
        this.dropSummaryCovering(messageId, message.roleName);

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
    const message = (await firstValueFrom(this.messages$)).find(m => m.id === messageId);
    await this.messageRepository.delete(messageId);
    this.dropSummaryCovering(messageId, message?.roleName);
  }

  /**
   * Save the edited text of one of the user's messages and answer it again (guided editing):
   * the messages after it are deleted, then a new answer streams in.
   */
  async resendEditedMessage(messageId: number, content: string): Promise<void> {
    if (this.isStreaming$.getValue()) {
      throw new Error('Wait until the answer is complete');
    }
    const conversationId = this.activeConversationId$.getValue()!;
    this.error$.next(null);

    await this.patchMessage(messageId, content, 3, true);

    // The server deleted the later messages; so does this browser (also the ones it only has itself)
    const messages = await firstValueFrom(this.messages$);
    const edited = messages.find(m => m.id === messageId);
    const following = edited ? messages.filter(m => Message.compare(m, edited) > 0) : [];
    await this.messageRepository.removeLocally(conversationId, following.map(m => m.id));

    await this._streamResponse(conversationId);
  }

  /**
   * Insert a text message of the user, the assistant or the system before or after a message
   * (manual editing). The server picks its id between the two neighbours, so it sorts there;
   * nothing answers it. A system message is an instruction to the model for the answers after it.
   */
  async insertMessage(
    next: Message, position: 'before' | 'after', roleName: 'user' | 'Assistant' | 'system', content: string
  ): Promise<void> {
    const inserted = await this.apiService.insertMessage(next.conversationId, next.id, position, roleName, content);
    await this.messageRepository.save(inserted, true);
    this.dropSummaryCovering(inserted.id, inserted.roleName);
  }

  /**
   * Answer the conversation as it is stored, without sending a new message (manual editing:
   * Generate in the composer). After an answer the server asks the model to go on from it.
   */
  async answerLatestMessage(): Promise<void> {
    if (this.isStreaming$.getValue()) {
      throw new Error('Wait until the answer is complete');
    }
    const conversationId = this.activeConversationId$.getValue();
    if (!conversationId || conversationId === '0') {
      return;
    }
    this.error$.next(null);
    await this._streamResponse(conversationId);
  }

  /**
   * Regenerate a message using streaming.
   * Deletes the old AI message and streams a new response.
   * @param modelId - Answer with this catalog model instead of the conversation's model (once)
   */
  async regenerateMessage(message: Message, modelId?: number): Promise<void> {
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
      this.dropSummaryCovering(message.id);

      // Start streaming a new response (backend will use the last user message)
      await this._streamResponse(message.conversationId, modelId);
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
   * A conversation with all its messages, e.g. for a download
   */
  exportConversation(conversationId: string): Promise<IConversationFile> {
    return this.conversationRepository.exportConversation(conversationId);
  }

  /**
   * Import a conversation file as a new conversation
   */
  importConversation(file: IConversationFile): Promise<Conversation> {
    return this.conversationRepository.importConversation(file);
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
   * Helper: Create conversation from first message with async AI-generated title
   */
  private async createConversationFromFirstMessage(content: string): Promise<void> {
    const backendAvailable = await this.isBackendAvailable();
    let conversation: Conversation;
    const selection = this.resolveDraftSelection();

    // Generate fallback title (truncated message)
    const fallbackTitle = content.length > 50
      ? content.substring(0, 47).trim() + '...'
      : content;

    if (!backendAvailable) {
      // Create local-only conversation with fallback title
      conversation = new Conversation(
        this.dbService.generateUUID(),
        0,
        fallbackTitle,
        ['user', 'Assistant']
      );
    } else {
      // Create conversation on server with fallback title (fast)
      const newConvData = new Conversation('', 0, fallbackTitle, ['user', 'Assistant']);
      this.applySelection(newConvData, selection);
      try {
        conversation = await this.apiService.createConversation(newConvData);

        // Fire off async title generation (don't await - runs in background)
        this.generateTitleAsync(conversation.id, content);
      } catch (error) {
        console.error('Failed to create conversation on server:', error);
        // Fallback to local with truncated title
        conversation = new Conversation(
          this.dbService.generateUUID(),
          0,
          fallbackTitle,
          ['user', 'Assistant']
        );
      }
    }

    // Keep the selection locally if the backend doesn't return it (no catalog yet, or a local-only conversation)
    if (conversation.modelId === undefined && conversation.personaId === undefined) {
      this.applySelection(conversation, selection);
    }
    await this.conversationRepository.save(conversation);
    this.isNewConversation$.next(false);
    this.activeConversationId$.next(conversation.id);
    this.uiState.setActiveConversation(conversation.id);
  }

  // =========================================================================
  // Model catalog selection
  // =========================================================================

  /** Pick the model for the active conversation (null = the user's default model). */
  async selectModel(modelId: number | null): Promise<void> {
    const conversationId = this.activeConversationId$.getValue();
    if (!conversationId || conversationId === '0') {
      this.draftSelection$.next({ ...this.draftSelection$.getValue(), modelId });
      return;
    }
    await this.conversationRepository.updateSelection(conversationId, { modelId });
  }

  /**
   * Pick the persona for the active conversation (null = no persona), with the values for its
   * variables. The model stays as it is.
   */
  async selectPersona(persona: IPublicPersona | null, values: PersonaValues | null = null): Promise<void> {
    const changes: Partial<IConversationSelection> = {
      personaId: persona ? persona.id : null,
      personaValues: persona && values && Object.keys(values).length > 0 ? values : null
    };

    const conversationId = this.activeConversationId$.getValue();
    if (!conversationId || conversationId === '0') {
      this.draftSelection$.next({ ...this.draftSelection$.getValue(), ...changes });
      return;
    }
    await this.conversationRepository.updateSelection(conversationId, changes);
  }

  /**
   * The selection a new conversation is created with: the picked or the default model, so the
   * conversation keeps its model when the default changes later. Undefined without a catalog,
   * so the create request stays as it was.
   */
  private resolveDraftSelection(): IConversationSelection | undefined {
    const draft = this.draftSelection$.getValue();
    if (!this.catalogService.hasModels && this.catalogService.personas.length === 0) {
      return undefined;
    }
    const defaultModelId = this.settingsState.getCurrentSettings()?.defaultModelId ?? null;
    const model = this.catalogService.resolveModel(draft.modelId, defaultModelId);
    return {
      modelId: model ? model.id : null,
      personaId: draft.personaId,
      personaValues: draft.personaValues
    };
  }

  private applySelection(conversation: Conversation, selection: IConversationSelection | undefined): void {
    if (!selection) return;
    conversation.modelId = selection.modelId;
    conversation.personaId = selection.personaId;
    conversation.personaValues = selection.personaValues;
  }

  /**
   * Generate AI title for conversation asynchronously and update sidebar
   */
  private generateTitleAsync(conversationId: string, firstMessage: string): void {
    this.apiService.generateConversationTitle(conversationId, firstMessage)
      .then(async (updatedConversation) => {
        // Update local cache and IndexedDB with the new title (backend already updated)
        await this.conversationRepository.saveFromServer(updatedConversation);
        console.log(`Conversation title updated to: ${updatedConversation.name}`);
      })
      .catch((error) => {
        // Silently fail - fallback title is already in place
        console.warn('Failed to generate AI title:', error);
      });
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
    const resetTimeMatch = error.includes('after') ? error.match(/after\s+(\S+)/) : null;
    this.authService.setGuestLimitReached(true, this.guestLimitMessage(resetTimeMatch?.[1]));
  }

  /** The guest limit's message, in the app's language, with the time it resets (an ISO time) when known. */
  private guestLimitMessage(resetTimeISO?: string): string {
    const resetDate = resetTimeISO ? new Date(resetTimeISO) : null;
    if (!resetDate || isNaN(resetDate.getTime())) {
      return this.translate.instant('message.guestLimitTryLater');
    }
    const time = resetDate.toLocaleTimeString(this.translate.currentLang || [], { hour: '2-digit', minute: '2-digit' });
    return this.translate.instant('message.guestLimitUntil', { time });
  }

  /**
   * Reset all state - used during logout
   */
  resetState(): void {
    console.log('Resetting chat state...');
    // Reset to new conversation state
    this.draftSelection$.next(EMPTY_DRAFT);
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
