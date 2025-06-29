import { Component, EventEmitter, Output, ViewChild, ElementRef, AfterViewInit, OnInit, OnDestroy, Input, NgZone } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { FilePreview } from '../../data/objects/file-preview';
import { DeviceCapabilitiesService } from '../services/device-capabilities.service';
import { VoiceRecordingService } from './voice-recording.service';
import { FileHandlingService } from '../services/file-handling.service';
import { RecordingConfig } from '../../data/objects/recording';


/**
 * ChatUiInputfieldComponent is a UI component that provides a versatile input field
 * for chat applications. It supports text input, file attachments, voice recording,
 * and additional actions like capturing location and photos.
 *
 * It integrates with external services for handling device capabilities, file management,
 * and voice recording. The component emits various events to allow the parent component
 * to handle different actions initiated by the user.
 *
 * The component dynamically adjusts its UI features such as responsive textarea height,
 * canvas resizing for visual elements, and action button switching based on user input
 * or available device capabilities.
 *
 * Lifecycle hooks:
 * - `ngOnInit()`: Initializes device capabilities and subscribes to voice recording state.
 * - `ngAfterViewInit()`: Performs post-render setup such as adjusting textarea and canvas dimensions.
 * - `ngOnDestroy()`: Cleans up subscriptions and resources.
 *
 * Features:
 * - Responsive text input area with adjustable height.
 * - File upload support with size validation and previews.
 * - Voice recording with a visual waveform displayed.
 * - Detecting and reflecting device-specific capabilities (camera, geolocation, etc.).
 * - Event emitters for sending messages, selecting files, requesting audio/camera/location.
 *
 * Events emitted:
 * - `messageSent`: Emits a string containing the entered message text.
 * - `audioRequested`: Emits when the user opts to start an audio recording.
 * - `filesSelected`: Emits the list of selected file previews.
 * - `cameraRequested`: Emits when the user initiates a camera action.
 * - `locationRequested`: Emits when the user requests to share their location.
 *
 * Inputs:
 * - `externalFiles`: Accepts an array of `FilePreview` objects passed from the parent to combine with existing files.
 * - `isMobile`: Flag to denote if the current device is mobile (used for rendering logic).
 *
 * Usage:
 * Intended to be used as an input field within a chat or messaging interface, with the ability to handle rich user interaction.
 * It facilitates communication between the user and the application through its modular, event-driven design.
 */
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
  constructor(
    private ngZone: NgZone,
    private deviceCapabilitiesService: DeviceCapabilitiesService,
    private voiceRecordingService: VoiceRecordingService,
    private fileHandlingService: FileHandlingService
  ) {}

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
  recordingTime: Date = new Date(0);
  canvasWidth: number = 800;
  canvasHeight: number = 80; // Taller to fill the input field
  isHoldToRecord: boolean = true; // Toggle between hold-to-record and tap-to-record
  recordingDuration: number = 0; // Store duration in seconds

  // Track if we have content to show appropriate button
  get hasContent(): boolean {
    return this.messageText.trim().length > 0 || this.filePreviews.length > 0;
  }

  // Subscription to recording state
  private recordingStateSubscription: any;

  ngOnInit() {
    // Subscribe to device capabilities
    this.deviceCapabilitiesService.getCapabilities().subscribe(capabilities => {
      this.hasCamera = capabilities.hasCamera;
      this.hasGeolocation = capabilities.hasGeolocation;
      this.isMobile = this.isMobile || capabilities.isMobile; // Use input or detected value
    });

    // Subscribe to recording state
    this.recordingStateSubscription = this.voiceRecordingService.getRecordingState().subscribe(state => {
      this.isRecording = state.isRecording;
      this.recordingDuration = state.duration;

      // Update recording time for display
      if (state.isRecording) {
        this.recordingTime = new Date(state.duration * 1000);
      } else {
        this.recordingTime = new Date(0);
      }
    });
  }

  ngAfterViewInit() {
    // Initial adjustment of textarea height
    this.adjustTextareaHeight();
    // Set initial canvas dimensions
    this.updateCanvasDimensions();

    // Add resize listener for responsive canvas
    window.addEventListener('resize', () => this.updateCanvasDimensions());
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

  // TODO: Check if this one is still needed
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
      const invalidFiles = fileArray.filter(file => !this.fileHandlingService.validateFileSize(file, 10));
      if (invalidFiles.length > 0) {
        console.error('Some files exceed the 10MB limit:', invalidFiles);
        // TODO: Show error message to user
      }

      // Create file previews for valid files
      const newPreviews = await this.fileHandlingService.createFilePreviews(fileArray, 10);

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
    return this.fileHandlingService.getFileIcon(type);
  }

  // Utility function to detect mobile devices - now handled by DeviceCapabilitiesService
  isMobileDevice(): boolean {
    return this.isMobile;
  }

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
  private async beginRecording(): Promise<void> {
    try {
      // Update canvas dimensions before starting recording
      this.updateCanvasDimensions();

      // Create recording config
      const config: RecordingConfig = {
        isHoldToRecord: this.isHoldToRecord,
        maxDuration: 300, // 5 minutes maximum
        audioConstraints: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      };

      // Start recording with visualization
      await this.voiceRecordingService.startRecording(
        config,
        this.waveformCanvas?.nativeElement
      );

      // Recording state is updated via subscription in ngOnInit

    } catch (error) {
      console.error('Error starting recording:', error);

      // Show error to user
      if (error instanceof DOMException) {
        if (error.name === 'NotAllowedError') {
          alert('Microphone access denied. Please allow microphone access and try again.');
        } else if (error.name === 'NotFoundError') {
          alert('No microphone found. Please connect a microphone and try again.');
        } else {
          alert('Error accessing microphone: ' + error.message);
        }
      }
    }
  }

  // Stop recording and create audio file
  private async stopRecording(): Promise<void> {
    try {
      const result = await this.voiceRecordingService.stopRecording();

      if (result) {
        // Create file preview from recording result
        const filePreview = this.fileHandlingService.createAudioFilePreview(result);

        // Add to file previews
        this.filePreviews = [...this.filePreviews, filePreview];
        this.filesSelected.emit(this.filePreviews);
      }
    } catch (error) {
      console.error('Error stopping recording:', error);
    }
  }

  // Cancel recording without saving
  cancelRecording(): void {
    this.voiceRecordingService.cancelRecording();
  }

  // Send the voice message
  async sendVoiceMessage(): Promise<void> {
    await this.stopRecording();
  }

  // Update canvas dimensions to match container
  private updateCanvasDimensions(): void {
    // Get the container element to match its size
    const container = document.querySelector('.input-field-container');
    if (container) {
      const rect = container.getBoundingClientRect();
      this.canvasWidth = Math.floor(rect.width);
      this.canvasHeight = Math.floor(rect.height) || 80; // Default height if not yet rendered

      // Note: The visualizer is now managed by VoiceRecordingService
      // and will adapt to the canvas size automatically
    }
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
    // Remove resize listener
    window.removeEventListener('resize', () => this.updateCanvasDimensions());

    // Unsubscribe from observables
    if (this.recordingStateSubscription) {
      this.recordingStateSubscription.unsubscribe();
    }

    // Stop any ongoing recording
    if (this.isRecording) {
      this.voiceRecordingService.cancelRecording();
    }

    // Revoke any object URLs to free memory
    this.filePreviews.forEach(preview => {
      if (preview.preview && preview.preview.startsWith('blob:')) {
        URL.revokeObjectURL(preview.preview);
      }
    });
  }
}
