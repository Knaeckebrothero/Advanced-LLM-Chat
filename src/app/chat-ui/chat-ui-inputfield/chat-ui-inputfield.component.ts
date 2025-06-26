import { Component, EventEmitter, Output, ViewChild, ElementRef, AfterViewInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';


@Component({
  selector: 'app-chat-ui-inputfield',
  standalone: true,
  imports: [CommonModule, FormsModule, MatIconModule, MatButtonModule],
  templateUrl: './chat-ui-inputfield.component.html',
  styleUrls: ['./chat-ui-inputfield.component.scss']
})
export class ChatUiInputfieldComponent implements AfterViewInit {
  // ViewChild to access the textarea element directly
  @ViewChild('messageTextarea') private messageTextarea!: ElementRef<HTMLTextAreaElement>;

  // The message text bound to the textarea
  messageText: string = '';

  // Event emitters for parent component communication
  @Output() messageSent = new EventEmitter<string>();
  @Output() audioRequested = new EventEmitter<void>();
  @Output() fileRequested = new EventEmitter<void>();

  // Track if we have content to show appropriate button
  get hasContent(): boolean {
    return this.messageText.trim().length > 0;
  }

  ngAfterViewInit() {
    // Initial adjustment of textarea height
    this.adjustTextareaHeight();
  }

  // Handle Enter key press - send on Enter, new line on Shift+Enter
  handleKeyPress(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  // Adjust textarea height based on content
  onTextareaInput(): void {
    this.adjustTextareaHeight();
  }

  // Method to dynamically adjust the textarea height
  private adjustTextareaHeight(): void {
    const textarea = this.messageTextarea.nativeElement;

    // Reset height to auto to get the correct scrollHeight
    textarea.style.height = 'auto';

    // Calculate new height (max 150px which is roughly 5-6 lines)
    const newHeight = Math.min(textarea.scrollHeight, 150);
    textarea.style.height = newHeight + 'px';
  }

  // Send the message
  sendMessage(): void {
    const trimmedMessage = this.messageText.trim();
    if (trimmedMessage) {
      this.messageSent.emit(trimmedMessage);
      this.messageText = '';

      // Reset textarea height after sending
      setTimeout(() => this.adjustTextareaHeight(), 0);
    }
  }

  // Handle action button click (send or microphone)
  handleActionClick(): void {
    if (this.hasContent) {
      this.sendMessage();
    } else {
      this.audioRequested.emit();
    }
  }

  // Handle file attachment request
  handleFileClick(): void {
    this.fileRequested.emit();
    console.log('File attachment requested'); // Temporary for testing
  }

  // Utility function to detect mobile devices
  isMobileDevice(): boolean {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  }
}
