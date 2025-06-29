import { Component, ViewChild, ElementRef, AfterViewChecked, OnInit, OnDestroy } from '@angular/core';
import { Subscription } from 'rxjs';
import { ChatService } from '../chat/chat.service';
import { Message } from '../data/objects/message';
import { ThemeService } from 'src/styles/themes/theme.service';
import { AuthService } from '../auth/auth.service';

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
  isDarkMode: boolean = false;
  private themeSubscription!: Subscription;

  inputField: string = '';

  // Messages are managed by the ChatService
  messages = this.chatService.messages;
  showGuestLimitWarning = false;
  guestLimitWarningMessage: string | null = null;
  private guestLimitSubscription!: Subscription;
  private guestLimitResetTimeSubscription!: Subscription;

  constructor(
    private chatService: ChatService,
    private themeService: ThemeService,
    private authService: AuthService
  ) {}

  ngOnInit(): void {
    // Subscribe to theme changes to toggle UI elements like the logo
    this.themeSubscription = this.themeService.getEffectiveTheme$().subscribe(theme => {
      this.isDarkMode = theme === 'dark';
    });
    this.guestLimitSubscription = this.authService.guestLimitReached$.subscribe(isReached => {
      this.showGuestLimitWarning = isReached;
    });
    this.guestLimitResetTimeSubscription = this.authService.guestLimitResetTime$.subscribe(message => {
      this.guestLimitWarningMessage = message;
    });


  }

  ngOnDestroy(): void {
    // Unsubscribe to prevent memory leaks
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

  ngAfterViewChecked() {
    // Automatically scroll to the newest message
    this.scrollToBottom();
  }

  private scrollToBottom(): void {
    try {
      this.messageContainer.nativeElement.scrollTop = this.messageContainer.nativeElement.scrollHeight;
    } catch(err) { }
  }

  async onMessageSent(message: string): Promise<void> {
    if (message.trim()) {
      try {
        // First, send the user's message and wait for it to be processed
        await this.chatService.sendMessage(message);
        console.log('User added message:', message);
        this.scrollToBottom();

        // After the user's message is sent, generate the AI response
        await this.chatService.generateMessage(this.aiName);
      } catch (error) {
        console.error('Error during message sending or generation:', error);
        // Optionally, display an error message to the user in the UI
      }
    }
  }


  // Utility function to detect mobile devices
  isMobileDevice(): boolean {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  }
  // TODO: Do we want to move this to the app.component?

  // Function to handle Enter key in textarea
  handleEnterKeyPress(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      if (this.isMobileDevice()) {
        // It's a mobile device, allow line breaks on Enter
        event.preventDefault(); // This line might be removed if you want to allow new lines
      } else {
        // It's not a mobile device, send the message
        this.inputUserMessage();
        event.preventDefault(); // Prevents new line even on desktop after sending message
      }
    }
  }

  // The addMessage method is called when the user submits a new message.
  inputUserMessage() {
    // The inputField property is checked to ensure that it is not empty.
    if (this.inputField !== '') {
      this.authService.setGuestLimitReached(false, null); // Reset on new user message
      // The ChatService is used to add a new usermessage to the history.
      this.chatService.sendMessage(this.inputField);
      console.log('User added message:');

      this.scrollToBottom();

      // The input field is cleared.
      this.inputField = '';
    }
  }

  // Placeholder for handling audio recording requests
  onAudioRequested(): void {
    console.log('Audio recording requested');
    // TODO: Implement audio recording functionality
  }

  // Placeholder for handling file attachment requests
  onFileRequested(): void {
    console.log('File attachment requested');
    // TODO: Implement file upload functionality
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
