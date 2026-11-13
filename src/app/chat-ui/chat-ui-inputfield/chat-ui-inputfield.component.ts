import { Component, EventEmitter, Output, ViewChild, ElementRef, AfterViewInit, OnInit, OnDestroy, Input, NgZone } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MatDividerModule } from '@angular/material/divider';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import {FilePreview, FilePreviewUtil} from '../../data/objects/file-preview';
import { DeviceCapabilitiesService } from '../services/device-capabilities.service';
import { VoiceRecordingService } from './voice-recording.service';
import { FileHandlingService } from '../services/file-handling.service';
import { RecordingConfig } from '../../data/objects/recording';
import { ApiService } from '../../services/api.service';
import { UploadStatus } from '../../data/objects/file-preview';
import { environment } from '../../environments/environment';
import { DomSanitizer, SafeUrl } from '@angular/platform-browser';
import { ImagePreviewDialogComponent, ImagePreviewDialogData } from './image-preview-dialog/image-preview-dialog.component';
import { TranslateModule, TranslateService } from "@ngx-translate/core";
import { ContextMeterComponent } from './context-meter/context-meter.component';
import { IContextSize } from '../../data/models/conversation.model';


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
    MatDividerModule,
    MatTooltipModule,
    MatProgressBarModule,
    MatDialogModule,
    TranslateModule,
    ContextMeterComponent
  ],
  templateUrl: './chat-ui-inputfield.component.html',
  styleUrls: ['./chat-ui-inputfield.component.scss']
})
export class ChatUiInputfieldComponent implements AfterViewInit, OnInit, OnDestroy {
  constructor(
    private ngZone: NgZone,
    private deviceCapabilitiesService: DeviceCapabilitiesService,
    private voiceRecordingService: VoiceRecordingService,
    private fileHandlingService: FileHandlingService,
    private apiService: ApiService,
    private sanitizer: DomSanitizer,
    private dialog: MatDialog,
    private translate: TranslateService,
    private snackBar: MatSnackBar
  ) {}

  // ViewChild to access the textarea element directly
  @ViewChild('messageTextarea') private messageTextarea!: ElementRef<HTMLTextAreaElement>;
  @ViewChild('fileInput') private fileInput!: ElementRef<HTMLInputElement>;
  @ViewChild('cameraInput') private cameraInput!: ElementRef<HTMLInputElement>;
  @ViewChild('waveformCanvas') private waveformCanvas!: ElementRef<HTMLCanvasElement>;
  @ViewChild('composer') private composer!: ElementRef<HTMLElement>;

  // The message text bound to the textarea
  messageText: string = '';

  // File previews array - now with Input to receive files from parent
  @Input() set externalFiles(files: FilePreview[]) {
    if (files) {
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
  @Output() stopRequested = new EventEmitter<void>();
  @Output() generateRequested = new EventEmitter<void>();
  /** "Files of this chat" in the attach menu: offered for a conversation the server has. */
  @Input() canShowChatFiles = false;
  @Output() chatFilesRequested = new EventEmitter<void>();

  // Input property to track if AI is currently streaming
  @Input() isStreaming: boolean = false;

  // Manual editing: the newest message is the user's and has no answer, so an empty field offers Generate
  @Input() canGenerate: boolean = false;
  /** Generate would follow an answer: the model goes on from it (another label, the same button). */
  @Input() generateContinues = false;

  // Manual editing: about how many input tokens the next answer sends (null hides the indicator)
  @Input() contextSize: IContextSize | null = null;

  // Device capability flags
  hasCamera: boolean = false;
  hasGeolocation: boolean = false;

  // Voice recording properties
  isRecording: boolean = false;
  recordingTime: Date = new Date(0);
  isHoldToRecord: boolean = true; // Toggle between hold-to-record and tap-to-record
  recordingDuration: number = 0; // Store duration in seconds

  // Track if we have content to show appropriate button
  get hasContent(): boolean {
    return this.messageText.trim().length > 0 || this.filePreviews.length > 0;
  }

  /**
   * A file is still on its way to the server: the message waits for it, since a message sent
   * before would go out without the file.
   */
  get uploading(): boolean {
    return this.filePreviews.some(preview => preview.uploadStatus === UploadStatus.UPLOADING);
  }

  /** Sent while a file was still uploading: the message goes out as soon as the file has arrived. */
  sendQueued = false;

  // Track created blob URLs for proper cleanup
  private downloadUrls: Map<string, SafeUrl> = new Map();
  private rawDownloadUrls: Map<string, string> = new Map();

  // Subscription to recording state
  private recordingStateSubscription: any;

  // Keeps the waveform canvas sized to the composer (a field, so removeEventListener gets the same function)
  private readonly onWindowResize = () => this.updateCanvasDimensions();

  /** Files are being dragged over the window: they can be dropped anywhere to attach them. */
  draggingFiles = false;
  private dragTimer: ReturnType<typeof setTimeout> | null = null;

  private static carriesFiles(event: DragEvent): boolean {
    return !!event.dataTransfer && Array.from(event.dataTransfer.types).includes('Files');
  }

  private setDragging(dragging: boolean): void {
    if (this.dragTimer) clearTimeout(this.dragTimer);
    this.dragTimer = null;
    if (dragging) {
      // "dragover" comes again and again while the files are over the window; once it stops
      // (they left it, or the drag was cancelled), the composer goes back to normal
      this.dragTimer = setTimeout(() => this.setDragging(false), 600);
    }
    if (dragging !== this.draggingFiles) {
      this.ngZone.run(() => this.draggingFiles = dragging);
    }
  }

  // Accepting the drop also keeps the browser from opening the file in place of the app
  private readonly onDragOver = (event: DragEvent) => {
    if (!ChatUiInputfieldComponent.carriesFiles(event)) return;
    event.preventDefault();
    event.dataTransfer!.dropEffect = 'copy';
    this.setDragging(true);
  };

  private readonly onDrop = (event: DragEvent) => {
    if (!ChatUiInputfieldComponent.carriesFiles(event)) return;
    event.preventDefault();
    const files = Array.from(event.dataTransfer?.files ?? []);
    this.setDragging(false);
    if (files.length) {
      this.ngZone.run(() => void this.addFiles(files));
    }
  };

  /** Files pasted into the message (a screenshot, a copied image) are attached. */
  onPaste(event: ClipboardEvent): void {
    const data = event.clipboardData;
    const files = Array.from(data?.files ?? []);
    // Text copied from an office program comes with a picture of itself: the text is what is meant
    if (!files.length || Array.from(data?.types ?? []).includes('text/plain')) {
      return;
    }
    event.preventDefault();
    void this.addFiles(files);
  }

  ngOnInit() {
    // Subscribe to device capabilities
    this.deviceCapabilitiesService.getCapabilities().subscribe(capabilities => {
      this.hasCamera = capabilities.hasCamera;
      this.hasGeolocation = capabilities.hasGeolocation;
      this.isMobile = this.isMobile || capabilities.isMobile; // Use input or detected value
    });

    // Subscribe to recording state
    this.recordingStateSubscription = this.voiceRecordingService.getRecordingState().subscribe(state => {
      const started = state.isRecording && !this.isRecording;
      const stopped = !state.isRecording && this.isRecording;
      this.isRecording = state.isRecording;
      this.recordingDuration = state.duration;

      // The composer changes its layout (and height) while recording: once that is rendered, fit the
      // waveform to it, and afterwards fit the textarea (it is re-created) to the text kept in it
      if (started) requestAnimationFrame(() => this.updateCanvasDimensions());
      if (stopped) requestAnimationFrame(() => this.adjustTextareaHeight());

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

    // Add resize listener for responsive canvas (it only touches the DOM, so no change detection needed)
    this.ngZone.runOutsideAngular(() => {
      window.addEventListener('resize', this.onWindowResize);
      // Files dropped anywhere on the window are attached ("dragover" fires constantly: no change detection)
      document.addEventListener('dragover', this.onDragOver);
      document.addEventListener('drop', this.onDrop);
    });
  }

  // Handle Enter key press - send on Enter, new line on Shift+Enter
  handleKeyPress(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      // On mobile devices, allow Enter to create new lines
      // since Shift+Enter is not available
      if (!this.isMobileDevice()) {
        event.preventDefault();
        this.sendMessage();
      }
      // On mobile, do nothing - let the default behavior create a new line
    }
  }

  // Adjust textarea height based on content
  onTextareaInput(): void {
    this.adjustTextareaHeight();
  }

  /**
   * Focus the message input textarea.
   * Called externally when a new conversation is created.
   */
  public focusInput(): void {
    // On touch screens focusing pops up the on-screen keyboard over the chat, so only focus where there is a mouse
    if (this.isTouchPrimary()) return;
    this.messageTextarea?.nativeElement.focus();
  }

  /** True when the main input is a finger (phones, tablets), not a mouse or trackpad. */
  private isTouchPrimary(): boolean {
    return typeof window.matchMedia === 'function'
      && window.matchMedia('(hover: none) and (pointer: coarse)').matches;
  }

  // Method to dynamically adjust the textarea height
  private adjustTextareaHeight(): void {
    const textarea = this.messageTextarea?.nativeElement;
    if (!textarea) return;  // Not rendered while recording

    // Reset height to auto to get the correct scrollHeight
    textarea.style.height = 'auto';

    // Grow with the text up to the stylesheet's max-height (smaller on phones), then scroll
    const maxHeight = parseFloat(getComputedStyle(textarea).maxHeight) || 240;
    textarea.style.height = Math.min(textarea.scrollHeight, maxHeight) + 'px';
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? 'auto' : 'hidden';
  }

  // Send the message
  sendMessage(): void {
    const trimmedMessage = this.messageText.trim();
    if (this.uploading) {
      this.sendQueued = true;
      return;
    }
    this.sendQueued = false;

    // Check if we have either text or files to send
    if (trimmedMessage || this.filePreviews.length > 0) {
      // Files alone are a message too
      this.messageSent.emit(trimmedMessage);

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
    console.log('Camera button clicked');

    // On mobile, use the hidden camera input
    if (this.isMobileDevice()) {
      // Use the cameraInput reference instead of creating a new element
      this.cameraInput.nativeElement.click();
    } else {
      // On desktop, show a simple camera preview
      this.showDesktopCamera();
    }
  }

  // Handle location sharing
  handleLocationClick(): void {
    this.locationRequested.emit();
    console.log('Location sharing requested');
  }

  // Handle file selection from input
  async handleFileSelection(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    input.value = '';  // The same file can be picked again
    await this.addFiles(files);
  }

  /** Attach files (picked, dropped on the window or pasted): they are uploaded right away. */
  async addFiles(fileArray: File[]): Promise<void> {
    if (fileArray.length > 0) {
      // Validate file sizes (10MB limit per file)
      const invalidFiles = fileArray.filter(file => !this.fileHandlingService.validateFileSize(file, 10));
      if (invalidFiles.length > 0) {
        this.snackBar.open(
          this.translate.instant('composer.fileTooLarge', { names: invalidFiles.map(file => file.name).join(', '), size: 10 }),
          this.translate.instant('filePreview.close'), { duration: 8000 });
      }

      // Create file previews for valid files
      const newPreviews = await this.fileHandlingService.createFilePreviews(fileArray, 10);

      // Add to existing previews with pending status
      this.filePreviews = [...this.filePreviews, ...newPreviews];
      await this.uploadFilesImmediately(newPreviews);
      this.filesSelected.emit(this.filePreviews);
      console.log('Files selected and uploaded:', this.filePreviews);
      if (this.sendQueued) {
        this.sendMessage();
      }
    }
  }

  // Remove a file preview
  removeFilePreview(fileId: string): void {
    // Find the file being removed
    const preview = this.filePreviews.find(fp => fp.id === fileId);
    if (preview && preview.file) {
      const key = `${preview.file.name}_${preview.file.size}_${preview.file.lastModified}`;

      // Revoke the download URL if it exists
      const rawUrl = this.rawDownloadUrls.get(key);
      if (rawUrl) {
        URL.revokeObjectURL(rawUrl);
        this.downloadUrls.delete(key);
        this.rawDownloadUrls.delete(key);
      }
    }

    this.filePreviews = this.filePreviews.filter(fp => fp.id !== fileId);
    this.sendQueued = false;
    this.filesSelected.emit(this.filePreviews);
  }

  // Clear all file previews
  clearFilePreviews(): void {
    // Revoke all download URLs
    this.rawDownloadUrls.forEach(url => URL.revokeObjectURL(url));
    this.downloadUrls.clear();
    this.rawDownloadUrls.clear();

    this.filePreviews = [];
    this.sendQueued = false;
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

  private async showDesktopCamera(): Promise<void> {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });

      // Create simple UI
      const container = document.createElement('div');
      container.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0,0,0,0.9);
      z-index: 9999;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
    `;

      const video = document.createElement('video');
      video.srcObject = stream;
      video.autoplay = true;
      video.style.cssText = `
      max-width: 80%;
      max-height: 60%;
      border-radius: 8px;
    `;

      const buttonContainer = document.createElement('div');
      buttonContainer.style.cssText = `
      margin-top: 20px;
      display: flex;
      gap: 10px;
    `;

      const captureBtn = this.createButton(this.translate.instant('composer.capturePhoto'), '#4CAF50');
      const cancelBtn = this.createButton(this.translate.instant('composer.cancel'), '#f44336');

      buttonContainer.appendChild(captureBtn);
      buttonContainer.appendChild(cancelBtn);
      container.appendChild(video);
      container.appendChild(buttonContainer);
      document.body.appendChild(container);

      // Wait for video to load
      await new Promise(resolve => video.onloadedmetadata = resolve);

      captureBtn.onclick = () => {
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext('2d')!.drawImage(video, 0, 0);

        canvas.toBlob(async (blob) => {
          if (blob) {
            const file = new File([blob], `photo-${Date.now()}.jpg`, { type: 'image/jpeg' });
            const filePreview = await FilePreviewUtil.createFromFile(file);
            this.filePreviews = [...this.filePreviews, filePreview];
            this.filesSelected.emit(this.filePreviews);
          }
          cleanup();
        }, 'image/jpeg', 0.9);
      };

      const cleanup = () => {
        stream.getTracks().forEach(track => track.stop());
        document.body.removeChild(container);
      };

      cancelBtn.onclick = cleanup;
      container.onclick = (e) => {
        if (e.target === container) cleanup();
      };

    } catch (error) {
      console.error('Camera error:', error);
      alert(this.translate.instant('composer.cameraError'));
    }
  }

  private createButton(text: string, color: string): HTMLButtonElement {
    const btn = document.createElement('button');
    btn.textContent = text;
    btn.style.cssText = `
    padding: 10px 20px;
    font-size: 16px;
    border: none;
    border-radius: 4px;
    background: ${color};
    color: white;
    cursor: pointer;
  `;
    return btn;
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
        maxDuration: 600, // 10 minutes maximum
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
          alert(this.translate.instant('composer.micDenied'));
        } else if (error.name === 'NotFoundError') {
          alert(this.translate.instant('composer.micNotFound'));
        } else {
          alert(this.translate.instant('composer.micError', { error: error.message }));
        }
      }
    }
  }

  // Stop recording and create audio file
  private async stopRecording(): Promise<void> {
    try {
      const result = await this.voiceRecordingService.stopRecording();

      if (result) {
        // Create file preview from recording result (now async to include base64)
        const filePreview = await this.fileHandlingService.createAudioFilePreview(result);

        // Set status to UPLOADING (not PENDING) for immediate display
        filePreview.uploadStatus = UploadStatus.UPLOADING;

        // Emit voice file immediately for instant display in chat
        // The message will show with "Transcribing..." indicator
        this.filesSelected.emit([filePreview]);

        // Upload in background - will update filePreview with fileId and transcript
        this.uploadVoiceMessageInBackground(filePreview);
      }
    } catch (error) {
      console.error('Error stopping recording:', error);
    }
  }

  // Upload voice message in background and notify when complete
  private async uploadVoiceMessageInBackground(filePreview: FilePreview): Promise<void> {
    try {
      // Check if backend is available
      const backendAvailable = await this.isBackendAvailable();

      if (!backendAvailable) {
        filePreview.uploadStatus = UploadStatus.PENDING;
        filePreview.error = 'Waiting for connection';
        console.log('Backend not available, voice message marked as pending');
        return;
      }

      // Upload the file
      const uploadResults = await this.apiService.uploadFiles([filePreview]);

      if (uploadResults.length > 0) {
        const result = uploadResults[0];
        filePreview.uploadStatus = UploadStatus.COMPLETED;
        filePreview.id = result.fileId;
        filePreview.error = undefined;

        // Store transcript for audio files
        if (result.transcript) {
          filePreview.transcript = result.transcript;
          console.log('Voice message transcribed:', filePreview.name, result.transcript.substring(0, 50) + '...');
        }
      }
    } catch (error) {
      console.error('Error uploading voice message:', error);
      filePreview.uploadStatus = UploadStatus.FAILED;
      filePreview.error = 'Upload failed';
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

  // Update canvas dimensions to match container. Written to the element directly rather than through
  // a template binding: the size is only known after the first render (NG0100 otherwise).
  private updateCanvasDimensions(): void {
    const canvas = this.waveformCanvas?.nativeElement;
    const container = this.composer?.nativeElement;
    if (!canvas || !container) return;

    const rect = container.getBoundingClientRect();
    const width = Math.floor(rect.width) || 800;
    const height = Math.floor(rect.height) || 80; // Defaults if not yet rendered
    // Setting the size clears the canvas, so only do it when it changes.
    // The visualizer (VoiceRecordingService) reads the canvas size on every frame.
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;
  }

  // Hold-to-record event handlers. Touch and mouse both work at any screen width; the mouse
  // events a browser emulates after a touch are ignored (lastTouchAt).
  private lastTouchAt = 0;

  private isEmulatedMouseEvent(): boolean {
    return Date.now() - this.lastTouchAt < 1000;
  }

  onMicTouchStart(event: TouchEvent): void {
    this.lastTouchAt = Date.now();
    if (this.isHoldToRecord) {
      event.preventDefault();
      this.beginRecording();
    }
  }

  onMicTouchEnd(event: TouchEvent): void {
    this.lastTouchAt = Date.now();
    if (this.isHoldToRecord && this.isRecording) {
      event.preventDefault();
      this.stopRecording();
    }
  }

  onMicMouseDown(event: MouseEvent): void {
    if (this.isHoldToRecord && !this.isEmulatedMouseEvent()) {
      event.preventDefault();
      this.beginRecording();
    }
  }

  onMicMouseUp(event: MouseEvent): void {
    if (this.isHoldToRecord && this.isRecording && !this.isEmulatedMouseEvent()) {
      event.preventDefault();
      this.stopRecording();
    }
  }

  onMicMouseLeave(event: MouseEvent): void {
    if (this.isHoldToRecord && this.isRecording && !this.isEmulatedMouseEvent()) {
      this.stopRecording();
    }
  }

  // Upload files immediately when selected
  private async uploadFilesImmediately(filePreviews: FilePreview[]): Promise<void> {
    // On their way from now on: the message isn't sent before they have arrived
    filePreviews.forEach(fp => fp.uploadStatus = UploadStatus.UPLOADING);

    // Check if backend is available
    const backendAvailable = await this.isBackendAvailable();

    if (!backendAvailable) {
      // Mark files as pending for offline upload
      filePreviews.forEach(fp => {
        fp.uploadStatus = UploadStatus.PENDING;
        fp.error = 'Waiting for connection';
      });
      console.log('Backend not available, files marked as pending');
      return;
    }

    // Upload files immediately
    for (const filePreview of filePreviews) {
      try {
        filePreview.uploadStatus = UploadStatus.UPLOADING;

        // Upload single file
        const uploadResults = await this.apiService.uploadFiles([filePreview]);

        // Update file with server-assigned ID and transcript (for audio)
        if (uploadResults.length > 0) {
          const result = uploadResults[0];
          filePreview.uploadStatus = UploadStatus.COMPLETED;
          filePreview.id = result.fileId;
          filePreview.error = undefined;

          // Store transcript for audio files
          if (result.transcript) {
            filePreview.transcript = result.transcript;
            console.log('Audio file transcribed:', filePreview.name);
          }
        }

        console.log('File uploaded successfully:', filePreview.name, filePreview.id);
      } catch (error) {
        console.error('Error uploading file:', filePreview.name, error);
        filePreview.uploadStatus = UploadStatus.FAILED;
        filePreview.error = 'Upload failed';
      }
    }
  }

  private async isBackendAvailable(): Promise<boolean> {
    try {
      // Simple check to see if backend is reachable
      // We'll use a lightweight endpoint check
      const response = await fetch(`${environment.apiUrl}/api/auth/me`, {
        method: 'GET',
        credentials: 'include'
      });
      return response.ok;
    } catch (error) {
      return false;
    }
  }

  onAttachmentClick(event: MouseEvent, preview: FilePreview): void {
    if (preview.type === 'image' && preview.preview) {
      event.preventDefault();
      this.openImagePopup(preview.preview);
    }
  }

  createDownloadUrl(file: File): SafeUrl {
    // Create unique key for this file
    const key = `${file.name}_${file.size}_${file.lastModified}`;

    // Return cached URL if exists
    if (this.downloadUrls.has(key)) {
      return this.downloadUrls.get(key)!;
    }

    // Create new URL and cache it
    const objectUrl = URL.createObjectURL(file);
    const safeUrl = this.sanitizer.bypassSecurityTrustUrl(objectUrl);

    // Store both raw and safe URLs
    this.downloadUrls.set(key, safeUrl);
    this.rawDownloadUrls.set(key, objectUrl);

    return safeUrl;
  }

  openImagePopup(imageUrl: string): void {
    // Get the file preview to extract more info
    const preview = this.filePreviews.find(fp => fp.preview === imageUrl);

    const dialogData: ImagePreviewDialogData = {
      imageUrl: imageUrl,
      fileName: preview?.name || 'Image',
      fileSize: preview?.sizeFormatted
    };

    this.dialog.open(ImagePreviewDialogComponent, {
      data: dialogData,
      panelClass: 'image-preview-dialog',
      maxWidth: '95vw',
      maxHeight: '95vh',
      hasBackdrop: true,
      backdropClass: 'image-preview-backdrop'
    });
  }

  // Clean up resources when component is destroyed
  ngOnDestroy(): void {
    // Remove resize listener
    window.removeEventListener('resize', this.onWindowResize);
    document.removeEventListener('dragover', this.onDragOver);
    document.removeEventListener('drop', this.onDrop);
    if (this.dragTimer) clearTimeout(this.dragTimer);

    // Unsubscribe from observables
    if (this.recordingStateSubscription) {
      this.recordingStateSubscription.unsubscribe();
    }

    // Stop any ongoing recording
    if (this.isRecording) {
      this.voiceRecordingService.cancelRecording();
    }

    // Revoke all download URLs
    this.rawDownloadUrls.forEach(url => URL.revokeObjectURL(url));
    this.downloadUrls.clear();
    this.rawDownloadUrls.clear();

    // Revoke any preview URLs to free memory
    this.filePreviews.forEach(preview => {
      if (preview.preview && preview.preview.startsWith('blob:')) {
        URL.revokeObjectURL(preview.preview);
      }
    });
  }
}
