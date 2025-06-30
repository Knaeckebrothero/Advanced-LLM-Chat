import { Component, ViewChild, ElementRef, AfterViewChecked, OnInit, OnDestroy } from '@angular/core';
import { Subscription } from 'rxjs';
import { ChatService } from '../chat/chat.service';
import { Message } from '../data/objects/message';
import { ThemeService } from 'src/styles/themes/theme.service';
import { AuthService } from '../auth/auth.service';
import { FilePreview } from '../data/objects/file-preview';

@Component({
  selector: 'app-chat-ui',
  templateUrl: './chat-ui.component.html',
  styleUrls: ['./chat-ui.component.scss'],
  standalone: false
})
export class ChatUiComponent implements AfterViewChecked, OnInit, OnDestroy {

  @ViewChild('messageContainer') private messageContainer!: ElementRef;

  userName: string = 'user';
  aiName: string = 'Assistant';
  isDarkMode: boolean = false;
  private themeSubscription!: Subscription;
  conversationId: number = 1;
  pendingFiles: FilePreview[] = [];
  inputField: string = '';
  messages = this.chatService.messages;
  showGuestLimitWarning = false;
  guestLimitWarningMessage: string | null = null;
  private guestLimitSubscription!: Subscription;
  private guestLimitResetTimeSubscription!: Subscription;

  // Properties for dropdowns
  selectedRole: 'student' | 'teacher' = 'student';
  selectedLanguage: 'DE' | 'EN' = 'DE';

  constructor(
    private chatService: ChatService,
    private themeService: ThemeService,
    private authService: AuthService
  ) {}

  ngOnInit(): void {
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
    this.scrollToBottom();
  }

  private scrollToBottom(): void {
    try {
      this.messageContainer.nativeElement.scrollTop = this.messageContainer.nativeElement.scrollHeight;
    } catch(err) { }
  }

  async onMessageSent(message: string): Promise<void> {
    if (message.trim() || this.pendingFiles.length > 0) {
      try {
        if (this.pendingFiles.length > 0) {
          console.log('Message sent with files:', this.pendingFiles);
        }
        await this.chatService.sendMessage(message);
        console.log('User added message:', message);
        this.scrollToBottom();
        this.pendingFiles = [];
        await this.generateMessage();
      } catch (error) {
        console.error('Error sending message:', error);
      }
    }
  }

  isMobileDevice(): boolean {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  }

  async generateMessage(): Promise<void> {
    try {
      await this.chatService.generateMessage(this.aiName);
    } catch (error) {
      console.error('Error generating AI response:', error);
    }
  }

  onAudioRequested(): void {
    console.log('Audio recording requested');
  }

  onFileRequested(filePreviews: FilePreview[]): void {
    console.log('Files selected:', filePreviews);
    this.pendingFiles = filePreviews;
  }

  onCameraRequested(): void {
    console.log('Camera requested - handled by input component');
  }

  onLocationRequested(): void {
    console.log('Location sharing requested');
  }

  deleteMessage(messageId: number) {
    this.chatService.deleteMessage(messageId);
  }

  patchMessage(message: Message) {
    this.chatService.patchMessage(message.id!, "New message content");
  }

  // Methods for dropdowns
  setRole(role: 'student' | 'teacher'): void {
    this.selectedRole = role;
  }

  setLanguage(language: 'DE' | 'EN'): void {
    this.selectedLanguage = language;
  }
}
