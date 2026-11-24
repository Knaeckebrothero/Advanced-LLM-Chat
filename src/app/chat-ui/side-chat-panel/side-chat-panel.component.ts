import { ChangeDetectorRef, Component, ElementRef, NgZone, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';
import { TranslateService } from '@ngx-translate/core';
import { Observable, Subscription, combineLatest } from 'rxjs';
import { map } from 'rxjs/operators';
import { Conversation } from '../../data/objects/conversation';
import { AgentContent, Message } from '../../data/objects/message';
import { describeHttpError } from '../../catalog-admin/catalog-admin.utils';
import { ChatStateService } from '../../services/chat-state.service';
import { SideChatService, SidePanelState } from '../../services/side-chat.service';
import { MessageHost } from '../message-host';
import { ChatUiInputfieldComponent } from '../chat-ui-inputfield/chat-ui-inputfield.component';
import { FilePreview } from '../../data/objects/file-preview';
import { UIStateService } from '../../services/ui-state.service';
import { ConversationFilesDialogService } from '../../components/conversation-files/conversation-files-dialog.service';

/** A side chat in the panel's list. */
interface SideChatItem {
  id: string;
  title: string;
  // The start of the message it was forked from, if this browser has it
  from: string;
  fromUser: boolean;
  // When it got its newest message, or was created
  when: Date;
  // One of the side chats of the message whose badge opened the list
  focus: boolean;
}

/** What the panel shows. */
interface PanelView {
  panel: SidePanelState;
  parentName: string;
  items: SideChatItem[];
  // The open side chat
  title: string;
  isNew: boolean;
  forkId: number | null;
  forkFromUser: boolean;
  forkTime: Date | null;
  forkExcerpt: string;
}

/** How long the main chat marks the message a side chat was forked from, after "Forked from". */
const FLASH_MS = 1600;

/** The panel's width the user set by dragging its edge, kept on this device; none: the default. */
const WIDTH_KEY = 'sideChatPanelWidth';
const MIN_WIDTH = 300;
// What the chat next to the panel keeps at least
const CHAT_MIN_WIDTH = 360;
// One press of an arrow key on the edge
const WIDTH_STEP = 24;

/**
 * The side chat panel (docs/side_chats.md): next to the chat on wide screens, a sheet over it on a
 * phone. It lists the side chats of the open conversation, or shows one of them: the message it
 * was forked from, its messages (the chat's message component, without editing) and a composer.
 */
@Component({
  selector: 'app-side-chat-panel',
  templateUrl: './side-chat-panel.component.html',
  styleUrls: ['./side-chat-panel.component.scss'],
  // Its messages ask it for what they need (ChatUiMessageComponent)
  providers: [{ provide: MessageHost, useExisting: SideChatPanelComponent }],
  // Files dropped on the panel are its composer's, not the chat's (ChatUiInputfieldComponent.ownDrops)
  host: { 'data-drop-area': '' },
  standalone: false
})
export class SideChatPanelComponent implements MessageHost, OnInit, OnDestroy {
  @ViewChild(ChatUiInputfieldComponent) private composer?: ChatUiInputfieldComponent;

  userName = 'user';
  aiName = 'Assistant';
  agentAvatar: string | null = null;
  agentName: string | null = null;

  // Files attached in the composer, sent with the next message
  pendingFiles: FilePreview[] = [];
  sending = false;
  // A voice message waits for its transcript before it is sent
  transcribing = false;
  promoting = false;
  // The width the user set (null: the default), and whether its edge is being dragged
  width: number | null = null;
  resizing = false;

  readonly messages$: Observable<Message[]> = this.sideChats.messages$;
  readonly streamingMessage$: Observable<Message<AgentContent> | null> = this.sideChats.streamingMessage$;
  readonly isStreaming$: Observable<boolean> = this.sideChats.isStreaming$;

  readonly view$: Observable<PanelView | null> = combineLatest([
    this.sideChats.panel$, this.sideChats.sideChats$, this.sideChats.openSideChat$,
    this.chatState.messages$, this.chatState.activeConversation$
  ]).pipe(
    map(([panel, sides, open, parentMessages, parent]) => panel
      ? this.buildView(panel, sides, open, parentMessages, parent)
      : null)
  );

  private streaming = false;
  private messages: Message[] = [];
  private subscriptions = new Subscription();
  private flashTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    public sideChats: SideChatService,
    private chatState: ChatStateService,
    private snackBar: MatSnackBar,
    private translate: TranslateService,
    private cdr: ChangeDetectorRef,
    private host: ElementRef<HTMLElement>,
    private zone: NgZone,
    private uiState: UIStateService,
    private filesDialog: ConversationFilesDialogService
  ) {}

  get isMobile(): boolean {
    return this.uiState.isMobile;
  }

  ngOnInit(): void {
    const saved = Number(localStorage.getItem(WIDTH_KEY));
    if (saved > 0) {
      this.setWidth(saved);
    }
    // The side chat's agent (its own, which may differ from its conversation's)
    this.subscriptions.add(this.sideChats.activePersona$.subscribe(persona => {
      this.agentAvatar = persona?.avatar ?? null;
      this.agentName = persona?.name?.trim() || null;
      this.cdr.markForCheck();
    }));
    this.subscriptions.add(this.sideChats.isStreaming$.subscribe(streaming => this.streaming = streaming));
    this.subscriptions.add(this.sideChats.messages$.subscribe(messages => this.messages = messages));
    // A new side chat: the composer is ready to type in
    this.subscriptions.add(this.sideChats.panel$.subscribe(panel => {
      if (panel?.view === 'chat' && !panel.sideId && !this.isPhone()) {
        setTimeout(() => this.composer?.focusInput());
      }
    }));
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
    if (this.flashTimer) clearTimeout(this.flashTimer);
  }

  private buildView(panel: SidePanelState, sides: Conversation[], open: Conversation | null,
                    parentMessages: Message[], parent: Conversation | null): PanelView {
    const byId = new Map(parentMessages.map(message => [message.id, message]));
    const items = [...sides]
      .sort((a, b) => b.lastActivity.getTime() - a.lastActivity.getTime())
      .map(side => {
        const fork = side.forkMessageId != null ? byId.get(side.forkMessageId) : undefined;
        return {
          id: side.id,
          title: side.name,
          from: fork ? this.excerpt(fork, 70) : '',
          fromUser: fork?.roleName === 'user',
          when: side.lastActivity,
          focus: panel.focusForkId != null && side.forkMessageId === panel.focusForkId
        };
      });
    const forkId = panel.view === 'chat' ? (panel.sideId ? open?.forkMessageId ?? null : panel.forkMessageId) : null;
    const fork = forkId != null ? byId.get(forkId) : undefined;
    return {
      panel,
      parentName: parent?.name ?? '',
      items,
      title: open?.name ?? this.translate.instant('sideChat.new'),
      isNew: panel.view === 'chat' && !panel.sideId,
      forkId,
      forkFromUser: fork?.roleName === 'user',
      // A message id is the server's clock in milliseconds: its time, also when this browser hasn't loaded it
      forkTime: forkId != null && forkId > 0 ? new Date(forkId) : null,
      forkExcerpt: fork ? this.excerpt(fork, 180) : ''
    };
  }

  /** The start of a message's text, on one line. */
  private excerpt(message: Message, length: number): string {
    const text = (message.isText() ? message.content.content : message.isAgent() ? message.content.content : '') ?? '';
    const plain = text.replace(/[#*_`>]+/g, '').replace(/\s+/g, ' ').trim();
    return plain.length > length ? plain.slice(0, length).replace(/\s+\S*$/, '') + '…' : plain;
  }

  private isPhone(): boolean {
    return window.matchMedia('(max-width: 768px)').matches;
  }

  // =========================================================================
  // The panel
  // =========================================================================

  close(): void {
    this.sideChats.close();
  }

  openList(): void {
    this.sideChats.openList();
  }

  openSide(id: string): void {
    this.sideChats.openSide(id);
  }

  /** Show the message the side chat was forked from in the chat, marked for a moment (the sheet closes on a phone). */
  showFork(forkId: number | null): void {
    if (forkId == null) return;
    if (this.isPhone()) {
      this.close();
    }
    setTimeout(() => {
      const element = document.querySelector<HTMLElement>(`app-chat-ui app-chat-ui-message[data-message-id="${forkId}"]`);
      if (!element || this.host.nativeElement.contains(element)) return;
      element.scrollIntoView({ block: 'center', behavior: 'smooth' });
      element.classList.add('side-chat-fork--flash');
      if (this.flashTimer) clearTimeout(this.flashTimer);
      this.flashTimer = setTimeout(() => element.classList.remove('side-chat-fork--flash'), FLASH_MS);
    });
  }

  // =========================================================================
  // Its width: the edge is dragged like a splitter (wide screens only)
  // =========================================================================

  /** Drag the panel's left edge: wider to the left, narrower to the right. */
  startResize(event: PointerEvent): void {
    if (event.button !== 0) return;
    event.preventDefault();
    const handle = event.currentTarget as HTMLElement;
    handle.setPointerCapture(event.pointerId);
    const startX = event.clientX;
    const startWidth = this.host.nativeElement.getBoundingClientRect().width;
    this.resizing = true;
    document.body.classList.add('side-chat-resizing');
    // Outside Angular: a move changes only a style, the chat doesn't need to be checked for it
    this.zone.runOutsideAngular(() => {
      const move = (moved: PointerEvent) => this.setWidth(startWidth + startX - moved.clientX);
      const end = () => {
        handle.removeEventListener('pointermove', move);
        handle.removeEventListener('pointerup', end);
        handle.removeEventListener('pointercancel', end);
        document.body.classList.remove('side-chat-resizing');
        this.zone.run(() => {
          this.resizing = false;
          this.saveWidth();
        });
      };
      handle.addEventListener('pointermove', move);
      handle.addEventListener('pointerup', end);
      handle.addEventListener('pointercancel', end);
    });
  }

  /** The arrow keys on the focused edge: left widens, right narrows; Home and End go to the limits. */
  onResizeKey(event: KeyboardEvent): void {
    const current = this.host.nativeElement.getBoundingClientRect().width;
    const widths: Record<string, number> = {
      ArrowLeft: current + WIDTH_STEP, ArrowRight: current - WIDTH_STEP, Home: this.maxWidth(), End: MIN_WIDTH
    };
    if (!(event.key in widths)) return;
    event.preventDefault();
    this.setWidth(widths[event.key]);
    this.saveWidth();
  }

  /** Back to the default width (a double-click on the edge). */
  resetWidth(): void {
    this.width = null;
    this.host.nativeElement.style.removeProperty('--side-panel-width');
    localStorage.removeItem(WIDTH_KEY);
  }

  /** The widest the panel may get: the chat next to it keeps CHAT_MIN_WIDTH. */
  maxWidth(): number {
    const layout = this.host.nativeElement.parentElement?.getBoundingClientRect().width ?? window.innerWidth;
    return Math.max(MIN_WIDTH, Math.round(layout - CHAT_MIN_WIDTH));
  }

  private setWidth(width: number): void {
    this.width = Math.round(Math.min(Math.max(width, MIN_WIDTH), this.maxWidth()));
    this.host.nativeElement.style.setProperty('--side-panel-width', `${this.width}px`);
  }

  private saveWidth(): void {
    if (this.width !== null) {
      localStorage.setItem(WIDTH_KEY, String(this.width));
    }
  }

  // =========================================================================
  // Writing
  // =========================================================================

  /** The composer sent a message: with the files attached in it. */
  async onMessageSent(text: string): Promise<void> {
    const files = this.pendingFiles;
    if ((!text.trim() && !files.length) || this.sending || this.streaming) return;
    this.pendingFiles = [];
    await this.send(text, files);
  }

  /**
   * Files attached in the composer: kept for the next message. A voice message is sent on its own,
   * with its transcript as its text, once the transcript is there.
   */
  async onFilesSelected(files: FilePreview[]): Promise<void> {
    const voice = files.length === 1 && files[0].mimeType.startsWith('audio/') && files[0].name.includes('Voice message')
      ? files[0] : null;
    if (!voice) {
      this.pendingFiles = files;
      return;
    }
    if ((voice as any).isSent) return;
    (voice as any).isSent = true;
    this.transcribing = true;
    const transcript = await this.waitForTranscript(voice, 30000);
    this.transcribing = false;
    await this.send(transcript, [voice]);
  }

  private async send(text: string, files: FilePreview[]): Promise<void> {
    this.sending = true;
    try {
      await this.sideChats.send(text, files);
    } catch (error) {
      console.error('Failed to send in the side chat:', error);
      this.showError('sideChat.sendFailed', error);
    } finally {
      this.sending = false;
      this.cdr.markForCheck();
    }
  }

  /** The transcript of a voice message the composer uploads, once it is there (else a stand-in text). */
  private waitForTranscript(voice: FilePreview, timeoutMs: number): Promise<string> {
    const started = Date.now();
    return new Promise(resolve => {
      const check = () => {
        if (voice.transcript) return resolve(voice.transcript);
        if (voice.uploadStatus === 'failed') return resolve('Voice message (transcription failed)');
        if (Date.now() - started > timeoutMs) return resolve('Voice message');
        setTimeout(check, 200);
      };
      check();
    });
  }

  /** "Files of this chat" in the composer: the side chat's files (with its conversation's up to the fork). */
  showFiles(sideId: string | null, title: string): void {
    if (sideId) void this.filesDialog.open(sideId, title);
  }

  stop(): void {
    void this.sideChats.stop();
  }

  async promote(): Promise<void> {
    if (this.promoting) return;
    this.promoting = true;
    try {
      const conversation = await this.sideChats.promote();
      if (conversation) {
        this.snackBar.open(this.translate.instant('sideChat.promoted', { name: conversation.name }),
                           this.translate.instant('sideChat.openPromoted'), { duration: 6000 })
          .onAction().subscribe(() => void this.chatState.loadConversation(conversation.id));
      }
    } catch (error) {
      console.error('Failed to make the side chat a conversation:', error);
      this.showError('sideChat.promoteFailed', error);
    } finally {
      this.promoting = false;
      this.cdr.markForCheck();
    }
  }

  async deleteSide(id: string): Promise<void> {
    if (!confirm(this.translate.instant('sideChat.deleteConfirm'))) return;
    try {
      await this.sideChats.deleteSideChat(id);
    } catch (error) {
      console.error('Failed to delete the side chat:', error);
      this.showError('sideChat.deleteFailed', error);
    }
  }

  private showError(key: string, error: unknown): void {
    this.snackBar.open(this.translate.instant(key, { error: describeHttpError(error, this.translate) }),
                       undefined, { duration: 6000 });
  }

  /** The newest answer of the side chat (it can be regenerated). */
  isLastAiMessage(message: Message, index: number, messages: Message[]): boolean {
    if (message.roleName === 'user' || message.roleName === 'system') return false;
    return !messages.slice(index + 1).some(later => later.roleName !== 'user' && later.roleName !== 'system');
  }

  trackById(_: number, message: Message): number {
    return message.id;
  }

  // =========================================================================
  // MessageHost: what the side chat's messages ask for
  // =========================================================================

  get isStreaming(): boolean {
    return this.streaming;
  }

  get canEdit(): boolean {
    return false;
  }

  get canForkSideChats(): boolean {
    return false;
  }

  sideChatCount(): number {
    return 0;
  }

  openSideChat(): void {}

  openSideChatsOf(): void {}

  deleteMessage(messageId: number): void {
    this.sideChats.deleteMessage(messageId).catch(error => this.showError('sideChat.deleteFailed', error));
  }

  switchAlternative(message: Message, position: number): Promise<void> {
    return this.chatState.switchAlternative(message, position);
  }

  deleteAlternative(message: Message): Promise<void> {
    return this.chatState.deleteAlternative(message);
  }

  patchMessage(): Promise<void> {
    return Promise.reject(new Error('Side chats are not edited'));
  }

  resendEditedMessage(): Promise<void> {
    return Promise.reject(new Error('Side chats are not edited'));
  }

  insertMessage(): Promise<void> {
    return Promise.reject(new Error('Side chats are not edited'));
  }

  resendMessage(): Promise<void> {
    return Promise.reject(new Error('Side chats are not edited'));
  }

  countMessagesAfter(message: Message): number {
    return this.messages.filter(other => Message.compare(other, message) > 0).length;
  }

  regenerateMessage(message: Message, modelId?: number): void {
    this.sideChats.regenerate(message, modelId).catch(error => this.showError('sideChat.sendFailed', error));
  }

  rateMessage(message: Message, rating: number | null): void {
    this.chatState.rateMessage(message, rating).catch(error => console.error('Failed to rate message:', error));
  }
}
