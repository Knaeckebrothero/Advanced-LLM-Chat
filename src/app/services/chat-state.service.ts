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
  DoneEventData,
  NoAnswerRunningError,
  StreamHttpError
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

/**
 * Model and persona for a new conversation, kept until it is created with the first message.
 * personaId undefined: the user's default agent (none picked yet); null: no agent.
 */
type DraftSelection = Omit<IConversationSelection, 'personaId'> & { personaId: number | null | undefined };
const EMPTY_DRAFT: DraftSelection = { modelId: null, personaId: undefined, personaValues: null };

/**
 * The answer this browser follows. It runs on the server on its own (docs/background_answers.md):
 * a stream that breaks only stops watching it, so it is followed again from the last event it got.
 */
interface Following {
  conversationId: string;
  message: Message<AgentContent>;
  runId: string | null;  // From message_start: to follow it again and to stop it
  lastEventId: number;  // The number of the last event it got
  attempts: number;  // Attempts in a row to follow it again without getting anything
  shown: boolean;  // The chat shows it (an answer followed again shows once its first event arrives)
  stored?: Message[];  // Followed again: the conversation's messages, to find the answer it writes a new version of
}

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
  // Answers that failed and that the server stored (with its error): kept when their stream ends
  private storedErrors = new WeakSet<Message>();
  // The answer a running stream writes a new version of (Regenerate), null for a new answer
  private regenerating: Message | null = null;
  // The answer this browser follows, also while it tries to follow it again (Following)
  private following: Following | null = null;
  // Waits before following an answer again after its stream broke without anything new
  private static readonly FOLLOW_AGAIN_DELAYS = [0, 2000, 5000, 10000];

  // Model catalog selection
  private draftSelection$ = new BehaviorSubject<DraftSelection>(EMPTY_DRAFT);

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

  /** The id of the agent a new conversation starts with (the user's default agent while it is offered), or null. */
  private defaultPersonaId$: Observable<number | null> = combineLatest([
    this.settingsState.settings$,
    this.catalogService.visiblePersonas$
  ]).pipe(
    map(([settings, personas]) => CatalogService.defaultPersona(settings?.defaultPersonaId, personas)?.id ?? null),
    distinctUntilChanged()
  );

  /** Model and persona of the active conversation (the draft for a new conversation, with the default agent). */
  public selection$: Observable<IConversationSelection> = combineLatest([
    this.activeConversation$,
    this.draftSelection$,
    this.defaultPersonaId$
  ]).pipe(
    map(([conversation, draft, defaultPersonaId]) => {
      if (!conversation || conversation.id === '0') {
        return ChatStateService.withDefaultPersona(draft, defaultPersonaId);
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
      // The answer of another conversation goes on on the server; opening it again follows it again
      if (this.following && this.following.conversationId !== conversationId) {
        this.leaveAnswer();
      }
      if (conversationId === '0') {
        this.isNewConversation$.next(true);
        this.activeConversationId$.next('0');
      } else {
        this.isNewConversation$.next(false);
        this.activeConversationId$.next(conversationId);

        // Trigger sync for this conversation if online
        if (await this.isBackendAvailable()) {
          this.conversationRepository.syncConversation(conversationId).catch(console.error);
          // An answer that is being written in it (started before the app was closed, or on another device)
          void this.followAnswer(conversationId);
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
    // An answer that is being written goes on on the server; opening its conversation follows it again
    this.leaveAnswer();
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
        // The server didn't have the answer being regenerated (only this browser did): it writes a
        // new answer, and this browser's copy goes
        const replaced = this.regenerating;
        if (replaced && replaced.id !== startData.messageId) {
          void this.messageRepository.removeLocally(replaced.conversationId, [replaced.id]);
          this.regenerating = null;
        }
        // Followed again (the app was closed): a new version of a stored answer hides it, as Regenerate does
        const stored = this.following?.message === message ? this.following.stored : undefined;
        if (!this.regenerating && stored) {
          this.regenerating = stored.find(m => m.id === startData.messageId && !m.isText()) ?? null;
        }
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
        this.takeVersions(message, doneData);
        message.content.status = 'complete';
        break;
      }

      case 'error': {
        // Handle error
        const errorData = event.data as ErrorEventData;
        message.content.status = 'error';
        message.content.error = errorData.error;
        if (errorData.messageId !== undefined) {
          // The server stored the failed answer: it stays here too
          message.id = errorData.messageId;
          this.takeVersions(message, errorData);
          this.storedErrors.add(message);
        }
        break;
      }
    }

    // Emit the updated message (create a new reference to trigger change detection)
    this.streamingMessage$.next(message);
  }

  /** The stored answer's version counter and versions, from a 'done' or a stored 'error' event. */
  private takeVersions(message: Message<AgentContent>, data: DoneEventData | ErrorEventData): void {
    if (data.version !== undefined) message.version = data.version;
    message.metadata.alternatives = Message.readAlternatives(data.alternativePosition, data.alternativeCount);
  }

  /**
   * Handle stream errors
   */
  private async handleStreamError(error: any, message: Message<AgentContent>): Promise<void> {
    console.error('Stream error:', error);

    // Update message to show error state
    message.content.status = 'error';
    message.content.error = error.message || 'An error occurred during streaming';

    // A new version that failed this way doesn't replace the stored answer here: its error is
    // shown on its own after it, as only this browser has it
    if (this.regenerating && message.id === this.regenerating.id) {
      message.id = Message.localId();
    }
    this.regenerating = null;

    // Save the error message to the repository (the server stored it too if it had started it)
    await this.messageRepository.save(message);
    await this.conversationRepository.recordMessage(message.conversationId, message.id);

    // Clean up streaming state
    this.following = null;
    this.streamingSubscription = null;
    this.isStreaming$.next(false);
    this.streamingMessage$.next(null);

    this.notificationService.showError('Failed to generate response');
  }

  /**
   * Handle stream completion
   */
  private async handleStreamComplete(message: Message<AgentContent>): Promise<void> {
    // Save what the server stored: a complete answer, or one that failed (with its error)
    const complete = message.content.status === 'complete';
    if (complete || this.storedErrors.has(message)) {
      // The message was already saved on the backend by the SSE endpoint,
      // but we need to save it locally to IndexedDB
      await this.messageRepository.save(message);

      // The conversation moves up in the sidebar
      await this.conversationRepository.recordMessage(message.conversationId, message.id);

      if (complete) {
        this.notificationService.showSuccess('Response generated');
      }
    }

    // Clean up streaming state
    this.regenerating = null;
    this.following = null;
    this.isStreaming$.next(false);
    this.streamingMessage$.next(null);
    this.streamingSubscription = null;
  }

  /**
   * Cancel an ongoing streaming response.
   * Saves the partial response if any content was generated.
   */
  async cancelStreaming(): Promise<void> {
    // Unsubscribe first to stop receiving more tokens; nothing follows the answer again
    const following = this.following;
    this.following = null;
    if (this.streamingSubscription) {
      this.streamingSubscription.unsubscribe();
      this.streamingSubscription = null;
    }

    // The answer runs on the server on its own (docs/background_answers.md): closing its stream
    // doesn't stop it, the server does, and keeps what was written (as a new answer, or as a new
    // version of the regenerated one). Only that run, so a late Stop can't stop a newer answer
    const stopped = following
      ? this.streamingService.stopAgentResponse(following.conversationId, following.runId).catch(error => {
          console.warn('Could not stop the answer:', error);
          return false;
        })
      : Promise.resolve(false);

    // Get the current streaming message before clearing
    const streamingMessage = this.streamingMessage$.getValue();
    const regenerated = this.regenerating;
    this.regenerating = null;

    // Save partial response if we have any content. The server keeps it too
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

        // The version counter and the versions are the server's: ask for them once it has the answer
        if (regenerated && streamingMessage.id === regenerated.id) {
          void stopped.then(() => this.refreshStoppedVersion(streamingMessage, regenerated.version));
        }
      }
      // Otherwise nothing changed: the version shown before appears again
    }

    // Clean up streaming state
    this.isStreaming$.next(false);
    this.streamingMessage$.next(null);
  }

  /**
   * After a stopped regeneration: take the answer as the server stored it (its version counter
   * and versions), once it is newer than the version this browser regenerated. Called once Stop
   * returned (the server has stored it then); it asks again a moment later in case it hadn't.
   */
  private async refreshStoppedVersion(message: Message, regeneratedVersion: number): Promise<void> {
    for (const wait of [500, 2000]) {
      await new Promise(resolve => setTimeout(resolve, wait));
      try {
        const [stored] = await this.apiService.getConversationMessages(message.conversationId, 1, message.id + 1);
        if (stored?.id === message.id && stored.version > regeneratedVersion) {
          await this.messageRepository.save(stored, true);
          return;
        }
      } catch {
        return;  // The next sync brings it
      }
    }
  }

  /**
   * Internal helper to start streaming an AI response.
   * Creates a placeholder agent message and streams the response.
   * @param modelId - Answer with this catalog model instead of the conversation's model
   */
  private async _streamResponse(conversationId: string, modelId?: number, regenerate?: Message): Promise<void> {
    // Create placeholder agent message for streaming
    const agentMessage = Message.createAgent(conversationId, [], '', 'thinking');
    if (regenerate) {
      // A new version of a stored answer takes its place and id: the chat hides the stored copy
      // while it streams (and shows it again if it is stopped before the model wrote anything)
      agentMessage.id = regenerate.id;
      agentMessage.roleName = regenerate.roleName;
    }
    this.regenerating = regenerate ?? null;
    this.streamingMessage$.next(agentMessage);
    this.isStreaming$.next(true);

    // Start streaming (an earlier stream, e.g. an attempt to follow an answer, is closed)
    this.watch(
      { conversationId, message: agentMessage, runId: null, lastEventId: 0, attempts: 0, shown: true },
      this.streamingService.streamAgentResponse(conversationId, 'Assistant', modelId, regenerate?.id)
    );
  }

  /**
   * Follow the answer that is being written in a conversation, if there is one
   * (docs/background_answers.md): it was started before the app was closed or the phone locked,
   * or on another device. Called when the conversation opens and when the app comes back; the
   * answer shows once its first events arrive, with what was written so far.
   */
  async followAnswer(conversationId: string): Promise<void> {
    if (!conversationId || conversationId === '0' || this.following) {
      return;
    }
    const stored = await firstValueFrom(this.messages$);
    if (this.following || this.activeConversationId$.getValue() !== conversationId) {
      return;
    }
    const message = Message.createAgent(conversationId, [], '', 'thinking');
    this.watch(
      { conversationId, message, runId: null, lastEventId: 0, attempts: 0, shown: false, stored },
      this.streamingService.followAgentResponse(conversationId)
    );
  }

  /** Put an answer's events into its message; how its stream ends decides what follows (onStreamEnd()). */
  private watch(following: Following, events$: Observable<StreamEvent>): void {
    this.streamingSubscription?.unsubscribe();
    this.following = following;
    this.streamingSubscription = events$.subscribe({
      next: event => {
        if (this.following !== following) return;
        if (event.id !== undefined) following.lastEventId = event.id;
        if (event.type === 'message_start') {
          following.runId = (event.data as MessageStartEventData).runId ?? null;
        }
        following.attempts = 0;
        this.handleStreamEvent(event, following.message);
        if (!following.shown) {
          // Followed again: the chat shows it from now on (its turn goes to the top of the view)
          following.shown = true;
          this.isStreaming$.next(true);
        }
      },
      error: error => void this.onStreamEnd(following, error),
      complete: () => void this.onStreamEnd(following)
    });
  }

  /**
   * An answer's stream ended. With its done or error event the answer is complete; otherwise only
   * the stream broke (the network, a phone that locked, a server that restarts) and the answer
   * goes on on the server: it is followed again from the last event this browser got.
   */
  private async onStreamEnd(following: Following, error?: unknown): Promise<void> {
    if (this.following !== following) {
      return;  // Stopped, left or replaced meanwhile
    }
    const message = following.message;
    if (message.content.status === 'complete' || message.content.status === 'error') {
      await this.handleStreamComplete(message);
      return;
    }
    if (error instanceof NoAnswerRunningError) {
      // Nothing to follow (any more): the stored answer, if any, comes with the sync
      this.finishFollowing(following);
      return;
    }
    if (error instanceof StreamHttpError && error.status === 409 && !following.runId) {
      // Another answer is being written in this conversation (another device's): follow that one
      this.finishFollowing(following);
      this.notificationService.showInfo(this.translate.instant('message.answerStillRunning'));
      void this.followAnswer(following.conversationId);
      return;
    }
    if (!following.runId) {
      if (!following.shown) {
        this.finishFollowing(following);  // Following an answer failed
      } else if (error) {
        await this.handleStreamError(error, message);  // The answer never began
      } else {
        await this.handleStreamComplete(message);
      }
      return;
    }
    if (error instanceof StreamHttpError) {
      this.finishFollowing(following);  // E.g. the session ended: the sync brings what is stored
      return;
    }
    await this.followAgain(following);
  }

  /** Follow an answer again after its stream broke, after a short wait and once the app is visible. */
  private async followAgain(following: Following): Promise<void> {
    const wait = ChatStateService.FOLLOW_AGAIN_DELAYS[following.attempts];
    if (wait === undefined) {
      // Unreachable for now (offline, or the server restarts): the sync and coming back to the
      // conversation bring the answer, or follow it again while it is written
      this.finishFollowing(following);
      return;
    }
    following.attempts++;
    if (wait) {
      await new Promise(resolve => setTimeout(resolve, wait));
    }
    // A hidden page (a locked phone) can't hold a connection: wait until it is visible
    while (document.hidden && this.following === following) {
      await new Promise<void>(resolve => document.addEventListener('visibilitychange', () => resolve(), { once: true }));
    }
    if (this.following !== following) {
      return;
    }
    this.watch(following, this.streamingService.followAgentResponse(
      following.conversationId, following.runId, following.lastEventId));
  }

  /** Stop following an answer that can't be followed: what the server stored comes with the sync. */
  private finishFollowing(following: Following): void {
    if (this.following !== following) {
      return;
    }
    const shown = following.shown;
    this.leaveAnswer();
    if (shown) {
      this.conversationRepository.syncConversation(following.conversationId).catch(console.error);
    }
  }

  /**
   * Stop following the answer this browser follows, without stopping it: it goes on on the
   * server (another conversation opens, or a new one), and opening its conversation follows it again.
   */
  private leaveAnswer(): void {
    const following = this.following;
    if (!following) {
      return;
    }
    this.following = null;
    this.streamingSubscription?.unsubscribe();
    this.streamingSubscription = null;
    if (following.shown) {
      this.regenerating = null;
      this.isStreaming$.next(false);
      this.streamingMessage$.next(null);
    }
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
   * Save the edited text of a stored message: a text message keeps its attachments, an agent
   * message its steps. Throws when the server doesn't take the edit (MessageRepository.patch());
   * the message then stays as it was.
   * @param deleteFollowing - Also delete the messages after it on the server, so it can be answered again
   */
  async patchMessage(messageId: number, content: string, deleteFollowing = false): Promise<void> {
    const messages = await firstValueFrom(this.messages$);
    const message = messages.find(m => m.id === messageId);

    if (!message || !(message.isText() || message.isAgent())) {
      throw new Error('Message not found or not a text or agent message');
    }

    await this.messageRepository.patch(message, content, deleteFollowing);
    this.dropSummaryCovering(messageId, message.roleName);
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
   * Show another version of an answer (docs/answer_versions.md): the server swaps it in, so the
   * next answers get it; the answer keeps its place and id.
   * @param position - The version to show, 1 for the first
   */
  async switchAlternative(message: Message, position: number): Promise<void> {
    const shown = await this.apiService.switchAlternative(message.conversationId, message.id, position);
    await this.messageRepository.save(shown, true);  // The server's copy: nothing to send
    this.dropSummaryCovering(message.id, message.roleName);
  }

  /**
   * Delete the version of an answer that is shown: the server shows the next one in its place
   * (the previous one after the last). An answer without other versions is deleted with deleteMessage().
   */
  async deleteAlternative(message: Message): Promise<void> {
    const shown = await this.apiService.deleteAlternative(message.conversationId, message.id);
    await this.messageRepository.save(shown, true);  // The server's copy: nothing to send
    this.dropSummaryCovering(message.id, message.roleName);
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

    await this.patchMessage(messageId, content, true);

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
   * Regenerate an answer using streaming: a new version of it (docs/answer_versions.md), written in
   * its place with the history before it. The version shown so far is kept, and the chat switches
   * between them. An answer only this browser has is deleted and answered anew.
   * @param modelId - Answer with this catalog model instead of the conversation's model (once)
   */
  async regenerateMessage(message: Message, modelId?: number): Promise<void> {
    if (!message.id || !message.conversationId) {
      throw new Error('Message ID and conversation ID are required');
    }

    // Check if it's an AI message
    if (message.roleName === 'user' || message.roleName === 'system') {
      throw new Error('Can only regenerate AI messages');
    }
    if (this.isStreaming$.getValue()) {
      throw new Error('Wait until the answer is complete');
    }

    this.error$.next(null);

    try {
      this.dropSummaryCovering(message.id);
      if (message.isLocal) {
        // It failed before the server stored it: only this browser has it
        await this.messageRepository.delete(message.id);
        await this._streamResponse(message.conversationId, modelId);
      } else {
        await this._streamResponse(message.conversationId, modelId, message);
      }
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
      // An answer that is being written in it (back to the app, or one another device started)
      void this.followAnswer(conversationId);
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
  async loadOlderMessages(beforeId: number, limit: number = 20): Promise<Message[]> {
    const conversationId = this.activeConversationId$.getValue();
    if (!conversationId || conversationId === '0') {
      return [];
    }

    const messages = await this.conversationRepository.loadOlderMessages(conversationId, beforeId, limit);

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
    const settings = this.settingsState.getCurrentSettings();
    const model = this.catalogService.resolveModel(draft.modelId, settings?.defaultModelId ?? null);
    const defaultPersona = CatalogService.defaultPersona(settings?.defaultPersonaId,
                                                        this.catalogService.visiblePersonas);
    return {
      ...ChatStateService.withDefaultPersona(draft, defaultPersona?.id ?? null),
      modelId: model ? model.id : null
    };
  }

  /** A draft's selection: the agent picked for it, else (none picked yet) the default agent. */
  private static withDefaultPersona(draft: DraftSelection, defaultPersonaId: number | null): IConversationSelection {
    if (draft.personaId !== undefined) {
      return { ...draft, personaId: draft.personaId };
    }
    return { ...draft, personaId: defaultPersonaId, personaValues: null };
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
