import { Component, ViewChild, ElementRef, AfterViewChecked, OnInit, OnDestroy } from '@angular/core';
import { ChatService } from '../chat/chat.service';
import { Message } from '../data/objects/message';
import { AuthService } from '../auth/auth.service';
import { Subscription } from 'rxjs';
import { FilePreview, FilePreviewUtil } from '../data/objects/file-preview';
import { RecordingResult } from '../data/objects/recording';


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
  conversationId: number = 1;
  pendingFiles: FilePreview[] = [];

  // The inputField property is bound to the input field in the template.
  inputField: string = '';

  // Messages are managed by the ChatService and are passed to this component via observable.
  messages = this.chatService.messages;
  showGuestLimitWarning = false;
  guestLimitWarningMessage: string | null = null;
  private guestLimitSubscription!: Subscription;
  private guestLimitResetTimeSubscription!: Subscription;

  // Constructor - REMOVED MatDialog dependency
  constructor(
    private chatService: ChatService,
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

  // Utility function to detect mobile devices
  isMobileDevice(): boolean {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  }

  // Handle message sent from the input component
  async onMessageSent(message: string): Promise<void> {
    if (message.trim() || this.pendingFiles.length > 0) {
      try {
        // Check if we have files to send
        if (this.pendingFiles.length > 0) {
          console.log('Sending message with files:', this.pendingFiles);
          // Use the new sendMessageWithFiles method
          await this.chatService.sendMessageWithFiles(message, this.pendingFiles);
          // Clear pending files after sending
          this.pendingFiles = [];
        } else {
          // Regular text message without files
          await this.chatService.sendMessage(message);
        }

        console.log('User message sent:', message);
        this.scrollToBottom();

        // Generate AI response after message is confirmed sent
        await this.generateMessage();
      } catch (error) {
        console.error('Error sending message:', error);
        // TODO: Optionally show an error to the user
      }
    }
  }

  // Generate a new message
  async generateMessage(): Promise<void> {
    try {
      await this.chatService.generateMessage(this.aiName);
    } catch (error) {
      console.error('Error generating AI response:', error);
      // Optionally show an error to the user
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
        await this.chatService.sendVoiceMessage(
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
    // Call the ChatService to delete the message
    this.chatService.deleteMessage(messageId);
  }

  // Method to change a message
  patchMessage(messageId: number, content: string) {
    // Call the ChatService to alter the message
    this.chatService.patchMessage(messageId, content);
  }
}
