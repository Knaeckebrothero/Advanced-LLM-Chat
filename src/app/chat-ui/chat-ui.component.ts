import { Component, ViewChild, ViewChildren, ElementRef, QueryList, AfterViewChecked, AfterViewInit, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { Message, AgentContent } from '../data/objects/message';
import { AuthService } from '../auth/auth.service';
import { Subscription, Observable, combineLatest } from 'rxjs';
import { map, filter } from 'rxjs/operators';
import { FilePreview, FilePreviewUtil } from '../data/objects/file-preview';
import { RecordingResult } from '../data/objects/recording';
import { ChatStateService } from '../services/chat-state.service';
import { UIStateService } from '../services/ui-state.service';
import { ThemeService } from '../services/theme.service';
import { ChatUiInputfieldComponent } from './chat-ui-inputfield/chat-ui-inputfield.component';
import { ChatUiMessageComponent } from './chat-ui-message/chat-ui-message.component';


@Component({
  selector: 'app-chat-ui',
  templateUrl: './chat-ui.component.html',
  styleUrls: ['./chat-ui.component.scss'],
  standalone: false
})
export class ChatUiComponent implements AfterViewChecked, AfterViewInit, OnInit, OnDestroy {

  // The messageContainer property is bound to the message container in the template.
  @ViewChild('messageContainer') private messageContainer!: ElementRef;

  // Reference to the chat input field component for programmatic focus
  @ViewChild(ChatUiInputfieldComponent) private chatInputField!: ChatUiInputfieldComponent;

  // Track message elements for anchor-based scrolling
  @ViewChildren(ChatUiMessageComponent, { read: ElementRef }) private messageElements!: QueryList<ElementRef>;

  // Variables
  userName: string = 'user';
  aiName: string = 'Assistant';
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
    private cdr: ChangeDetectorRef
  ) { }

  ngOnInit() {
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

        // When switching conversations or loading initial messages, scroll to bottom
        if (previousLength === 0 && this.currentMessages.length > 0) {
          this.shouldScrollToBottom = true;
          this.userIsAtBottom = true;
          // Use setTimeout to ensure DOM has updated
          setTimeout(() => this.scrollToBottom(), 100);
        }
      })
    );

    // Subscribe to active conversation changes
    this.destroy$.add(
      this.chatState.activeConversation$.subscribe(() => {
        // Reset scroll state when conversation changes
        this.shouldScrollToBottom = true;
        this.userIsAtBottom = true;
      })
    );

    // Subscribe to streaming message for auto-scroll during response generation
    this.destroy$.add(
      this.streamingMessage$.subscribe(streamingMsg => {
        if (streamingMsg && this.userIsAtBottom) {
          // Get current streaming content length (includes both steps and response)
          const currentContent = streamingMsg.content?.content || '';
          const stepsCount = streamingMsg.content?.steps?.length || 0;
          const contentLength = currentContent.length + (stepsCount * 100); // Approximate step contribution

          // Only scroll if content has grown (throttle scrolls)
          if (contentLength > this.lastStreamingContent.length + 50) {
            this.lastStreamingContent = String(contentLength);
            // Use requestAnimationFrame for smooth scrolling with smart positioning
            requestAnimationFrame(() => {
              // Use debounced scroll on mobile for better performance
              if (this.uiState.isMobile) {
                this.debouncedSmartScroll();
              } else {
                this.smartScroll();
              }
            });
          }
        } else if (!streamingMsg) {
          // Reset when streaming ends
          this.lastStreamingContent = '';
          this.useAnchorMode = false;
          this.anchorMessageIndex = null;

          // If user scrolled up during streaming, respect their intent
          // Don't yank them back down to the bottom
          if (this.userScrolledDuringStreaming) {
            this.shouldScrollToBottom = false;
            this.userIsAtBottom = false;
            this.userScrolledDuringStreaming = false; // Reset for next streaming session
          } else {
            // User stayed at bottom during streaming, keep auto-scroll enabled
            const isAtBottom = this.isNearBottom();
            this.shouldScrollToBottom = isAtBottom;
            this.userIsAtBottom = isAtBottom;
          }
        }
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
  }

  // Handle scroll events to load older messages and track user scroll intent
  onScroll(event: Event): void {
    if (this.isRestoringScroll) return;

    const element = event.target as HTMLElement;
    const currentScrollTop = element.scrollTop;

    // Detect scroll direction - if user scrolled UP, disable auto-scroll immediately
    // This makes it easy to "break free" from auto-scroll during streaming
    if (!this.isProgrammaticScroll && currentScrollTop < this.lastScrollTop - 5) {
      // User scrolled up by more than 5px - disable auto-scroll
      this.userIsAtBottom = false;
      this.shouldScrollToBottom = false;

      // Track that user scrolled during streaming (to prevent pull-down when streaming ends)
      if (this.lastStreamingContent) {
        this.userScrolledDuringStreaming = true;
      }
    } else {
      // Track if user manually scrolled away from bottom
      const wasAtBottom = this.userIsAtBottom;
      this.userIsAtBottom = this.isNearBottom();

      // If user scrolled up from bottom, they want to read history - disable auto-scroll
      if (wasAtBottom && !this.userIsAtBottom) {
        this.shouldScrollToBottom = false;
      }

      // If user scrolled back to bottom, re-enable auto-scroll
      if (!wasAtBottom && this.userIsAtBottom) {
        this.shouldScrollToBottom = true;
        // Reset the streaming scroll flag - user is back at bottom
        this.userScrolledDuringStreaming = false;
      }
    }

    // Update last scroll position for next comparison
    this.lastScrollTop = currentScrollTop;

    // Reset programmatic scroll flag
    this.isProgrammaticScroll = false;

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
      const oldestMessage = this.currentMessages[0];
      if (!oldestMessage) return;

      // Store scroll position before loading
      const scrollContainer = this.messageContainer.nativeElement;
      const scrollHeightBefore = scrollContainer.scrollHeight;
      const scrollTopBefore = scrollContainer.scrollTop;

      // Load older messages
      const newMessages = await this.chatState.loadOlderMessages(oldestMessage.time, 20);

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

    // Clean up scroll debounce timer
    if (this.scrollDebounceTimer) {
      clearTimeout(this.scrollDebounceTimer);
    }
  }

  // Method to scroll to the bottom of the chat window.
  private scrollToBottom(): void {
    try {
      this.isProgrammaticScroll = true;
      this.messageContainer.nativeElement.scrollTop = this.messageContainer.nativeElement.scrollHeight;
      this.lastScrollTop = this.messageContainer.nativeElement.scrollTop;
    } catch (err) { }
  }

  // Track if we should auto-scroll
  private shouldScrollToBottom = true;
  private lastMessageCount = 0;
  private currentMessages: Message[] = [];
  private wasNearBottom = true; // Track scroll position before updates
  private userIsAtBottom = true; // Track if user is intentionally at bottom
  private lastStreamingContent = ''; // Track streaming content for scroll triggers

  // Anchor-based scrolling state (Claude/ChatGPT style)
  private useAnchorMode = false; // When true, anchor user message at top
  private anchorMessageIndex: number | null = null; // Index of message to anchor at top
  private scrollDebounceTimer: any = null; // Debounce timer for mobile
  private lastScrollTop = 0; // Track scroll position for direction detection
  private isProgrammaticScroll = false; // Flag to ignore programmatic scroll events
  private userScrolledDuringStreaming = false; // Track if user scrolled up during streaming

  // Loading state for older messages
  isLoadingOlderMessages = false;
  private isLoadingMessages = false;
  private isRestoringScroll = false;
  private lastLoadTime = 0;
  private readonly LOAD_DEBOUNCE_MS = 300;

  // Check if user is near bottom of chat (within threshold)
  private isNearBottom(): boolean {
    if (!this.messageContainer) return true;
    const element = this.messageContainer.nativeElement;
    // Larger threshold on mobile to account for touch momentum
    const threshold = this.uiState.isMobile ? 200 : 150;
    return element.scrollHeight - element.scrollTop - element.clientHeight < threshold;
  }

  // ============================================
  // Anchor-based scrolling (Claude/ChatGPT style)
  // ============================================

  /**
   * Scroll to position a specific message at the top of the viewport
   */
  private scrollToMessageAtTop(messageIndex: number, padding: number = 16): void {
    const elements = this.messageElements?.toArray();
    if (!elements || messageIndex < 0 || messageIndex >= elements.length) return;

    const messageEl = elements[messageIndex].nativeElement;
    const container = this.messageContainer.nativeElement;

    // Calculate scroll position to place message at top with padding
    const messageTop = messageEl.offsetTop;
    this.isProgrammaticScroll = true;
    container.scrollTop = Math.max(0, messageTop - padding);
    this.lastScrollTop = container.scrollTop;
  }

  /**
   * Check if the last message (AI response) extends below the visible viewport
   */
  private isContentBelowViewport(): boolean {
    const container = this.messageContainer?.nativeElement;
    if (!container) return false;

    const elements = this.messageElements?.toArray();
    if (!elements || elements.length === 0) return false;

    const containerRect = container.getBoundingClientRect();
    const lastMessage = elements[elements.length - 1].nativeElement;
    const lastMessageRect = lastMessage.getBoundingClientRect();

    // Use visualViewport for accurate visible area on mobile (handles virtual keyboard)
    const visibleBottom = (window as any).visualViewport
      ? (window as any).visualViewport.height + (window as any).visualViewport.offsetTop
      : containerRect.bottom;

    // Content is below viewport if the bottom of last message exceeds visible area
    return lastMessageRect.bottom > visibleBottom;
  }

  /**
   * Smart scroll that chooses between anchor mode and follow mode
   * - Anchor mode: Keep user message at top of viewport
   * - Follow mode: Keep bottom of content visible (traditional auto-scroll)
   */
  private smartScroll(): void {
    if (!this.userIsAtBottom) return; // Respect user scroll intent

    if (this.useAnchorMode && this.anchorMessageIndex !== null) {
      // Check if content has grown beyond viewport
      if (this.isContentBelowViewport()) {
        // Phase 2: Content fills viewport, switch to follow mode
        this.scrollToBottom();
      } else {
        // Phase 1: Keep anchor (user message) at top
        this.scrollToMessageAtTop(this.anchorMessageIndex);
      }
    } else {
      // No anchor mode, use traditional scroll to bottom
      this.scrollToBottom();
    }
  }

  /**
   * Debounced smart scroll for mobile (prevents jank during rapid updates)
   */
  private debouncedSmartScroll(): void {
    if (this.scrollDebounceTimer) {
      clearTimeout(this.scrollDebounceTimer);
    }
    this.scrollDebounceTimer = setTimeout(() => {
      this.smartScroll();
      this.scrollDebounceTimer = null;
    }, 50);
  }

  /**
   * Find and set the anchor to the last user message
   */
  private updateAnchorIndex(): void {
    if (!this.useAnchorMode) return;

    // Find the last user message index
    for (let i = this.currentMessages.length - 1; i >= 0; i--) {
      if (this.currentMessages[i].roleName === 'user') {
        this.anchorMessageIndex = i;
        return;
      }
    }
    this.anchorMessageIndex = null;
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

  // Use the AfterViewChecked lifecycle hook to trigger the scroll method.
  ngAfterViewChecked() {
    // Check if we're at a different message count
    const currentMessageCount = this.currentMessages.length;

    if (currentMessageCount !== this.lastMessageCount) {
      // Messages changed, check if we should scroll
      this.lastMessageCount = currentMessageCount;

      // Update anchor index if in anchor mode
      this.updateAnchorIndex();

      // Only auto-scroll if user is at bottom OR we should force scroll
      if (this.userIsAtBottom || this.shouldScrollToBottom) {
        // Use smart scroll for anchor-based positioning
        this.smartScroll();
        this.shouldScrollToBottom = false; // Reset flag after scrolling
      }
    }

    // Always update the wasNearBottom status for next check
    this.wasNearBottom = this.isNearBottom();
  }

  // Utility function to detect mobile devices - now uses UIStateService
  isMobileDevice(): boolean {
    return this.uiState.isMobile;
  }

  // Handle message sent from the input component
  async onMessageSent(message: string): Promise<void> {
    if (message.trim() || this.pendingFiles.length > 0) {
      try {
        if (this.pendingFiles.length > 0) {
          console.log('Sending message with files:', this.pendingFiles);
          await this.chatState.sendMessageWithFiles(message, this.pendingFiles);
          this.pendingFiles = []; // Clear pending files after sending
        } else {
          console.log('Sending message:', message);
          await this.chatState.sendMessage(message);
        }

        console.log('User message sent:', message);

        // Enable anchor mode for Claude/ChatGPT style scrolling
        // User message will be anchored at top, AI response grows below
        this.useAnchorMode = true;
        this.userIsAtBottom = true;
        this.shouldScrollToBottom = true;
        this.userScrolledDuringStreaming = false; // Reset for new streaming session

      } catch (error) {
        console.error('Error sending message:', error);
      }
    }
  }

  // Cancel ongoing streaming
  cancelStreaming(): void {
    this.chatState.cancelStreaming();
  }

  // Generate a new message
  async generateMessage(): Promise<void> {
    try {
      await this.chatState.generateMessage(this.aiName);
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
        // If still uploading, wait for transcript before sending to AI
        if (voiceFile.uploadStatus === 'uploading') {
          // Show message immediately with placeholder, then wait for transcript
          await this.handleVoiceMessageWithPendingTranscript(voiceFile);
        } else {
          // Transcript already available (or upload failed)
          const transcript = voiceFile.transcript || 'Voice message';
          await this.chatState.sendMessageWithFiles(transcript, [voiceFile]);
        }

        this.shouldScrollToBottom = true;
        this.wasNearBottom = true;
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

  // Method to change a message
  patchMessage(messageId: number, content: string) {
    this.chatState.patchMessage(messageId, content);
  }

  // Method to regenerate a message
  regenerateMessage(message: Message) {
    // Disable anchor mode for regeneration - just follow the bottom
    // (unlike new messages, we don't want the user message at top with whitespace)
    this.useAnchorMode = false;
    this.anchorMessageIndex = null;

    // Enable auto-scroll to follow the regenerating message
    this.userIsAtBottom = true;
    this.shouldScrollToBottom = true;

    this.chatState.regenerateMessage(message);
  }

  // Method to rate a message
  rateMessage(message: Message, rating: number | null) {
    try {
      this.chatState.rateMessage(message, rating);
    } catch (error) {
      console.error('Failed to rate message:', error);
    }
  }

  // Check if a message is the last AI message in the conversation
  isLastAiMessage(message: Message, index: number): boolean {
    if (message.roleName === 'user') {
      return false;
    }

    const messages = this.currentMessages;
    if (!messages || messages.length === 0) {
      return false;
    }

    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].roleName !== 'user') {
        return messages[i].id === message.id;
      }
    }

    return false;
  }
}
