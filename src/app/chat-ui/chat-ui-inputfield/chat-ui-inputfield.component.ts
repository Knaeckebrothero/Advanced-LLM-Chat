import { Component, EventEmitter, Output, ViewChild, ElementRef, AfterViewInit, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';


@Component({
  selector: 'app-chat-ui-inputfield',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatIconModule,
    MatButtonModule,
    MatMenuModule,
    MatTooltipModule
  ],
  templateUrl: './chat-ui-inputfield.component.html',
  styleUrls: ['./chat-ui-inputfield.component.scss']
})
export class ChatUiInputfieldComponent implements AfterViewInit, OnInit {
  // ViewChild to access the textarea element directly
  @ViewChild('messageTextarea') private messageTextarea!: ElementRef<HTMLTextAreaElement>;
  @ViewChild('fileInput') private fileInput!: ElementRef<HTMLInputElement>;

  // The message text bound to the textarea
  messageText: string = '';

  // Event emitters for parent component communication
  @Output() messageSent = new EventEmitter<string>();
  @Output() audioRequested = new EventEmitter<void>();
  @Output() fileRequested = new EventEmitter<File[]>();
  @Output() cameraRequested = new EventEmitter<void>();
  @Output() locationRequested = new EventEmitter<void>();

  // Device capability flags
  hasCamera: boolean = false;
  hasGeolocation: boolean = false;

  // Track if we have content to show appropriate button
  get hasContent(): boolean {
    return this.messageText.trim().length > 0;
  }

  ngOnInit() {
    // Check device capabilities
    this.checkDeviceCapabilities();
  }

  ngAfterViewInit() {
    // Initial adjustment of textarea height
    this.adjustTextareaHeight();
  }

  // Check what capabilities the device has
  private checkDeviceCapabilities(): void {
    // Check for camera support
    // We check for mediaDevices API and also if we're in a secure context (HTTPS)
    if (navigator.mediaDevices && window.isSecureContext) {
      // Check if there are any video input devices
      navigator.mediaDevices.enumerateDevices()
        .then(devices => {
          this.hasCamera = devices.some(device => device.kind === 'videoinput');
        })
        .catch(() => {
          this.hasCamera = false;
        });
    }

    // Check for geolocation support
    this.hasGeolocation = 'geolocation' in navigator && window.isSecureContext;
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

  // Handle file menu item clicks
  handleFileMenuClick(action: 'file' | 'camera' | 'location'): void {
    switch(action) {
      case 'file':
        // Trigger the hidden file input
        this.fileInput.nativeElement.click();
        break;
      case 'camera':
        this.handleCameraClick();
        break;
      case 'location':
        this.handleLocationClick();
        break;
    }
  }

  // Handle direct camera button click
  handleCameraClick(): void {
    this.cameraRequested.emit();
    console.log('Camera requested');
    // TODO: Implement camera capture functionality
  }

  // Handle location sharing
  handleLocationClick(): void {
    this.locationRequested.emit();
    console.log('Location sharing requested');
    // TODO: Implement location sharing functionality
  }

  // Handle file selection from input
  handleFileSelection(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = input.files;

    if (files && files.length > 0) {
      const fileArray = Array.from(files);
      this.fileRequested.emit(fileArray);
      console.log('Files selected:', fileArray);
      // TODO: Show file preview in UI

      // Reset the input so the same file can be selected again
      input.value = '';
    }
  }

  // Utility function to detect mobile devices
  isMobileDevice(): boolean {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  }
}
