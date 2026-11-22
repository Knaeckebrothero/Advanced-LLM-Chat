import { Component, ViewChild, ElementRef, AfterViewChecked, AfterViewInit, OnInit, OnDestroy, ChangeDetectorRef, NgZone } from '@angular/core';
import { Message, AgentContent } from '../data/objects/message';
import { AuthService } from '../auth/auth.service';
import { BehaviorSubject, Subject, Subscription, Observable, combineLatest, firstValueFrom, from, merge, of } from 'rxjs';
import { map, filter, distinctUntilChanged, debounceTime, switchMap, catchError, shareReplay } from 'rxjs/operators';
import { FilePreview, FilePreviewUtil } from '../data/objects/file-preview';
import { RecordingResult } from '../data/objects/recording';
import { ChatStateService } from '../services/chat-state.service';
import { UIStateService } from '../services/ui-state.service';
import { ThemeService } from '../services/theme.service';
import { SettingsStateService } from '../services/settings-state.service';
import { ChatUiInputfieldComponent } from './chat-ui-inputfield/chat-ui-inputfield.component';
import { IPublicModel } from '../data/models/catalog.model';
import { IContextSize, IConversationSummary, ISystemPrompt } from '../data/models/conversation.model';
import { ApiService } from '../services/api.service';
import { MatSnackBar } from '@angular/material/snack-bar';
import { TranslateService } from '@ngx-translate/core';
import { FamilyModeService } from '../services/family-mode.service';
import { ConversationFilesDialogService } from '../components/conversation-files/conversation-files-dialog.service';


@Component({
  selector: 'app-chat-ui',
  templateUrl: './chat-ui.component.html',
  styleUrls: ['./chat-ui.component.scss'],
  standalone: false
})
export class ChatUiComponent implements AfterViewChecked, AfterViewInit, OnInit, OnDestroy {

  // The messageContainer property is bound to the message container in the template.
  @ViewChild('messageContainer') private messageContainer!: ElementRef<HTMLElement>;

  // The thread inside it, and the room under its last message (see "Where the view stands")
  @ViewChild('messageList') private messageList!: ElementRef<HTMLElement>;
  @ViewChild('turnReserve') private turnReserve!: ElementRef<HTMLElement>;

  // Reference to the chat input field component for programmatic focus
  @ViewChild(ChatUiInputfieldComponent) private chatInputField!: ChatUiInputfieldComponent;

  // Variables
  userName: string = 'user';
  aiName: string = 'Assistant';
  // The image of the conversation's agent, shown with its answers (null: none, an icon is shown)
  agentAvatar: string | null = null;
  // The name of the conversation's agent, the name on its answers (null: no agent, "Assistant")
  agentName: string | null = null;
  pendingFiles: FilePreview[] = [];
  isDarkMode: boolean = false; // Add this property

  // The inputField property is bound to the input field in the template.
  inputField: string = '';

  // Observable state from ChatStateService
  isLoading$: Observable<boolean> = this.chatState.state$.pipe(map(state => state.isLoading));
  error$: Observable<string | null> = this.chatState.state$.pipe(map(state => state.error));
  hasReachedEnd$: Observable<boolean> = this.chatState.state$.pipe(map(state => state.hasReachedEnd || false));

  // Streaming state
  streamingMessage$: Observable<Message<AgentContent> | null> = this.chatState.state$.pipe(
    map(state => state.streamingMessage)
  );
  isStreaming$: Observable<boolean> = this.chatState.state$.pipe(map(state => state.isStreaming));

  // The catalog model that answers in this conversation (null without a catalog)
  effectiveModel$: Observable<IPublicModel | null> = this.chatState.effectiveModel$;

  // Messages filtered to exclude the streaming message (prevents duplicate during transition)
  // This ensures smooth handoff: while streaming, the message shows from streamingMessage$;
  // when streaming ends, the persisted version appears in messages$ without overlap
  messages$: Observable<Message[]> = combineLatest([
    this.chatState.messages$,
    this.streamingMessage$
  ]).pipe(
    map(([messages, streamingMsg]) => {
      if (!streamingMsg || !streamingMsg.id) {
        return messages;
      }
      // Filter out the streaming message from persisted list to prevent duplicates
      return messages.filter(m => m.id !== streamingMsg.id);
    })
  );

  // For template compatibility
  messages = this.messages$;

  // The summary of the oldest messages, shown after the newest message it covers that is loaded
  summaryDivider$: Observable<{ summary: IConversationSummary; afterId: number } | null> = combineLatest([
    this.messages$,
    this.chatState.conversationSummary$
  ]).pipe(
    map(([messages, summary]) => {
      if (!summary) return null;
      const covered = messages.filter(m => m.id > 0 && m.id <= summary.coversUntil);
      return covered.length > 0 ? { summary, afterId: covered[covered.length - 1].id } : null;
    })
  );

  // A summary being written at the user's request (from the conversation's menu)
  isSummarizing$ = this.chatState.isSummarizing$;

  // A new conversation without messages yet shows a short greeting
  showEmptyState$: Observable<boolean> = combineLatest([
    this.chatState.activeConversation$,
    this.messages$,
    this.streamingMessage$
  ]).pipe(
    map(([conversation, messages, streaming]) =>
      (!conversation || conversation.id === '0') && messages.length === 0 && !streaming),
    distinctUntilChanged()
  );

  // The attach menu offers "Files of this chat" once the server has the conversation
  hasStoredConversation$: Observable<boolean> = this.chatState.activeConversation$.pipe(
    map(conversation => !!conversation && conversation.id !== '0'),
    distinctUntilChanged()
  );

  /** Every file of this conversation, to open and download. */
  async showChatFiles(): Promise<void> {
    const conversation = await firstValueFrom(this.chatState.activeConversation$);
    if (conversation && conversation.id !== '0') this.filesDialog.open(conversation.id, conversation.name);
  }

  // Manual editing: the composer offers Generate whenever the conversation has a stored message
  // (system messages aside, they belong to the system prompt): the model answers the conversation
  // as it stands. 'answer': the newest message is the user's and has no answer yet. 'continue':
  // it is an answer, and the server asks the model to go on from it (CONTINUE_NOTE in
  // backend/services/conversation_history.py), since no provider answers a history that ends
  // with the model's own message.
  generateKind$: Observable<'answer' | 'continue' | null> = combineLatest([
    this.settingsState.settings$,
    this.messages$
  ]).pipe(
    map(([settings, messages]) => {
      if (settings.editingMode !== 'manual') return null;
      const newest = [...messages].reverse().find(m => m.roleName !== 'system');
      if (!newest || newest.id <= 0) return null;
      return newest.roleName === 'user' ? 'answer' as const : 'continue' as const;
    }),
    distinctUntilChanged()
  );
  canGenerate$: Observable<boolean> = this.generateKind$.pipe(map(kind => kind !== null));

  // A saved change of the system prompt: shown at once, and the input tokens are counted again
  private systemPromptEdited$ = new Subject<ISystemPrompt>();
  private systemPromptSaved$ = new BehaviorSubject<number>(0);

  // Manual editing: about how many input tokens the next answer sends. The backend counts again
  // whenever the messages, the summary, the model or the agent change (the effective model follows
  // the selection); only with a session, since a 401 would open the login page. Null hides it.
  contextSize$: Observable<IContextSize | null> = combineLatest([
    this.settingsState.settings$.pipe(map(settings => settings.editingMode === 'manual'), distinctUntilChanged()),
    this.authService.currentUser$.pipe(map(user => user !== null), distinctUntilChanged()),
    this.chatState.activeConversation$,
    this.chatState.messages$,
    this.chatState.conversationSummary$,
    this.chatState.effectiveModel$,
    this.systemPromptSaved$
  ]).pipe(
    debounceTime(300),
    switchMap(([manual, signedIn, conversation, , , model]) => {
      if (!manual || !signedIn || !conversation || conversation.id === '0') return of(null);
      return from(this.apiService.getContextSize(conversation.id, model?.id)).pipe(catchError(() => of(null)));
    }),
    shareReplay({ bufferSize: 1, refCount: true })
  );

  // Manual editing: the system prompt the next answer gets, shown as the conversation's first
  // message. The backend builds it again whenever the conversation, its agent or the model
  // change, when an answer is done (it may have changed the agent's memory) and when family mode
  // is switched; a saved change shows at once. Null hides it.
  systemPrompt$: Observable<ISystemPrompt | null> = merge(
    combineLatest([
      this.settingsState.settings$.pipe(map(settings => settings.editingMode === 'manual'), distinctUntilChanged()),
      this.authService.currentUser$.pipe(map(user => user !== null), distinctUntilChanged()),
      this.chatState.activeConversation$,
      this.chatState.effectiveModel$,
      this.chatState.state$.pipe(map(state => !!state.isStreaming), distinctUntilChanged()),
      this.familyMode.active$
    ]).pipe(
      debounceTime(300),
      switchMap(([manual, signedIn, conversation, model, streaming]) => {
        if (!manual || !signedIn || !conversation || conversation.id === '0') return of(null);
        if (streaming) return of(undefined);  // Keep what is shown while the answer is written
        return from(this.apiService.getSystemPrompt(conversation.id, model?.id)).pipe(catchError(() => of(null)));
      }),
      filter((prompt): prompt is ISystemPrompt | null => prompt !== undefined)
    ),
    this.systemPromptEdited$
  ).pipe(shareReplay({ bufferSize: 1, refCount: true }));
  systemPromptBusy = false;
  systemPromptFailed = false;

  /** Save the conversation's own system prompt ('' for none), or go back to the built one (null). */
  async saveSystemPrompt(content: string | null): Promise<void> {
    const [conversation, model] = await firstValueFrom(
      combineLatest([this.chatState.activeConversation$, this.chatState.effectiveModel$]));
    if (!conversation || conversation.id === '0' || this.systemPromptBusy) return;
    this.systemPromptBusy = true;
    this.systemPromptFailed = false;
    try {
      this.systemPromptEdited$.next(await this.apiService.setSystemPrompt(conversation.id, content, model?.id));
      this.systemPromptSaved$.next(this.systemPromptSaved$.value + 1);
    } catch (error) {
      console.error('Error saving the system prompt:', error);
      this.systemPromptFailed = true;
    } finally {
      this.systemPromptBusy = false;
    }
  }

  // The thread goes on below the view: a button jumps to the newest message
  showScrollToBottom = false;

  // Mobile state from UIStateService
  isMobile$ = this.uiState.isMobile$;

  showGuestLimitWarning = false;
  guestLimitWarningMessage: string | null = null;
  private guestLimitSubscription!: Subscription;
  private guestLimitResetTimeSubscription!: Subscription;
  private destroy$ = new Subscription();
  private themeSubscription!: Subscription; // Add this property

  // Add this property to hold the current state
  private hasReachedEnd = false;

  constructor(
    private chatState: ChatStateService,
    private uiState: UIStateService,
    private authService: AuthService,
    private themeService: ThemeService,
    private settingsState: SettingsStateService,
    private apiService: ApiService,
    private cdr: ChangeDetectorRef,
    private snackBar: MatSnackBar,
    private translate: TranslateService,
    private familyMode: FamilyModeService,
    private filesDialog: ConversationFilesDialogService,
    private ngZone: NgZone
  ) { }

  ngOnInit() {
    this.destroy$.add(
      this.chatState.activePersona$.subscribe(persona => {
        this.agentAvatar = persona?.avatar ?? null;
        this.agentName = persona?.name?.trim() || null;
        this.cdr.markForCheck();
      })
    );

    // An agent hid its chat while answering : say so, and let the user take it back
    this.destroy$.add(
      this.chatState.agentHideMarks$.subscribe(({ conversationId, hidden }) => {
        if (!hidden || !this.familyMode.available) return;
        const key = this.familyMode.active ? 'hide.agentMarkedHidden' : 'hide.agentMarked';
        this.snackBar.open(this.translate.instant(key), this.translate.instant('hide.undo'), { duration: 10000 })
          .onAction().subscribe(() => void this.chatState.setConversationHidden(conversationId, false));
      })
    );

    // Add this block to subscribe to theme changes
    this.themeSubscription = this.themeService.theme$.subscribe(() => {
      this.isDarkMode = this.themeService.getCurrentEffectiveTheme() === 'dark';
    });

    this.guestLimitSubscription = this.authService.guestLimitReached$.subscribe(isReached => {
      this.showGuestLimitWarning = isReached;
    });
    this.guestLimitResetTimeSubscription = this.authService.guestLimitResetTime$.subscribe(message => {
      this.guestLimitWarningMessage = message;
    });

    // Subscribe to the hasReachedEnd$ observable to keep our local property in sync
    this.destroy$.add(
      this.hasReachedEnd$.subscribe(value => {
        this.hasReachedEnd = value;
      })
    );

    this.destroy$.add(
      this.messages$.subscribe(messages => {
        const previousLength = this.currentMessages.length;
        this.currentMessages = messages || [];

        if (this.turnRequested) {
          // The message the user just sent is in the thread: its turn goes to the top of the view
          if (this.currentMessages.length > previousLength) this.placePending = true;
        } else if (previousLength === 0 && this.currentMessages.length > 0) {
          // A conversation's messages arrive: it opens at its end
          this.stick = true;
        }
      })
    );

    // Keep the pending summary at the end of the chat in view
    this.destroy$.add(
      this.isSummarizing$.pipe(filter(Boolean)).subscribe(() => {
        if (this.endIsInView()) setTimeout(() => this.scrollToEnd(), 0);
      })
    );

    // Another conversation opens at its end. Not the conversation that the first message of a
    // new chat creates: its turn is being placed
    this.destroy$.add(
      this.chatState.activeConversation$.pipe(
        map(conversation => conversation?.id ?? null),
        distinctUntilChanged()
      ).subscribe(() => {
        if (this.turnRequested) return;
        this.turn = null;
        this.keptTurnTop = null;
        this.placePending = false;
        this.stick = true;
        this.standing = false;
        this.showScrollToBottom = false;
        this.smoothTarget = null;
        this.updateAnchoring();
      })
    );

    // An answer starts: its turn goes to the top of the view and stays there while it is written
    this.destroy$.add(
      this.isStreaming$.pipe(distinctUntilChanged()).subscribe(streaming => {
        if (streaming) {
          this.placePending = true;
          this.stick = false;
        } else {
          this.placePending = false;
        }
        this.turnRequested = false;
        this.updateAnchoring();
      })
    );
  }

  ngAfterViewInit() {
    // Focus input field when a new conversation is created
    this.destroy$.add(
      this.chatState.isNewConversation$.pipe(
        filter(isNew => isNew)
      ).subscribe(() => {
        // Small delay to ensure the view is ready
        setTimeout(() => this.chatInputField?.focusInput(), 0);
      })
    );

    this.watchThread();
  }

  // Handle scroll events: where the reader stands, and older messages near the top
  onScroll(event: Event): void {
    if (this.isRestoringScroll) return;

    const element = event.target as HTMLElement;
    const previousScrollTop = this.lastScrollTop;
    this.lastScrollTop = element.scrollTop;

    if (this.smoothTarget !== null) {
      // The view is on its way (to a new turn, or to the end): no sign of what the reader wants
      if (Math.abs(element.scrollTop - this.smoothTarget) < 2) this.arrived(element);
    } else if (this.standing && this.keptTurnTop !== null && Math.abs(element.scrollTop - this.keptTurnTop) > 2
      && !(element.scrollTop < this.keptTurnTop && this.gapBelow(element) <= 1)) {
      // The view left the turn (the browser's search, say; not just pushed up by a thread that
      // got shorter, which onThreadResized() undoes): it no longer stands there
      this.standing = false;
      this.updateAnchoring();
    } else if (element.scrollTop < previousScrollTop - 2 && this.gapBelow(element) > 2) {
      // The reader went up: the view stays with them. (A thread that got shorter also moves the
      // view up, but leaves it at the end)
      this.stick = false;
    } else if (element.scrollTop > previousScrollTop && this.reserveHeight === 0
      && this.gapBelow(element) <= this.END_REACHED && this.readerIsScrolling()) {
      // The reader went down to the end of the thread: the view stays there as the thread grows
      this.stick = true;
    }
    this.updateScrollButton(element);

    // Use the component's 'hasReachedEnd' property here
    if (element.scrollTop < 100 && !this.isLoadingMessages && this.currentMessages.length > 0 && !this.hasReachedEnd) {
      this.loadOlderMessages();
    }
  }

  private async loadOlderMessages(): Promise<void> {
    if (this.isLoadingMessages) return;

    // Debounce rapid requests
    const now = Date.now();
    if (now - this.lastLoadTime < this.LOAD_DEBOUNCE_MS) {
      return;
    }
    this.lastLoadTime = now;

    const conversationId = this.chatState.getActiveConversationId();
    if (!conversationId || conversationId === '0') return;

    this.isLoadingMessages = true;
    this.isLoadingOlderMessages = true;

    try {
      // The oldest message the server stored (the ones only this browser has sort last)
      const oldestMessage = this.currentMessages[0];
      if (!oldestMessage || oldestMessage.isLocal) return;

      // Store scroll position before loading
      const scrollContainer = this.messageContainer.nativeElement;
      const scrollHeightBefore = scrollContainer.scrollHeight;
      const scrollTopBefore = scrollContainer.scrollTop;

      // Load older messages
      const newMessages = await this.chatState.loadOlderMessages(oldestMessage.id, 20);

      // If no new messages were loaded, we've reached the beginning
      if (newMessages.length === 0) {
        return;
      }

      // Use requestAnimationFrame for smoother scroll restoration
      requestAnimationFrame(() => {
        const scrollHeightAfter = scrollContainer.scrollHeight;
        const scrollDiff = scrollHeightAfter - scrollHeightBefore;

        // Restore scroll position by adding the height difference
        scrollContainer.scrollTop = scrollTopBefore + scrollDiff;
        this.lastScrollTop = scrollContainer.scrollTop;

        // Allow new scroll events after a short delay
        setTimeout(() => {
          this.isRestoringScroll = false;
        }, 100);
      });

      // Prevent scroll events during restoration
      this.isRestoringScroll = true;
    } catch (error) {
      console.error('Error loading older messages:', error);
    } finally {
      this.isLoadingMessages = false;
      this.isLoadingOlderMessages = false;
    }
  }

  ngOnDestroy() {
    this.destroy$.unsubscribe();

    // Add this block to unsubscribe from theme changes
    if (this.themeSubscription) {
      this.themeSubscription.unsubscribe();
    }

    if (this.guestLimitSubscription) {
      this.guestLimitSubscription.unsubscribe();
    }
    if (this.guestLimitResetTimeSubscription) {
      this.guestLimitResetTimeSubscription.unsubscribe();
    }

    this.resizeObserver?.disconnect();
    this.removeInputListeners?.();
    if (this.smoothTimer) {
      clearTimeout(this.smoothTimer);
    }
  }

  // ============================================
  // Where the view stands
  // ============================================
  //
  // An answer is read from its first line while it is still being written, so the view never
  // moves under the reader. When the user asks for an answer (a message, Generate, regenerate),
  // their message goes to the top of the view, with a strip of the message before it, and stays
  // there. A reserve under the last message gives the thread the height for that before the
  // answer exists; the answer grows into it. An answer longer than the view grows out of it at
  // the bottom, and the button to the newest message appears.
  //
  // The view only follows the thread's end for a reader who is there: a conversation that opens,
  // or a reader who went to the end themself (the button, or scrolling down to it).

  // How much of the message before a turn stays in view above it
  private readonly TURN_PEEK = 48;
  // A message of the user taller than this share of the view shows only its last lines (a long
  // text is folded after ten lines and fits in it whole, so this is above all one with a photo) ...
  private readonly TALL_QUESTION_SHARE = 0.6;
  // ... this many pixels of them
  private readonly TALL_QUESTION_VISIBLE = 112;
  // How long a turn that was just placed follows its message's changes of height (milliseconds)
  private readonly TURN_SETTLES = 500;
  // The reader counts as at the end of the thread within this distance
  private readonly END_REACHED = 24;
  // The button to the newest message shows once this much of the thread is below the view:
  // while an answer is written, as soon as it grows out of the view
  private readonly BUTTON_SHOWS = 400;
  private readonly BUTTON_SHOWS_STREAMING = 48;

  private currentMessages: Message[] = [];

  // The turn at the top of the view: the user's newest message ('question'), or the answer that
  // continues an answer ('answer'). It keeps its reserve until the next turn
  private turn: 'question' | 'answer' | null = null;
  // Where the view's top edge stood for it when its message was last in the thread
  private keptTurnTop: number | null = null;
  // The user asked for an answer; its turn is not in the thread yet
  private turnRequested = false;
  // The turn is in the thread and goes to the top of the view after the next rendering
  private placePending = false;
  // The view is at the end of the thread and stays there as the thread grows
  private stick = true;
  // The view stands at the turn, where this component put it: the reader hasn't moved it since.
  // It then stays there, also when the turn moves in the thread (standAtTurn())
  private standing = false;
  // Where a smooth scroll of this component is heading (null: none)
  private smoothTarget: number | null = null;
  private smoothTimer: ReturnType<typeof setTimeout> | null = null;
  // Until then a turn that was just placed is placed again when its message changes its height:
  // a message's text is rendered a moment after the message appears
  private settlingUntil = 0;
  // When the reader last used the wheel, a finger, a key or the scrollbar in the thread
  private lastInputAt = 0;
  private lastScrollTop = 0;
  private reserveHeight = 0;
  private resizeObserver?: ResizeObserver;
  private removeInputListeners?: () => void;

  // Loading state for older messages
  isLoadingOlderMessages = false;
  private isLoadingMessages = false;
  private isRestoringScroll = false;
  private lastLoadTime = 0;
  private readonly LOAD_DEBOUNCE_MS = 300;

  /**
   * React when the thread or the view changes its height (an answer grows, an image loads, steps
   * open, the composer grows, the window is resized), and notice the reader's own scrolling.
   */
  private watchThread(): void {
    const scroller = this.messageContainer?.nativeElement;
    const thread = this.messageList?.nativeElement;
    if (!scroller || !thread || typeof ResizeObserver === 'undefined') return;

    this.ngZone.runOutsideAngular(() => {
      this.resizeObserver = new ResizeObserver(() => this.onThreadResized());
      this.resizeObserver.observe(thread);
      this.resizeObserver.observe(scroller);

      // The reader takes over: a smooth scroll of this component no longer counts
      const takeOver = () => {
        this.smoothTarget = null;
        this.settlingUntil = 0;
        this.lastInputAt = performance.now();
        if (this.standing) {
          this.standing = false;
          this.updateAnchoring();
        }
      };
      const events = ['wheel', 'touchstart', 'touchmove', 'keydown', 'pointerdown'];
      events.forEach(name => scroller.addEventListener(name, takeOver, { passive: true }));
      this.removeInputListeners = () => events.forEach(name => scroller.removeEventListener(name, takeOver));
    });
  }

  private onThreadResized(): void {
    const scroller = this.messageContainer?.nativeElement;
    if (!scroller) return;
    // The browser moves the view up when it ends up beyond what can be scrolled: when the view
    // gets taller (the composer shrinks), or the thread shorter (an answer is removed to be
    // written again). The reader's own scrolling has reported itself by now (onScroll)
    const stood = this.lastScrollTop;
    const movedUp = this.smoothTarget === null && !this.isRestoringScroll
      && scroller.scrollTop < stood - 1 && this.gapBelow(scroller) <= 1;
    this.updateReserve(scroller);
    if (movedUp && this.turn) {
      // The reserve has the room again: the view goes back to where it stood
      scroller.scrollTop = stood;
      this.lastScrollTop = scroller.scrollTop;
    }
    if (this.turn && this.standing) {
      if (performance.now() < this.settlingUntil || this.smoothTarget !== null) {
        this.scrollToTurn(scroller);  // On its way there
      } else {
        this.standAtTurn(scroller);
      }
    } else if (this.stick && !this.turnRequested && this.smoothTarget === null) {
      this.scrollToEnd();
    }
    this.updateScrollButton(scroller);
  }

  /**
   * Browsers keep what is in view in place when the thread changes above it, and put a view back
   * that they had to move up (scroll anchoring). That is right for a reader who is somewhere in
   * the thread, and wrong while the view stands at a turn or an answer is written: there the
   * browser then moves the view itself, e.g. to keep a line of the growing answer in place when
   * the steps above it grow, or towards the thread's end when the composer shrinks after a
   * message was sent. So it is off then, and this component alone decides where the view stands.
   */
  private updateAnchoring(): void {
    const scroller = this.messageContainer?.nativeElement;
    if (!scroller) return;
    const anchoring = this.standing || this.turnRequested || this.isStreaming ? 'none' : '';
    if (scroller.style.overflowAnchor !== anchoring) scroller.style.overflowAnchor = anchoring;
  }

  /**
   * Whether a scroll is the reader's: only then does reaching the end mean they want to stay
   * there. The browser moves the view too (when the thread changes above what is in view), and
   * a view that then follows a growing answer is what "Where the view stands" is there to avoid.
   * Long enough for the scrolling that goes on after a swipe.
   */
  private readerIsScrolling(): boolean {
    return performance.now() - this.lastInputAt < 4000;
  }

  /** How far the view is from the end of what can be scrolled (the thread and its reserve). */
  private gapBelow(scroller: HTMLElement): number {
    return scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
  }

  /** Whether the end of the thread is in view (or nearly). */
  private endIsInView(): boolean {
    const scroller = this.messageContainer?.nativeElement;
    return !scroller || this.gapBelow(scroller) - this.reserveHeight <= this.END_REACHED;
  }

  /** The messages in the thread, in order; the answer being written is the last one. */
  private messageElementsInThread(): HTMLElement[] {
    const thread = this.messageList?.nativeElement;
    return thread ? Array.from(thread.querySelectorAll<HTMLElement>(':scope > app-chat-ui-message')) : [];
  }

  /**
   * The message of the turn at the top of the view: the user's newest message, or the answer
   * that continues an answer (the one being written, later the newest one).
   */
  private turnElement(): HTMLElement | null {
    const elements = this.messageElementsInThread();
    if (this.turn === 'question') {
      return elements.filter(element => element.dataset['role'] === 'user').pop() ?? null;
    }
    if (this.turn === 'answer') {
      const inProgress = elements.find(element => element.classList.contains('streaming-message'));
      if (inProgress) return inProgress;
      // While it is asked for again (regenerate), it is in the thread no longer and not yet
      return this.turnRequested ? null : elements.filter(element => element.dataset['role'] === 'answer').pop() ?? null;
    }
    return null;
  }

  /** Where the view's top edge stands for the turn (a scroll position); null without a turn. */
  private currentTurnTop(scroller: HTMLElement): number | null {
    if (!this.turn) return null;
    const element = this.turnElement();
    if (element) {
      this.keptTurnTop = this.turnTop(scroller, element);
      return this.keptTurnTop;
    }
    // An answer that is written again starts where it started before
    if (this.turnRequested && this.keptTurnTop !== null) return this.keptTurnTop;
    this.turn = null;  // Its message is gone
    this.keptTurnTop = null;
    return null;
  }

  /** Where the view's top edge stands for a turn that starts with this message (a scroll position). */
  private turnTop(scroller: HTMLElement, element: HTMLElement): number {
    const box = (element.querySelector('.message-row') ?? element).getBoundingClientRect();
    const top = box.top - scroller.getBoundingClientRect().top - scroller.clientTop + scroller.scrollTop;
    if (this.turn === 'question' && box.height > scroller.clientHeight * this.TALL_QUESTION_SHARE) {
      // A long message of the user: its last lines stay in view, the answer gets the room
      return Math.max(0, Math.round(top + box.height - this.TALL_QUESTION_VISIBLE));
    }
    return Math.max(0, Math.round(top - this.TURN_PEEK));
  }

  /**
   * Give the thread the height that lets the turn stand at the top of the view: what is missing
   * under its last message. The reserve shrinks as the answer grows, so nothing moves.
   */
  private updateReserve(scroller: HTMLElement): void {
    const reserve = this.turnReserve?.nativeElement;
    if (!reserve) return;
    const top = this.currentTurnTop(scroller);
    let height = 0;
    if (top !== null) {
      // Where the thread ends (the reserve starts there), as a scroll position
      const end = reserve.getBoundingClientRect().top - scroller.getBoundingClientRect().top
        - scroller.clientTop + scroller.scrollTop;
      const paddingBottom = parseFloat(getComputedStyle(scroller).paddingBottom) || 0;
      // Rounded up, so that the view can stand exactly there; but down for a thread that fits
      // the view, where a pixel too much would show a scrollbar
      const missing = top + scroller.clientHeight - end - paddingBottom;
      height = Math.max(0, top > 0 ? Math.ceil(missing) : Math.floor(missing));
    }
    if (height !== this.reserveHeight) {
      this.reserveHeight = height;
      reserve.style.height = `${height}px`;
    }
  }

  /**
   * Put the turn that is being answered at the top of the view.
   * @returns false while its message is not in the thread yet
   */
  private placeTurn(): boolean {
    const scroller = this.messageContainer?.nativeElement;
    if (!scroller) return false;

    const elements = this.messageElementsInThread();
    const answerInProgress = elements.find(element => element.classList.contains('streaming-message'));
    // Not before the thread shows the messages as they are now: an answer that is written again
    // (a new version, docs/answer_versions.md) can still stand in it in the first check, and
    // would make the turn an answer that goes on
    if (elements.length - (answerInProgress ? 1 : 0) !== this.currentMessages.length) return false;
    const newest = elements
      .filter(element => element !== answerInProgress && element.dataset['role'] !== 'system').pop();
    if (newest?.dataset['role'] === 'user') {
      this.turn = 'question';
    } else if (answerInProgress) {
      this.turn = 'answer';  // It continues an answer
    } else {
      return false;
    }

    if (!this.turnElement()) return false;
    this.stick = false;
    this.standing = true;
    this.updateAnchoring();
    this.settlingUntil = performance.now() + this.TURN_SETTLES;
    this.updateReserve(scroller);
    this.scrollToTurn(scroller);
    // Not in this rendering, which has checked the button already
    queueMicrotask(() => this.updateScrollButton(scroller));
    return true;
  }

  /**
   * Keep the view standing at the turn when the turn moved in the thread, because something
   * above it changed its height (in manual editing the system prompt, the thread's first
   * message, is loaded again for every answer): at once, so that what is read stays in place.
   */
  private standAtTurn(scroller: HTMLElement): void {
    const top = this.currentTurnTop(scroller);
    if (top !== null && Math.abs(scroller.scrollTop - top) >= 1) {
      scroller.scrollTop = top;
      this.lastScrollTop = scroller.scrollTop;
    }
  }

  /** Move the view to where the turn stands at its top, unless it is there or on its way. */
  private scrollToTurn(scroller: HTMLElement): void {
    const top = this.currentTurnTop(scroller);
    if (top === null) return;
    const heading = this.smoothTarget ?? scroller.scrollTop;
    if (Math.abs(heading - top) >= 2) {
      this.scrollSmoothly(scroller, top);
    }
  }

  private scrollSmoothly(scroller: HTMLElement, top: number): void {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      this.smoothTarget = null;
      scroller.scrollTop = top;
      this.lastScrollTop = scroller.scrollTop;
      return;
    }
    this.smoothTarget = top;
    if (this.smoothTimer) clearTimeout(this.smoothTimer);
    // If the view never gets there (the reader interrupts it, the thread changes)
    this.smoothTimer = setTimeout(() => this.arrived(scroller), 1200);
    scroller.scrollTo({ top, behavior: 'smooth' });
  }

  /** A smooth scroll of this component is over. */
  private arrived(scroller: HTMLElement): void {
    this.smoothTarget = null;
    if (this.smoothTimer) {
      clearTimeout(this.smoothTimer);
      this.smoothTimer = null;
    }
    // The thread may have grown on the way to its end
    if (this.stick) this.scrollToEnd();
    this.updateScrollButton(scroller);
  }

  // The button: go to the newest message and stay with the thread as it grows
  jumpToBottom(): void {
    const scroller = this.messageContainer?.nativeElement;
    if (!scroller) return;
    this.stick = true;
    this.standing = false;
    this.showScrollToBottom = false;
    this.updateAnchoring();
    this.scrollSmoothly(scroller, scroller.scrollHeight - scroller.clientHeight);
  }

  /** Jump to the end of the thread. */
  private scrollToEnd(): void {
    const scroller = this.messageContainer?.nativeElement;
    if (!scroller) return;
    scroller.scrollTop = scroller.scrollHeight;
    this.lastScrollTop = scroller.scrollTop;
  }

  /**
   * Show the button to the newest message when the thread goes on below the view, and hide it
   * once the reader is back at its end.
   */
  private updateScrollButton(scroller: HTMLElement): void {
    const below = this.gapBelow(scroller) - this.reserveHeight;
    let show = this.showScrollToBottom;
    if (this.stick || below <= this.END_REACHED) {
      show = false;
    } else if (below > (this.isStreaming ? this.BUTTON_SHOWS_STREAMING : this.BUTTON_SHOWS)) {
      show = true;
    }
    if (show !== this.showScrollToBottom) {
      // The thread's resizes are watched outside of Angular
      this.ngZone.run(() => {
        this.showScrollToBottom = show;
        this.cdr.markForCheck();
      });
    }
  }

  /**
   * The user asks for an answer: its turn goes to the top of the view once its message is in
   * the thread (see the subscriptions in ngOnInit), and the view doesn't follow the thread's
   * end in the meantime.
   */
  private async withTurn<T>(request: () => Promise<T>): Promise<T> {
    this.turnRequested = true;
    // The turn before no longer holds the view; the new one will, once it is placed
    this.standing = false;
    // Before the thread changes: the browser must not move the view on its own from here on
    this.updateAnchoring();
    try {
      return await request();
    } finally {
      // Nothing answers (the message was not sent, or the request failed)
      if (!this.isStreaming) {
        this.turnRequested = false;
        this.updateAnchoring();
      }
    }
  }

  /**
   * Handle agent steps panel expansion - no aggressive scrolling
   * Let the user control their scroll position when viewing agent steps
   */
  onAgentStepsExpanded(event: { expanded: boolean; messageElement: HTMLElement }): void {
    // Don't auto-scroll when expanding/collapsing agent steps
    // The user opened the panel to read it where they are, not to be pulled to the bottom
    // This is intentionally a no-op now
  }

  // After every rendering: a turn whose message is now in the thread goes to the top of the view
  ngAfterViewChecked() {
    if (this.placePending && this.placeTurn()) {
      this.placePending = false;
    }
  }

  // Utility function to detect mobile devices - now uses UIStateService
  isMobileDevice(): boolean {
    return this.uiState.isMobile;
  }

  // Handle message sent from the input component
  async onMessageSent(message: string): Promise<void> {
    if (message.trim() || this.pendingFiles.length > 0) {
      try {
        // The message goes to the top of the view, its answer is written below it
        await this.withTurn(async () => {
          if (this.pendingFiles.length > 0) {
            console.log('Sending message with files:', this.pendingFiles);
            await this.chatState.sendMessageWithFiles(message, this.pendingFiles);
            this.pendingFiles = []; // Clear pending files after sending
          } else {
            console.log('Sending message:', message);
            await this.chatState.sendMessage(message);
          }
        });

        console.log('User message sent:', message);
      } catch (error) {
        console.error('Error sending message:', error);
      }
    }
  }

  // Cancel ongoing streaming
  cancelStreaming(): void {
    this.chatState.cancelStreaming();
  }

  // Generate in the composer (manual editing): answer the conversation as it stands
  async generateAnswer(): Promise<void> {
    // The message it answers goes to the top of the view; after an answer, the new answer does
    try {
      await this.withTurn(() => this.chatState.answerLatestMessage());
    } catch (error) {
      console.error('Error generating AI response:', error);
    }
  }

  // Handle audio recording request
  onAudioRequested(): void {
    console.log('Audio recording requested');
  }

  // Handle file attachment request (including voice messages)
  async onFileRequested(filePreviews: FilePreview[]): Promise<void> {
    // Check if this is a voice message (single audio file with "Voice message" name)
    const isVoiceMessageBatch = filePreviews.length === 1 &&
      filePreviews[0].mimeType.startsWith('audio/') &&
      filePreviews[0].name.includes('Voice message');

    if (isVoiceMessageBatch) {
      const voiceFile = filePreviews[0];

      // Skip if already marked as sent (prevent double-send)
      if ((voiceFile as any).isSent) {
        return;
      }
      (voiceFile as any).isSent = true;

      try {
        await this.withTurn(async () => {
          // If still uploading, wait for transcript before sending to AI
          if (voiceFile.uploadStatus === 'uploading') {
            // Show message immediately with placeholder, then wait for transcript
            await this.handleVoiceMessageWithPendingTranscript(voiceFile);
          } else {
            // Transcript already available (or upload failed)
            const transcript = voiceFile.transcript || 'Voice message';
            await this.chatState.sendMessageWithFiles(transcript, [voiceFile]);
          }
        });
      } catch (error) {
        console.error('Error sending voice message:', error);
        // Un-mark if sending failed, so it can be retried.
        delete (voiceFile as any).isSent;
      }
    } else {
      // Regular file attachments - add to pending files for manual send
      this.pendingFiles = filePreviews;
    }
  }

  // Handle voice message when transcript is still pending (upload in progress)
  private async handleVoiceMessageWithPendingTranscript(voiceFile: FilePreview): Promise<void> {
    // Show message immediately with "Transcribing..." placeholder
    const placeholderText = '🎤 Transcribing voice message...';

    // Create and display message locally first (don't sync to backend yet)
    await this.chatState.addLocalVoiceMessage(placeholderText, voiceFile);

    // Wait for upload to complete (poll for transcript)
    const transcript = await this.waitForTranscript(voiceFile, 30000); // 30 second timeout

    // Update message with real transcript and trigger AI response
    await this.chatState.updateVoiceMessageAndRespond(voiceFile, transcript);
  }

  // Wait for transcript to become available
  private waitForTranscript(voiceFile: FilePreview, timeoutMs: number): Promise<string> {
    return new Promise((resolve) => {
      const startTime = Date.now();
      const checkInterval = 200; // Check every 200ms

      const check = () => {
        // Check if transcript is ready
        if (voiceFile.transcript) {
          resolve(voiceFile.transcript);
          return;
        }

        // Check if upload failed
        if (voiceFile.uploadStatus === 'failed') {
          resolve('Voice message (transcription failed)');
          return;
        }

        // Check timeout
        if (Date.now() - startTime > timeoutMs) {
          resolve('Voice message');
          return;
        }

        // Keep checking
        setTimeout(check, checkInterval);
      };

      check();
    });
  }

  // SIMPLIFIED: Camera is now handled by the input component directly
  onCameraRequested(): void {
    console.log('Camera requested - handled by input component');
  }

  onLocationRequested(): void {
    console.log('Location sharing requested');
  }

  // Method to delete a message
  deleteMessage(messageId: number) {
    this.chatState.deleteMessage(messageId);
  }

  // Show another version of an answer, or delete the one shown (docs/answer_versions.md)
  switchAlternative(message: Message, position: number): Promise<void> {
    return this.chatState.switchAlternative(message, position);
  }

  deleteAlternative(message: Message): Promise<void> {
    return this.chatState.deleteAlternative(message);
  }

  // Method to change a message's text
  patchMessage(messageId: number, content: string): Promise<void> {
    return this.chatState.patchMessage(messageId, content);
  }

  // Save an edited message of the user and answer it again (guided editing)
  resendEditedMessage(messageId: number, content: string): Promise<void> {
    return this.withTurn(() => this.chatState.resendEditedMessage(messageId, content));
  }

  // Insert a message next to another one (manual editing)
  insertMessage(
    next: Message, position: 'before' | 'after', roleName: 'user' | 'Assistant' | 'system', content: string
  ): Promise<void> {
    return this.chatState.insertMessage(next, position, roleName, content);
  }

  // How many messages come after this one (an edit in guided mode deletes them)
  countMessagesAfter(message: Message): number {
    return this.currentMessages.filter(m => Message.compare(m, message) > 0).length;
  }

  get isStreaming(): boolean {
    return this.chatState.isCurrentlyStreaming();
  }

  // Send a message again that the server didn't take
  resendMessage(messageId: number): Promise<void> {
    return this.withTurn(() => this.chatState.resendMessage(messageId));
  }

  // Method to regenerate a message (optionally once with another catalog model)
  regenerateMessage(message: Message, modelId?: number) {
    // The chat state reports a failure itself
    this.withTurn(() => this.chatState.regenerateMessage(message, modelId)).catch(() => undefined);
  }

  // Method to rate a message
  rateMessage(message: Message, rating: number | null) {
    try {
      this.chatState.rateMessage(message, rating);
    } catch (error) {
      console.error('Failed to rate message:', error);
    }
  }

  // Check if a message is the last AI message in the conversation (system messages are no answers)
  isLastAiMessage(message: Message, index: number): boolean {
    if (message.roleName === 'user' || message.roleName === 'system') {
      return false;
    }

    const messages = this.currentMessages;
    if (!messages || messages.length === 0) {
      return false;
    }

    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].roleName !== 'user' && messages[i].roleName !== 'system') {
        return messages[i].id === message.id;
      }
    }

    return false;
  }
}
