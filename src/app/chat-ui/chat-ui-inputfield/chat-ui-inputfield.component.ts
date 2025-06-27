import { Component, EventEmitter, Output, ViewChild, ElementRef, AfterViewInit, OnInit, OnDestroy, Input } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { FilePreview, FilePreviewUtil, FileType, UploadStatus } from '../../data/objects/file-preview';


@Component({
  selector: 'app-chat-ui-inputfield',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatIconModule,
    MatButtonModule,
    MatMenuModule,
    MatTooltipModule,
    MatChipsModule,
    MatProgressBarModule
  ],
  templateUrl: './chat-ui-inputfield.component.html',
  styleUrls: ['./chat-ui-inputfield.component.scss']
})
export class ChatUiInputfieldComponent implements AfterViewInit, OnInit, OnDestroy {
  // ViewChild to access the textarea element directly
  @ViewChild('messageTextarea') private messageTextarea!: ElementRef<HTMLTextAreaElement>;
  @ViewChild('fileInput') private fileInput!: ElementRef<HTMLInputElement>;
  @ViewChild('waveformCanvas') private waveformCanvas!: ElementRef<HTMLCanvasElement>;

  // The message text bound to the textarea
  messageText: string = '';

  // File previews array - now with Input to receive files from parent
  @Input() set externalFiles(files: FilePreview[]) {
    if (files && files.length > 0) {
      // Merge external files with existing ones
      this.filePreviews = [...files];
    }
  }

  // Input property to determine if the device is mobile
  @Input() isMobile: boolean = false;

  filePreviews: FilePreview[] = [];

  // Event emitters for parent component communication
  @Output() messageSent = new EventEmitter<string>();
  @Output() audioRequested = new EventEmitter<void>();
  @Output() filesSelected = new EventEmitter<FilePreview[]>();  // Changed from fileRequested
  @Output() cameraRequested = new EventEmitter<void>();
  @Output() locationRequested = new EventEmitter<void>();

  // Device capability flags
  hasCamera: boolean = false;
  hasGeolocation: boolean = false;

  // Voice recording properties
  isRecording: boolean = false;
  recordingStartTime: number = 0;
  recordingTime: Date = new Date(0);
  recordingTimer: any;
  waveformAnimationId: any;
  waveformWidth: number = 200;
  waveformData: number[] = [];
  isHoldToRecord: boolean = true; // Toggle between hold-to-record and tap-to-record
  recordingDuration: number = 0; // Store duration in seconds

  // Track if we have content to show appropriate button
  get hasContent(): boolean {
    return this.messageText.trim().length > 0 || this.filePreviews.length > 0;
  }

  ngOnInit() {
    // Check device capabilities
    this.checkDeviceCapabilities();
  }

  ngAfterViewInit() {
    // Initial adjustment of textarea height
    this.adjustTextareaHeight();
    // Set initial waveform width
    this.updateWaveformWidth();
  }

  // Check what capabilities the device has
  private checkDeviceCapabilities(): void {
    // Check for camera support
    // We check for mediaDevices API and also if we're in a secure context (HTTPS)
    if (navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === 'function' &&
      window.isSecureContext) {
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

    // Check if we have either text or files to send
    if (trimmedMessage || this.filePreviews.length > 0) {
      // TODO: In the future, emit both message and files together
      if (trimmedMessage) {
        this.messageSent.emit(trimmedMessage);
      }

      // Clear the input and files after sending
      this.messageText = '';
      this.clearFilePreviews();

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
  }

  // Handle location sharing
  handleLocationClick(): void {
    this.locationRequested.emit();
    console.log('Location sharing requested');
  }

  // Handle file selection from input
  async handleFileSelection(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const files = input.files;

    if (files && files.length > 0) {
      const fileArray = Array.from(files);

      // Validate file sizes (10MB limit per file)
      const invalidFiles = fileArray.filter(file => !FilePreviewUtil.validateFileSize(file, 10));
      if (invalidFiles.length > 0) {
        console.error('Some files exceed the 10MB limit:', invalidFiles);
        // TODO: Show error message to user
      }

      // Create file previews for valid files
      const validFiles = fileArray.filter(file => FilePreviewUtil.validateFileSize(file, 10));
      const newPreviews: FilePreview[] = [];

      for (const file of validFiles) {
        try {
          const preview = await FilePreviewUtil.createFromFile(file);
          newPreviews.push(preview);
        } catch (error) {
          console.error('Error creating file preview:', error);
        }
      }

      // Add to existing previews
      this.filePreviews = [...this.filePreviews, ...newPreviews];

      // Emit the file previews
      this.filesSelected.emit(this.filePreviews);

      console.log('Files selected:', this.filePreviews);

      // Reset the input so the same file can be selected again
      input.value = '';
    }
  }

  // Remove a file preview
  removeFilePreview(fileId: string): void {
    this.filePreviews = this.filePreviews.filter(fp => fp.id !== fileId);
    this.filesSelected.emit(this.filePreviews);
  }

  // Clear all file previews
  clearFilePreviews(): void {
    this.filePreviews = [];
    this.filesSelected.emit(this.filePreviews);
  }

  // Get icon for file type (helper for template)
  getFileIcon(type: string): string {
    return FilePreviewUtil.getFileIcon(type as any);
  }

  // Utility function to detect mobile devices
  isMobileDevice(): boolean {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  }

  // Voice Recording Methods

  // Start recording
  startRecording(): void {
    if (!this.isHoldToRecord) {
      this.toggleRecording();
    }
  }

  // Toggle recording (for tap mode)
  private toggleRecording(): void {
    if (this.isRecording) {
      this.stopRecording();
    } else {
      this.beginRecording();
    }
  }

  // Begin the recording process
  private beginRecording(): void {
    this.isRecording = true;
    this.recordingStartTime = Date.now();
    this.recordingDuration = 0;
    this.updateWaveformWidth();

    // Start the timer
    this.recordingTimer = setInterval(() => {
      const elapsed = Date.now() - this.recordingStartTime;
      this.recordingTime = new Date(elapsed);
      this.recordingDuration = Math.floor(elapsed / 1000);
    }, 100);

    // Start the waveform animation
    this.startWaveformAnimation();

    console.log('Voice recording started');
  }

  // Stop recording and create audio file
  private stopRecording(): void {
    if (!this.isRecording) return;

    this.isRecording = false;

    // Stop timers
    if (this.recordingTimer) {
      clearInterval(this.recordingTimer);
    }

    // Stop animation
    if (this.waveformAnimationId) {
      cancelAnimationFrame(this.waveformAnimationId);
    }

    // Create a mock audio file
    this.createAudioFilePreview();

    // Reset
    this.recordingTime = new Date(0);
    this.waveformData = [];

    console.log('Voice recording stopped');
  }

  // Cancel recording without saving
  cancelRecording(): void {
    this.isRecording = false;

    // Stop timers
    if (this.recordingTimer) {
      clearInterval(this.recordingTimer);
    }

    // Stop animation
    if (this.waveformAnimationId) {
      cancelAnimationFrame(this.waveformAnimationId);
    }

    // Reset
    this.recordingTime = new Date(0);
    this.waveformData = [];

    console.log('Voice recording cancelled');
  }

  // Send the voice message
  sendVoiceMessage(): void {
    this.stopRecording();
  }

  // Create audio file preview
  private async createAudioFilePreview(): Promise<void> {
    // Create a mock audio file (in real implementation, this would be the actual recording)
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const duration = this.formatDuration(this.recordingDuration);
    const fileName = `voice-message-${timestamp}.webm`;

    // Create a mock blob (in real implementation, this would be the actual audio data)
    const mockAudioData = new Blob(['mock audio data'], { type: 'audio/webm' });

    // Create a File object
    const audioFile = new File([mockAudioData], fileName, {
      type: 'audio/webm',
      lastModified: Date.now()
    });

    // Create FilePreview
    const filePreview: FilePreview = {
      id: FilePreviewUtil.generateId(),
      file: audioFile,
      name: `Voice message (${duration})`,
      size: mockAudioData.size,
      sizeFormatted: FilePreviewUtil.formatFileSize(mockAudioData.size),
      type: FileType.AUDIO,
      mimeType: 'audio/webm',
      uploadStatus: UploadStatus.PENDING
    };

    // Add to file previews
    this.filePreviews = [...this.filePreviews, filePreview];
    this.filesSelected.emit(this.filePreviews);

    console.log('Audio file created:', filePreview);
  }

  // Format duration in MM:SS format
  private formatDuration(seconds: number): string {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
  }

  // Update waveform canvas width based on container
  private updateWaveformWidth(): void {
    // In a real implementation, you'd calculate this based on the container width
    // For now, we'll use a fixed width that looks good
    this.waveformWidth = window.innerWidth > 768 ? 400 : window.innerWidth - 150;
  }

  // Start waveform animation
  private startWaveformAnimation(): void {
    if (!this.waveformCanvas) return;

    const canvas = this.waveformCanvas.nativeElement;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Initialize waveform data
    const barCount = 50;
    this.waveformData = new Array(barCount).fill(0.3);

    const animate = () => {
      // Clear canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Update waveform data with random variations to simulate audio input
      this.waveformData = this.waveformData.map((value, index) => {
        const change = (Math.random() - 0.5) * 0.3;
        const newValue = Math.max(0.1, Math.min(1, value + change));
        return value * 0.7 + newValue * 0.3; // Smooth the animation
      });

      // Draw waveform
      const barWidth = canvas.width / barCount;
      const maxHeight = canvas.height * 0.8;

      ctx.fillStyle = '#2C8BCC';
      this.waveformData.forEach((value, index) => {
        const barHeight = value * maxHeight;
        const x = index * barWidth + barWidth * 0.1;
        const y = (canvas.height - barHeight) / 2;
        const width = barWidth * 0.8;

        // Draw rounded bars
        const radius = width / 2;
        ctx.beginPath();
        ctx.moveTo(x + radius, y);
        ctx.lineTo(x + width - radius, y);
        ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
        ctx.lineTo(x + width, y + barHeight - radius);
        ctx.quadraticCurveTo(x + width, y + barHeight, x + width - radius, y + barHeight);
        ctx.lineTo(x + radius, y + barHeight);
        ctx.quadraticCurveTo(x, y + barHeight, x, y + barHeight - radius);
        ctx.lineTo(x, y + radius);
        ctx.quadraticCurveTo(x, y, x + radius, y);
        ctx.closePath();
        ctx.fill();
      });

      if (this.isRecording) {
        this.waveformAnimationId = requestAnimationFrame(animate);
      }
    };

    animate();
  }

  // Hold-to-record event handlers
  onMicTouchStart(event: TouchEvent): void {
    if (this.isHoldToRecord) {
      event.preventDefault();
      this.beginRecording();
    }
  }

  onMicTouchEnd(event: TouchEvent): void {
    if (this.isHoldToRecord && this.isRecording) {
      event.preventDefault();
      this.stopRecording();
    }
  }

  onMicMouseDown(event: MouseEvent): void {
    if (this.isHoldToRecord && !this.isMobileDevice()) {
      event.preventDefault();
      this.beginRecording();
    }
  }

  onMicMouseUp(event: MouseEvent): void {
    if (this.isHoldToRecord && this.isRecording && !this.isMobileDevice()) {
      event.preventDefault();
      this.stopRecording();
    }
  }

  onMicMouseLeave(event: MouseEvent): void {
    if (this.isHoldToRecord && this.isRecording && !this.isMobileDevice()) {
      this.stopRecording();
    }
  }

  // Clean up resources when component is destroyed
  ngOnDestroy(): void {
    // Stop any ongoing recording
    if (this.isRecording) {
      this.cancelRecording();
    }

    // Revoke any object URLs to free memory
    this.filePreviews.forEach(preview => {
      if (preview.preview && preview.preview.startsWith('blob:')) {
        URL.revokeObjectURL(preview.preview);
      }
    });
  }
}
