import { Component, ViewChild, ElementRef, AfterViewChecked, OnInit, OnDestroy } from '@angular/core';
import { Message } from '../data/objects/message';
import { AuthService } from '../auth/auth.service';
import { Subscription, Observable, combineLatest } from 'rxjs';
import { map } from 'rxjs/operators';
import { FilePreview, FilePreviewUtil } from '../data/objects/file-preview';
import { RecordingResult } from '../data/objects/recording';
import { ChatStateService } from '../services/chat-state.service';
import { UIStateService } from '../services/ui-state.service';


@Component({
  selector: 'app-chat-ui',
  templateUrl: './chat-ui.component.html',
  styleUrls: ['./chat-ui.component.scss'],
  standalone: false
})
export class ChatUiComponent implements AfterViewChecked, OnInit, OnDestroy {

  // The messageContainer property is bound to the message container in the template.
  @ViewChild('messageContainer') private messageContainer!: ElementRef;

  // Variables
  userName: string = 'user';
  aiName: string = 'Assistant';
  pendingFiles: FilePreview[] = [];

  // The inputField property is bound to the input field in the template.
  inputField: string = '';

  // Observable state from ChatStateService
  messages$: Observable<Message[]> = this.chatState.messages$;
  isLoading$: Observable<boolean> = this.chatState.state$.pipe(map(state => state.isLoading));
  error$: Observable<string | null> = this.chatState.state$.pipe(map(state => state.error));
  
  // For template compatibility - expose messages as non-observable
  messages = this.chatState.messages$;
  
  // Mobile state from UIStateService
  isMobile$ = this.uiState.isMobile$;
  
  showGuestLimitWarning = false;
  guestLimitWarningMessage: string | null = null;
  private guestLimitSubscription!: Subscription;
  private guestLimitResetTimeSubscription!: Subscription;
  private destroy$ = new Subscription();

  // Constructor - now using state services
  constructor(
    private chatState: ChatStateService,
    private uiState: UIStateService,
    private authService: AuthService
  ) {}

  ngOnInit() {
    this.guestLimitSubscription = this.authService.guestLimitReached$.subscribe(isReached => {
      this.showGuestLimitWarning = isReached;
    });
    this.guestLimitResetTimeSubscription = this.authService.guestLimitResetTime$.subscribe(message => {
      this.guestLimitWarningMessage = message;
    });
  }

  ngOnDestroy() {
    this.destroy$.unsubscribe();
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
    } catch(err) { }
  }

  // Use the AfterViewChecked lifecycle hook to trigger the scroll method.
  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  // Utility function to detect mobile devices - now uses UIStateService
  isMobileDevice(): boolean {
    return this.uiState.isMobile;
  }

  // Handle message sent from the input component
  async onMessageSent(message: string): Promise<void> {
    if (message.trim() || this.pendingFiles.length > 0) {
      try {
        // Check if we have files to send
        if (this.pendingFiles.length > 0) {
          console.log('Sending message with files:', this.pendingFiles);
          // Use ChatStateService for sending messages with files
          await this.chatState.sendMessageWithFiles(message, this.pendingFiles);
          // Clear pending files after sending
          this.pendingFiles = [];
        } else {
          // Regular text message without files
          await this.chatState.sendMessage(message);
        }

        console.log('User message sent:', message);
        this.scrollToBottom();

        // Generate AI response after message is confirmed sent
        await this.generateMessage();
      } catch (error) {
        console.error('Error sending message:', error);
        // Error is now available through error$ observable
      }
    }
  }

  // Generate a new message
  async generateMessage(): Promise<void> {
    try {
      await this.chatState.generateMessage(this.aiName);
    } catch (error) {
      console.error('Error generating AI response:', error);
      // Error is now available through error$ observable
    }
  }

  // Handle audio recording request
  onAudioRequested(): void {
    console.log('Audio recording requested');
    // The voice recording is now handled internally by the input field component
    // The component will emit the audio through filesSelected when recording is complete
  }

  // Handle file attachment request (including voice messages)
  async onFileRequested(filePreviews: FilePreview[]): Promise<void> {
    console.log('Files selected:', filePreviews);

    // Check if this is a voice message (audio file with specific naming pattern)
    if (filePreviews.length === 1 &&
      filePreviews[0].mimeType.startsWith('audio/') &&
      filePreviews[0].name.includes('Voice message')) {

      // This is a voice message, send it immediately
      const voiceFile = filePreviews[0];

      try {
        // Extract duration from the name (format: "Voice message (MM:SS)")
        const durationMatch = voiceFile.name.match(/\((\d+):(\d+)\)/);
        let duration = 0;
        if (durationMatch) {
          const minutes = parseInt(durationMatch[1]);
          const seconds = parseInt(durationMatch[2]);
          duration = minutes * 60 + seconds;
        }

        // Send as voice message
        await this.chatState.sendVoiceMessage(
          voiceFile.file,
          duration,
          voiceFile.mimeType
        );

        console.log('Voice message sent');
        this.scrollToBottom();

        // Generate AI response
        await this.generateMessage();
      } catch (error) {
        console.error('Error sending voice message:', error);
      }
    } else {
      // Regular file attachments - store temporarily until message is sent
      this.pendingFiles = [...this.pendingFiles, ...filePreviews];
    }
  }

  // SIMPLIFIED: Camera is now handled by the input component directly
  onCameraRequested(): void {
    console.log('Camera requested - handled by input component');
    // The input component now handles camera directly
    // No need for a dialog
  }

  onLocationRequested(): void {
    console.log('Location sharing requested');
    // TODO: Get and display current location
    // When implemented, this could:
    // 1. Get user's current location
    // 2. Create a location message type
    // 3. Send it using chatService
  }

  // Method to delete a message
  deleteMessage(messageId: number) {
    // Call the ChatStateService to delete the message
    this.chatState.deleteMessage(messageId);
  }

  // Method to change a message
  patchMessage(messageId: number, content: string) {
    // Call the ChatStateService to alter the message
    this.chatState.patchMessage(messageId, content);
  }
}
