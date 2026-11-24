// src/app/services/side-chat.service.ts
import { Injectable, OnDestroy } from '@angular/core';
import { TranslateService } from '@ngx-translate/core';
import { BehaviorSubject, Observable, Subject, combineLatest, firstValueFrom, interval, of } from 'rxjs';
import { distinctUntilChanged, map, shareReplay, switchMap, takeUntil } from 'rxjs/operators';
import { Conversation } from '../data/objects/conversation';
import { AgentContent, Message } from '../data/objects/message';
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
    private translate: TranslateService
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
  // Writing
  // =========================================================================

  /**
   * Send a message in the open side chat and stream its answer. A new side chat is created with
   * it, forked from its message, with a title from the model.
   */
  async send(text: string): Promise<void> {
    const state = this.state$.getValue();
    const content = text.trim();
    if (!state || state.view !== 'chat' || !content || this.answers.isStreaming$.getValue()) return;

    let sideId = state.sideId;
    if (!sideId) {
      if (state.forkMessageId == null) return;
      const draft = new Conversation('', 0, content.length > 50 ? content.substring(0, 47).trim() + '...' : content,
                                     ['user', 'Assistant']);
      draft.parentId = state.parentId;
      draft.forkMessageId = state.forkMessageId;
      const created = await this.apiService.createConversation(draft);
      await this.conversationRepository.save(created);
      sideId = created.id;
      if (this.state$.getValue() === state) {
        this.state$.next({ ...state, sideId });
      }
      this.apiService.generateConversationTitle(sideId, content)
        .then(titled => this.conversationRepository.saveFromServer(titled))
        .catch(error => console.warn('Failed to generate the side chat\'s title:', error));
    }

    const userMessage: MessageWithSyncStatus = Message.createText(
      { id: Message.localId(), conversationId: sideId, roleName: 'user', time: new Date() }, content);
    await this.conversationRepository.markMessageSent(sideId);
    await this.messageRepository.save(userMessage);
    if (userMessage.isLocal) {
      userMessage.syncStatus = 'failed';
      throw new Error('The message was not sent');
    }
    await this.conversationRepository.recordMessage(sideId, userMessage.id);
    this.answers.start(sideId);
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
