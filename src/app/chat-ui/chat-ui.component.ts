import { Component, ViewChild, ElementRef, AfterViewChecked, OnInit, OnDestroy } from '@angular/core';
import { ChatService } from '../chat/chat.service';
import { Message } from '../data/objects/message';
import { AuthService } from '../auth/auth.service';
import { Subscription } from 'rxjs';
import { FilePreview } from '../data/objects/file-preview';


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
        // Log files for demo purposes
        if (this.pendingFiles.length > 0) {
          console.log('Message sent with files:', this.pendingFiles);
        }

        // Wait for the message to be sent (and conversation created if needed)
        await this.chatService.sendMessage(message);
        console.log('User added message:', message);
        this.scrollToBottom();

        // Clear pending files after sending
        this.pendingFiles = [];

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
  }

  // Handle file attachment request
  onFileRequested(filePreviews: FilePreview[]): void {
    console.log('Files selected:', filePreviews);
    // Store files temporarily until message is sent
    this.pendingFiles = filePreviews;
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
  }

  // Method to delete a message
  deleteMessage(messageId: number) {
    // Call the ChatService to delete the message
    this.chatService.deleteMessage(messageId);
  }

  // Method to change a message
  patchMessage(message: Message) {
    // Call the ChatService to alter the message
    this.chatService.patchMessage(message.id!, "New message content");
  }
}
