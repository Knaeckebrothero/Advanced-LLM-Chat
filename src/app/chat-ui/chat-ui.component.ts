import { Component, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { ChatService } from '../chat/chat.service';
import { Message } from '../data/objects/message';

@Component({
    selector: 'app-chat-ui',
    templateUrl: './chat-ui.component.html',
    styleUrls: ['./chat-ui.component.scss'],
    standalone: false
})
export class ChatUiComponent implements AfterViewChecked {

  @ViewChild('messageContainer') private messageContainer!: ElementRef;
  @ViewChild('fileInput') fileInputRef!: ElementRef<HTMLInputElement>;

  userName: string = 'user';
  aiName: string = 'Assistant';
  conversationId: number = 1;
  inputField: string = '';
  messages = this.chatService.messages;
  selectedFiles: File[] = [];
  isRecording: boolean = false;

  constructor(private chatService: ChatService) {}

  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  private scrollToBottom(): void {
    try {
      this.messageContainer.nativeElement.scrollTop = this.messageContainer.nativeElement.scrollHeight;
    } catch (err) {}
  }

  isMobileDevice(): boolean {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  }

  handleEnterKeyPress(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      if (this.isMobileDevice()) {
        event.preventDefault();
      } else {
        this.handleActionClick();
        event.preventDefault();
      }
    }
  }

  handleActionClick(): void {
    const trimmedInput = this.inputField.trim();
    if (trimmedInput || this.selectedFiles.length > 0) {
      this.inputUserMessage();
      this.generateMessage();
    } else {
      this.startVoiceInput();
    }
  }

  inputUserMessage() {
    if (this.inputField.trim() !== '' || this.selectedFiles.length > 0) {
      this.chatService.sendMessage(this.inputField);
      this.scrollToBottom();
      this.inputField = '';
      this.selectedFiles = [];
    }
  }

  generateMessage() {
    this.chatService.generateMessage(this.aiName);
  }

  startVoiceInput() {
    this.isRecording = true;
    console.log('Voice input triggered');

    setTimeout(() => {
      this.isRecording = false;
      this.inputField = '🎤 Spracheingabe erkannt...';
    }, 2000);
  }

  onPlusClick(): void {
    this.fileInputRef.nativeElement.click();
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      const newFiles = Array.from(input.files);
      this.selectedFiles = [...this.selectedFiles, ...newFiles];
    }
  }

  deleteMessage(messageId: number) {
    this.chatService.deleteMessage(messageId);
  }

  patchMessage(message: Message) {
    this.chatService.patchMessage(message.id!, 'New message content');
  }

  get selectedFileNames(): string {
    return this.selectedFiles.map(file => file.name).join(', ');
  }
}
