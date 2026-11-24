// src/app/services/side-chat.service.ts
import { Injectable, OnDestroy } from '@angular/core';
import { TranslateService } from '@ngx-translate/core';
import { BehaviorSubject, Observable, Subject, combineLatest, firstValueFrom, interval, of } from 'rxjs';
import { distinctUntilChanged, map, shareReplay, switchMap, takeUntil } from 'rxjs/operators';
import { Conversation } from '../data/objects/conversation';
import { AgentContent, Message } from '../data/objects/message';
import { FilePreview, UploadStatus } from '../data/objects/file-preview';
import { IConversationSelection, IPublicModel, IPublicPersona, PersonaValues } from '../data/models/catalog.model';
import { CatalogService } from './catalog.service';
import { SettingsStateService } from './settings-state.service';
import { ConversationRepository } from '../repositories/conversation.repository';
import { MessageRepository, MessageWithSyncStatus } from '../repositories/message.repository';
import { AnswerFollower } from './answer-follower';
import { ApiService } from './api.service';
import { ChatStateService } from './chat-state.service';
import { NotificationService } from './notification.service';
import { StreamingService } from './streaming.service';

/** What the side chat panel shows: the list of a conversation's side chats, or one of them. */
export interface SidePanelState {
  parentId: string;
  view: 'list' | 'chat';
  // The side chat shown; null: a new one, created with its first message
  sideId: string | null;
  // A new side chat: the message of the conversation it is forked from
  forkMessageId: number | null;
  // The list was opened from a message's side chats: they are marked
  focusForkId: number | null;
}

/** Side chats in a row before the sync asks the server for the open one's messages again. */
const SYNC_INTERVAL_MS = 60_000;

/**
 * Side chats (docs/side_chats.md): conversations forked from a message of the open conversation,
 * to ask about something or make an image on the side. They open in a panel next to the chat (a
 * sheet over it on a phone), which shows the conversation's side chats or one of them. A side chat
 * answers with an answer follower of its own, so it can write while the main chat does.
 */
@Injectable({
  providedIn: 'root'
})
export class SideChatService implements OnDestroy {
  private destroy$ = new Subject<void>();
  private state$ = new BehaviorSubject<SidePanelState | null>(null);

  /** What the panel shows; null when it is closed. */
  readonly panel$: Observable<SidePanelState | null> = this.state$.asObservable();

  /** The side chats of the open conversation, oldest first. */
  readonly sideChats$: Observable<Conversation[]> = combineLatest([
    this.chatState.activeConversation$, this.chatState.sideChatsByParent$
  ]).pipe(
    map(([conversation, byParent]) => (conversation && byParent.get(conversation.id)) || []),
    shareReplay(1)
  );

  /** How many side chats each message of the open conversation has. */
  readonly countsByMessage$: Observable<ReadonlyMap<number, number>> = this.sideChats$.pipe(
    map(sides => {
      const counts = new Map<number, number>();
      for (const side of sides) {
        if (side.forkMessageId != null) counts.set(side.forkMessageId, (counts.get(side.forkMessageId) ?? 0) + 1);
      }
      return counts;
    }),
    shareReplay(1)
  );

  /** The side chat the panel shows, null for a new one or when it shows the list. */
  readonly openSideChat$: Observable<Conversation | null> = combineLatest([this.state$, this.sideChats$]).pipe(
    map(([state, sides]) => (state?.view === 'chat' && state.sideId
      ? sides.find(side => side.id === state.sideId) ?? null : null)),
    shareReplay(1)
  );

  private openSideId$: Observable<string | null> = this.state$.pipe(
    map(state => (state?.view === 'chat' ? state.sideId : null)),
    distinctUntilChanged()
  );

  // The side chat's answer: started here, or followed while it is written
  private answers = new AnswerFollower(
    {
      streamingService: this.streamingService,
      messageRepository: this.messageRepository,
      conversationRepository: this.conversationRepository,
      apiService: this.apiService,
      notificationService: this.notificationService,
      translate: this.translate
    },
    {
      storedMessages: conversationId => firstValueFrom(this.messageRepository.getByConversationId(conversationId)),
      canFollow: conversationId => this.openSideId === conversationId
    }
  );

  /** The answer being written in the open side chat, as the panel shows it. */
  readonly streamingMessage$: Observable<Message<AgentContent> | null> = this.answers.streamingMessage$.asObservable();
  /** Whether an answer is being written in the open side chat. */
  readonly isStreaming$: Observable<boolean> = this.answers.isStreaming$.asObservable();

  // A new side chat's model and agent, where its composer picked others than its conversation's
  private draftSelection$ = new BehaviorSubject<Partial<IConversationSelection>>({});

  /**
   * The model and agent of the side chat the panel shows (the picker in its composer): a new one
   * has its conversation's, unless picked otherwise before its first message.
   */
  readonly selection$: Observable<IConversationSelection> = combineLatest([
    this.state$, this.openSideChat$, this.chatState.activeConversation$, this.draftSelection$
  ]).pipe(
    map(([state, open, parent, draft]) => {
      if (state?.view === 'chat' && state.sideId && open) {
        return open.selection;
      }
      const base = parent?.selection ?? { modelId: null, personaId: null, personaValues: null };
      return { ...base, ...draft };
    }),
    shareReplay(1)
  );

  /** The catalog model that answers in the side chat the panel shows; null without a catalog. */
  readonly effectiveModel$: Observable<IPublicModel | null> = combineLatest([
    this.selection$, this.catalogService.models$, this.settingsState.settings$
  ]).pipe(
    map(([selection, models, settings]) =>
      this.catalogService.resolveModel(selection.modelId, settings?.defaultModelId, models)),
    shareReplay(1)
  );

  /** The agent of the side chat the panel shows, if it is (still) in the catalog. */
  readonly activePersona$: Observable<IPublicPersona | null> = combineLatest([
    this.selection$, this.catalogService.personas$
  ]).pipe(
    map(([selection, personas]) => personas.find(persona => persona.id === selection.personaId) ?? null),
    shareReplay(1)
  );

  /** The stored messages of the open side chat (without the answer being written), in order. */
  readonly messages$: Observable<Message[]> = combineLatest([
    this.openSideId$.pipe(switchMap(id => (id ? this.messageRepository.getByConversationId(id) : of([])))),
    this.answers.streamingMessage$
  ]).pipe(
    map(([messages, streaming]) => messages
      .filter(message => !streaming || message.id !== streaming.id)
      .sort(Message.compare)),
    shareReplay(1)
  );

  constructor(
    private chatState: ChatStateService,
    private conversationRepository: ConversationRepository,
    private messageRepository: MessageRepository,
    private apiService: ApiService,
    private streamingService: StreamingService,
    private notificationService: NotificationService,
    private translate: TranslateService,
    private catalogService: CatalogService,
    private settingsState: SettingsStateService
  ) {
    // The panel belongs to its conversation: opening another one closes it
    this.chatState.activeConversation$.pipe(takeUntil(this.destroy$)).subscribe(conversation => {
      const state = this.state$.getValue();
      if (state && conversation?.id !== state.parentId) {
        this.close();
      }
    });
    // A link to a side chat opened its conversation: the panel shows the side chat
    this.chatState.sideChatRequests$.pipe(takeUntil(this.destroy$)).subscribe(request => {
      this.state$.next({ parentId: request.parentId, view: 'chat', sideId: request.sideId,
                         forkMessageId: null, focusForkId: null });
    });
    // The side chat that opens: its messages from the server, and its answer if one is being written
    this.openSideId$.pipe(takeUntil(this.destroy$)).subscribe(id => {
      if (this.answers.followedConversationId && this.answers.followedConversationId !== id) {
        this.answers.leave();  // It goes on on the server; opening the side chat again follows it again
      }
      if (id) this.refresh(id);
    });
    // While a side chat is open: its sync every minute and when the app comes back
    interval(SYNC_INTERVAL_MS).pipe(takeUntil(this.destroy$)).subscribe(() => this.refreshOpen());
    document.addEventListener('visibilitychange', this.onVisible);
  }

  private get openSideId(): string | null {
    const state = this.state$.getValue();
    return state?.view === 'chat' ? state.sideId : null;
  }

  private onVisible = (): void => {
    if (!document.hidden) this.refreshOpen();
  };

  private refreshOpen(): void {
    const id = this.openSideId;
    if (id) this.refresh(id);
  }

  private refresh(id: string): void {
    void this.answers.follow(id);
    this.conversationRepository.syncConversation(id).catch(console.error);
  }

  // =========================================================================
  // Opening and closing
  // =========================================================================

  /** The open conversation's side chats; focusForkId marks those of one message. */
  openList(focusForkId: number | null = null): void {
    const parentId = this.chatState.getActiveConversationId();
    if (!parentId || parentId === '0') return;
    this.state$.next({ parentId, view: 'list', sideId: null, forkMessageId: null, focusForkId });
  }

  /** A new side chat, forked from this message of the open conversation (created with its first message). */
  openNew(message: Message): void {
    const parentId = this.chatState.getActiveConversationId();
    if (!parentId || parentId === '0' || message.isLocal || message.conversationId !== parentId) return;
    this.draftSelection$.next({});
    this.state$.next({ parentId, view: 'chat', sideId: null, forkMessageId: message.id, focusForkId: null });
  }

  /** One of the open conversation's side chats. */
  openSide(sideId: string): void {
    const parentId = this.chatState.getActiveConversationId();
    if (!parentId || parentId === '0') return;
    this.state$.next({ parentId, view: 'chat', sideId, forkMessageId: null, focusForkId: null });
  }

  /** The panel of a message's side chats: the side chat if it has one, else the list with them marked. */
  async openForMessage(messageId: number): Promise<void> {
    const sides = (await firstValueFrom(this.sideChats$)).filter(side => side.forkMessageId === messageId);
    if (sides.length === 1) {
      this.openSide(sides[0].id);
    } else {
      this.openList(messageId);
    }
  }

  close(): void {
    if (this.state$.getValue()) this.state$.next(null);
  }

  // =========================================================================
  // The model and agent (the picker in the panel's composer)
  // =========================================================================

  /** The model of the side chat the panel shows (null: the user's default model). */
  async selectModel(modelId: number | null): Promise<void> {
    await this.select({ modelId });
  }

  /** The agent of the side chat the panel shows (null: none), with the values for its variables. */
  async selectPersona(persona: IPublicPersona | null, values: PersonaValues | null = null): Promise<void> {
    await this.select({
      personaId: persona ? persona.id : null,
      personaValues: persona && values && Object.keys(values).length > 0 ? values : null
    });
  }

  private async select(changes: Partial<IConversationSelection>): Promise<void> {
    const id = this.openSideId;
    if (id) {
      await this.conversationRepository.updateSelection(id, changes);
    } else {
      this.draftSelection$.next({ ...this.draftSelection$.getValue(), ...changes });
    }
  }

  // =========================================================================
  // Writing
  // =========================================================================

  /**
   * Send a message in the open side chat, with files attached, and stream its answer. A new side
   * chat is created with it, forked from its message, with a title from the model.
   */
  async send(text: string, files: FilePreview[] = []): Promise<void> {
    const state = this.state$.getValue();
    const content = text.trim();
    if (!state || state.view !== 'chat' || (!content && !files.length) || this.answers.isStreaming$.getValue()) return;

    let sideId = state.sideId;
    if (!sideId) {
      if (state.forkMessageId == null) return;
      const name = content || files.map(file => file.name).join(', ') || this.translate.instant('sideChat.new');
      const draft = new Conversation('', 0, name.length > 50 ? name.substring(0, 47).trim() + '...' : name,
                                     ['user', 'Assistant']);
      draft.parentId = state.parentId;
      draft.forkMessageId = state.forkMessageId;
      // A model or agent its composer picked (else the server gives it its conversation's)
      const picked = this.draftSelection$.getValue();
      if (picked.modelId !== undefined) draft.modelId = picked.modelId;
      if (picked.personaId !== undefined) {
        draft.personaId = picked.personaId;
        draft.personaValues = picked.personaValues ?? null;
      }
      const created = await this.apiService.createConversation(draft);
      await this.conversationRepository.save(created);
      sideId = created.id;
      if (this.state$.getValue() === state) {
        this.state$.next({ ...state, sideId });
      }
      if (content) {
        this.apiService.generateConversationTitle(sideId, content)
          .then(titled => this.conversationRepository.saveFromServer(titled))
          .catch(error => console.warn('Failed to generate the side chat\'s title:', error));
      }
    }

    await this.uploadPending(files);
    const userMessage: MessageWithSyncStatus = Message.createText(
      { id: Message.localId(), conversationId: sideId, roleName: 'user', time: new Date() }, content, files);
    await this.conversationRepository.markMessageSent(sideId);
    await this.messageRepository.save(userMessage);
    if (userMessage.isLocal) {
      userMessage.syncStatus = 'failed';
      throw new Error('The message was not sent');
    }
    await this.conversationRepository.recordMessage(sideId, userMessage.id);
    this.answers.start(sideId);
  }

  /** Files the composer couldn't upload yet (it uploads them as they are attached) go now. */
  private async uploadPending(files: FilePreview[]): Promise<void> {
    const pending = files.filter(file => file.uploadStatus === UploadStatus.PENDING);
    if (!pending.length) return;
    try {
      const uploaded = await this.apiService.uploadFiles(pending);
      pending.forEach((file, index) => {
        file.uploadStatus = UploadStatus.COMPLETED;
        file.id = uploaded[index]?.fileId || file.id;
        file.transcript = uploaded[index]?.transcript || file.transcript;
      });
    } catch (error) {
      pending.forEach(file => {
        file.uploadStatus = UploadStatus.FAILED;
        file.error = 'Upload failed';
      });
      throw error;
    }
  }

  /** Stop the answer being written in the open side chat; what was written is kept. */
  async stop(): Promise<void> {
    await this.answers.cancel();
  }

  /** A new version of an answer of the open side chat (with modelId: by that model). */
  async regenerate(message: Message, modelId?: number): Promise<void> {
    if (this.answers.isStreaming$.getValue()) {
      throw new Error('Wait until the answer is complete');
    }
    if (message.isLocal) {
      await this.messageRepository.delete(message.id);
      this.answers.start(message.conversationId, modelId);
    } else {
      this.answers.start(message.conversationId, modelId, message);
    }
  }

  /** Delete a message of the open side chat. */
  async deleteMessage(messageId: number): Promise<void> {
    await this.messageRepository.delete(messageId);
  }

  /**
   * Make the open side chat a conversation of its own: it moves to the sidebar (with copies of the
   * messages it needs) and the panel closes. Returns the conversation.
   */
  async promote(): Promise<Conversation | null> {
    const id = this.openSideId;
    if (!id || this.answers.isStreaming$.getValue()) return null;
    this.answers.leave();
    const conversation = await this.conversationRepository.promote(id);
    this.close();
    return conversation;
  }

  /** Delete a side chat; the list shows again. */
  async deleteSideChat(sideId: string): Promise<void> {
    if (this.answers.followedConversationId === sideId) {
      this.answers.leave();
    }
    await this.conversationRepository.delete(sideId, 'delete');
    const state = this.state$.getValue();
    if (state?.sideId === sideId) {
      this.openList();
    }
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
    document.removeEventListener('visibilitychange', this.onVisible);
    this.answers.leave();
  }
}
