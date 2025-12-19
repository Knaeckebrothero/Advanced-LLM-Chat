import { Component, ViewChild, ElementRef, AfterViewChecked, AfterViewInit, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
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

  // Variables
  userName: string = 'user';
  aiName: string = 'Assistant';
  pendingFiles: FilePreview[] = [];
  isDarkMode: boolean = false; // Add this property

  // The inputField property is bound to the input field in the template.
  inputField: string = '';

  // Observable state from ChatStateService
  messages$: Observable<Message[]> = this.chatState.messages$;
  isLoading$: Observable<boolean> = this.chatState.state$.pipe(map(state => state.isLoading));
  error$: Observable<string | null> = this.chatState.state$.pipe(map(state => state.error));
  hasReachedEnd$: Observable<boolean> = this.chatState.state$.pipe(map(state => state.hasReachedEnd || false));

  // Streaming state
  streamingMessage$: Observable<Message<AgentContent> | null> = this.chatState.state$.pipe(
    map(state => state.streamingMessage)
  );
  isStreaming$: Observable<boolean> = this.chatState.state$.pipe(map(state => state.isStreaming));

  // For template compatibility - expose messages as non-observable
  messages = this.chatState.messages$;

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
          // Get current streaming content length
          const currentContent = streamingMsg.content?.finalResponse || '';

          // Only scroll if content has grown (throttle scrolls)
          if (currentContent.length > this.lastStreamingContent.length + 50) {
            this.lastStreamingContent = currentContent;
            // Use requestAnimationFrame for smooth scrolling
            requestAnimationFrame(() => this.scrollToBottom());
          }
        } else if (!streamingMsg) {
          // Reset when streaming ends
          this.lastStreamingContent = '';
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
    }

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
  }

  // Method to scroll to the bottom of the chat window.
  private scrollToBottom(): void {
    try {
      this.messageContainer.nativeElement.scrollTop = this.messageContainer.nativeElement.scrollHeight;
    } catch (err) { }
  }

  // Track if we should auto-scroll
  private shouldScrollToBottom = true;
  private lastMessageCount = 0;
  private currentMessages: Message[] = [];
  private wasNearBottom = true; // Track scroll position before updates
  private userIsAtBottom = true; // Track if user is intentionally at bottom
  private lastStreamingContent = ''; // Track streaming content for scroll triggers

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
    const threshold = 150; // Slightly larger threshold for better UX
    return element.scrollHeight - element.scrollTop - element.clientHeight < threshold;
  }

  // Use the AfterViewChecked lifecycle hook to trigger the scroll method.
  ngAfterViewChecked() {
    // Check if we're at a different message count
    const currentMessageCount = this.currentMessages.length;

    if (currentMessageCount !== this.lastMessageCount) {
      // Messages changed, check if we should scroll
      this.lastMessageCount = currentMessageCount;

      // Only auto-scroll if user is at bottom OR we should force scroll
      if (this.userIsAtBottom || this.shouldScrollToBottom) {
        this.scrollToBottom();
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
        this.shouldScrollToBottom = true;
        this.wasNearBottom = true; // Force scroll for user's own messages

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
      // Voice messages are pre-uploaded by inputfield component
      // They come in their own batch and should be sent immediately
      const voiceFile = filePreviews[0];

      // Skip if already marked as sent (prevent double-send)
      if ((voiceFile as any).isSent) {
        return;
      }
      (voiceFile as any).isSent = true;

      try {
        // Get transcript - should already be set from upload
        const transcript = voiceFile.transcript || 'Voice message';

        // Send as a text message with the audio file as attachment
        await this.chatState.sendMessageWithFiles(transcript, [voiceFile]);

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
