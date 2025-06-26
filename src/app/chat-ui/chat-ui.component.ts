import { Component, ViewChild, ElementRef, AfterViewChecked, OnInit, OnDestroy } from '@angular/core';
import { Subscription } from 'rxjs';
import { ChatService } from '../chat/chat.service';
import { Message } from '../data/objects/message';
import { ThemeService } from 'src/styles/themes/theme.service';

@Component({
  selector: 'app-chat-ui',
  templateUrl: './chat-ui.component.html',
  styleUrls: ['./chat-ui.component.scss'],
  standalone: false
})
export class ChatUiComponent implements OnInit, AfterViewChecked, OnDestroy {

  @ViewChild('messageContainer') private messageContainer!: ElementRef;

  // Component state
  userName: string = 'user';
  aiName: string = 'Assistant';
  isDarkMode: boolean = false;
  private themeSubscription!: Subscription;

  // Messages are managed by the ChatService
  messages = this.chatService.messages;

  constructor(
    private chatService: ChatService,
    private themeService: ThemeService
  ) {}

  ngOnInit(): void {
    // Subscribe to theme changes to toggle UI elements like the logo
    this.themeSubscription = this.themeService.getEffectiveTheme$().subscribe(theme => {
      this.isDarkMode = theme === 'dark';
    });
  }

  ngOnDestroy(): void {
    // Unsubscribe to prevent memory leaks
    if (this.themeSubscription) {
      this.themeSubscription.unsubscribe();
    }
  }

  ngAfterViewChecked() {
    // Automatically scroll to the newest message
    this.scrollToBottom();
  }

  private scrollToBottom(): void {
    try {
      this.messageContainer.nativeElement.scrollTop = this.messageContainer.nativeElement.scrollHeight;
    } catch(err) {
      // Ignore errors if the element isn't available yet
    }
  }

  /**
   * Handles the messageSent event from the input field component.
   * It sends the user's message and then triggers the AI to generate a response.
   */
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
    this.chatService.deleteMessage(messageId);
  }

  // Method to change a message
  patchMessage(message: Message) {
    // This is an example; you might want a more sophisticated editing UI
    this.chatService.patchMessage(message.id!, "New message content");
  }
}
