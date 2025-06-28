import { Component, EventEmitter, Output, ViewChild, ElementRef, AfterViewInit, OnInit, OnDestroy, Input, NgZone } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { FilePreview, FilePreviewUtil, FileType, UploadStatus } from '../../data/objects/file-preview';

// Time-based bar visualization interfaces and classes
interface VisualizationBar {
  height: number;      // 1-100 normalized value
  timestamp: number;   // When bar was created
  x: number;           // Current x position
}

class TimeBasedBarVisualizer {
  private bars: VisualizationBar[] = [];
  private lastBarTime = 0;
  private readonly BAR_INTERVAL = 500; // 0.5 seconds
  private readonly BAR_WIDTH = 8;
  private readonly BAR_GAP = 2;
  private readonly SCROLL_SPEED = 20; // pixels per second

  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private animationId: number | null = null;
  private lastAnimationTime = 0;
  private audioLevelCallback: () => number;
  private renderer: OptimizedCanvasRenderer;

  constructor(canvas: HTMLCanvasElement, audioLevelCallback: () => number) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d', { alpha: false })!; // Disable alpha for performance
    this.audioLevelCallback = audioLevelCallback;
    this.renderer = new OptimizedCanvasRenderer(canvas, this.BAR_WIDTH, this.BAR_GAP);
  }

  start(): void {
    this.lastAnimationTime = performance.now();
    this.lastBarTime = this.lastAnimationTime;
    this.animationId = requestAnimationFrame(this.animate);
  }

  stop(): void {
    if (this.animationId !== null) {
      cancelAnimationFrame(this.animationId);
      this.animationId = null;
    }
    this.bars = [];
  }

  private animate = (currentTime: number): void => {
    const deltaTime = currentTime - this.lastAnimationTime;
    this.lastAnimationTime = currentTime;

    // Add new bar every 0.5 seconds
    if (currentTime - this.lastBarTime >= this.BAR_INTERVAL) {
      const audioLevel = this.audioLevelCallback();
      this.addNewBar(audioLevel);
      this.lastBarTime = currentTime;
    }

    // Update bar positions (scroll left)
    this.updateBarPositions(deltaTime);

    // Render frame
    this.renderer.renderFrame(this.bars);

    this.animationId = requestAnimationFrame(this.animate);
  };

  private addNewBar(height: number): void {
    this.bars.push({
      height,
      timestamp: Date.now(),
      x: this.canvas.width - this.BAR_WIDTH
    });
  }

  private updateBarPositions(deltaTime: number): void {
    const scrollDistance = (this.SCROLL_SPEED * deltaTime) / 1000;

    // Update positions and remove off-screen bars
    this.bars = this.bars.filter(bar => {
      bar.x -= scrollDistance;
      return bar.x > -this.BAR_WIDTH; // Keep bars until fully off-screen
    });
  }
}

class VoiceAudioProcessor {
  private analyser: AnalyserNode;
  private timeDomainData: Uint8Array;
  private smoother: AudioLevelSmoother;

  constructor(audioContext: AudioContext, analyserNode: AnalyserNode) {
    this.analyser = analyserNode;
    this.analyser.fftSize = 2048;
    this.analyser.smoothingTimeConstant = 0.3; // Light smoothing for voice

    this.timeDomainData = new Uint8Array(this.analyser.fftSize);
    this.smoother = new AudioLevelSmoother();
  }

  getVoiceLevel(): number {
    // Use time domain for accurate voice levels
    this.analyser.getByteTimeDomainData(this.timeDomainData);

    // Calculate RMS
    let sum = 0;
    for (let i = 0; i < this.timeDomainData.length; i++) {
      const sample = (this.timeDomainData[i] - 128) / 128; // Normalize to -1 to 1
      sum += sample * sample;
    }
    const rms = Math.sqrt(sum / this.timeDomainData.length);

    // Convert to decibels
    const db = 20 * Math.log10(Math.max(rms, 0.0001)); // Avoid log(0)

    // Normalize for voice (your specified mapping)
    const normalized = this.normalizeVoiceLevel(db);

    // Apply smoothing to prevent jumpy bars
    return this.smoother.smooth(normalized);
  }

  private normalizeVoiceLevel(db: number): number {
    // Voice-specific thresholds
    const SILENCE_DB = -60;    // Maps to 1
    const QUIET_DB = -40;      // Maps to 20
    const NORMAL_DB = -25;     // Maps to 40
    const LOUD_DB = -15;       // Maps to 60
    const VERY_LOUD_DB = -5;   // Maps to 80
    const MAX_DB = 0;          // Maps to 100

    if (db <= SILENCE_DB) return 1;
    if (db <= QUIET_DB) return this.lerp(1, 20, (db - SILENCE_DB) / (QUIET_DB - SILENCE_DB));
    if (db <= NORMAL_DB) return this.lerp(20, 40, (db - QUIET_DB) / (NORMAL_DB - QUIET_DB));
    if (db <= LOUD_DB) return this.lerp(40, 60, (db - NORMAL_DB) / (LOUD_DB - NORMAL_DB));
    if (db <= VERY_LOUD_DB) return this.lerp(60, 80, (db - LOUD_DB) / (VERY_LOUD_DB - LOUD_DB));
    return this.lerp(80, 100, Math.min(1, (db - VERY_LOUD_DB) / (MAX_DB - VERY_LOUD_DB)));
  }

  private lerp(a: number, b: number, t: number): number {
    return a + (b - a) * Math.max(0, Math.min(1, t));
  }
}

// Smoothing algorithm optimized for voice
class AudioLevelSmoother {
  private currentLevel = 0;
  private readonly ATTACK = 0.8;   // Fast response to speech onset
  private readonly RELEASE = 0.15; // Slower decay for natural look

  smooth(inputLevel: number): number {
    if (inputLevel > this.currentLevel) {
      // Attack phase - quick rise for speech onset
      this.currentLevel = this.ATTACK * inputLevel + (1 - this.ATTACK) * this.currentLevel;
    } else {
      // Release phase - slower fall
      this.currentLevel = this.RELEASE * inputLevel + (1 - this.RELEASE) * this.currentLevel;
    }
    return Math.round(this.currentLevel); // Round for consistent bar heights
  }
}

class OptimizedCanvasRenderer {
  private offscreenCanvas: HTMLCanvasElement;
  private offscreenCtx: CanvasRenderingContext2D;
  private ctx: CanvasRenderingContext2D;
  private readonly BAR_WIDTH: number;
  private readonly BAR_GAP: number;

  constructor(private canvas: HTMLCanvasElement, barWidth: number, barGap: number) {
    // Disable alpha channel for better performance
    this.ctx = canvas.getContext('2d', {
      alpha: false,
      desynchronized: true // Hint for better performance
    })!;

    this.BAR_WIDTH = barWidth;
    this.BAR_GAP = barGap;

    // Create offscreen canvas for bar pre-rendering
    this.offscreenCanvas = document.createElement('canvas');
    this.offscreenCanvas.width = this.BAR_WIDTH;
    this.offscreenCanvas.height = canvas.height;
    this.offscreenCtx = this.offscreenCanvas.getContext('2d')!;

    // Pre-render gradient bar for reuse
    this.preRenderBar();
  }

  private preRenderBar(): void {
    const gradient = this.offscreenCtx.createLinearGradient(0, 0, 0, this.canvas.height);
    gradient.addColorStop(0, '#4CA5DC');
    gradient.addColorStop(1, '#357BA6'); // Slight gradient for depth
    this.offscreenCtx.fillStyle = gradient;
    this.offscreenCtx.fillRect(0, 0, this.BAR_WIDTH, this.canvas.height);
  }

  renderFrame(bars: VisualizationBar[]): void {
    // Clear with solid color (faster than clearRect)
    this.ctx.fillStyle = '#000000';
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    // Only render visible bars
    const visibleBars = bars.filter(bar =>
      bar.x > -this.BAR_WIDTH && bar.x < this.canvas.width
    );

    // Batch similar operations
    visibleBars.forEach(bar => {
      const barHeight = (bar.height / 100) * this.canvas.height;
      const y = this.canvas.height - barHeight;

      // Use integer coordinates to avoid sub-pixel rendering
      const x = Math.floor(bar.x);
      const height = Math.ceil(barHeight);

      // Draw pre-rendered bar with clipping
      this.ctx.drawImage(
        this.offscreenCanvas,
        0, 0, this.BAR_WIDTH, height,
        x, y, this.BAR_WIDTH, height
      );
    });
  }
}


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
  constructor(private ngZone: NgZone) {}
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
  waveformWidth: number = 200;
  isHoldToRecord: boolean = true; // Toggle between hold-to-record and tap-to-record
  recordingDuration: number = 0; // Store duration in seconds

  // Audio recording properties
  mediaRecorder: MediaRecorder | null = null;
  audioStream: MediaStream | null = null;
  audioChunks: Blob[] = [];
  audioContext: AudioContext | null = null;
  analyser: AnalyserNode | null = null;

  // Time-based bar visualization properties
  barVisualizer: TimeBasedBarVisualizer | null = null;
  audioProcessor: VoiceAudioProcessor | null = null;

  // Property for backward compatibility
  private waveformAnimationId: number | null = null;

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

          // Also check for audio input devices
          const hasAudio = devices.some(device => device.kind === 'audioinput');
          if (!hasAudio) {
            console.warn('No audio input devices found');
          }
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

  // Get supported MIME type for recording
  private getSupportedMimeType(): string {
    const types = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/ogg',
      'audio/mp4',
      'audio/mpeg'
    ];

    for (const type of types) {
      if (MediaRecorder.isTypeSupported(type)) {
        console.log('Using MIME type:', type);
        return type;
      }
    }

    // Fallback to empty string (browser default)
    console.log('Using browser default MIME type');
    return '';
  }

  // Set up audio analysis for time-based bar visualization
  private setupAudioAnalysis(stream: MediaStream): void {
    try {
      // Create audio context
      this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      console.log('AudioContext created, state:', this.audioContext.state);

      // Create analyser node
      this.analyser = this.audioContext.createAnalyser();

      // Connect stream to analyser
      const source = this.audioContext.createMediaStreamSource(stream);
      source.connect(this.analyser);
      // Note: We don't connect to destination to avoid feedback

      // Create audio processor for voice level calculation
      this.audioProcessor = new VoiceAudioProcessor(this.audioContext, this.analyser);

      // Create bar visualizer
      if (this.waveformCanvas && this.waveformCanvas.nativeElement) {
        // Run visualization outside Angular zone for better performance
        this.ngZone.runOutsideAngular(() => {
          this.barVisualizer = new TimeBasedBarVisualizer(
            this.waveformCanvas.nativeElement,
            () => this.audioProcessor?.getVoiceLevel() || 0
          );

          // Start the visualization
          this.barVisualizer.start();
        });
      }

      console.log('Audio analysis setup complete');
    } catch (error) {
      console.error('Error setting up audio analysis:', error);
    }
  }

  // Begin the recording process
  private async beginRecording(): Promise<void> {
    try {
      // Request microphone access
      this.audioStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      // Set recording state first to show UI
      this.isRecording = true;
      this.recordingStartTime = Date.now();
      this.recordingDuration = 0;

      // Update canvas width and wait for it to render
      this.updateWaveformWidth();
      await new Promise(resolve => setTimeout(resolve, 50));

      // Set up MediaRecorder
      const mimeType = this.getSupportedMimeType();
      this.mediaRecorder = new MediaRecorder(this.audioStream, { mimeType });
      this.audioChunks = [];

      // Set up audio analysis for waveform
      this.setupAudioAnalysis(this.audioStream);

      // Handle data available event
      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };

      // Handle recording stop
      this.mediaRecorder.onstop = () => {
        console.log('MediaRecorder stopped');
      };

      // Start recording
      this.mediaRecorder.start(100); // Collect data every 100ms

      // Start the timer
      this.recordingTimer = setInterval(() => {
        const elapsed = Date.now() - this.recordingStartTime;
        this.recordingTime = new Date(elapsed);
        this.recordingDuration = Math.floor(elapsed / 1000);
      }, 100);

      // Visualization is started in setupAudioAnalysis

      console.log('Voice recording started with real audio');
    } catch (error) {
      console.error('Error accessing microphone:', error);
      this.isRecording = false;

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
    if (!this.isRecording || !this.mediaRecorder) return;

    this.isRecording = false;

    // Stop the MediaRecorder
    this.mediaRecorder.stop();

    // Stop all audio tracks
    if (this.audioStream) {
      this.audioStream.getTracks().forEach(track => track.stop());
    }

    // Close audio context
    if (this.audioContext) {
      this.audioContext.close();
    }

    // Stop timers
    if (this.recordingTimer) {
      clearInterval(this.recordingTimer);
    }

    // Stop the bar visualization
    if (this.barVisualizer) {
      this.barVisualizer.stop();
    }

    // Wait a bit for the last data chunk
    await new Promise(resolve => setTimeout(resolve, 100));

    // Create audio file from chunks
    if (this.audioChunks.length > 0) {
      const audioBlob = new Blob(this.audioChunks, {
        type: this.mediaRecorder.mimeType || 'audio/webm'
      });
      await this.createAudioFilePreview(audioBlob);
    }

    // Reset
    this.recordingTime = new Date(0);
    this.mediaRecorder = null;
    this.audioStream = null;
    this.audioContext = null;
    this.analyser = null;
    this.audioProcessor = null;
    this.barVisualizer = null;

    console.log('Voice recording stopped');
  }

  // Cancel recording without saving
  cancelRecording(): void {
    this.isRecording = false;

    // Stop the MediaRecorder if it exists
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }

    // Stop all audio tracks
    if (this.audioStream) {
      this.audioStream.getTracks().forEach(track => track.stop());
    }

    // Close audio context
    if (this.audioContext) {
      this.audioContext.close();
    }

    // Stop timers
    if (this.recordingTimer) {
      clearInterval(this.recordingTimer);
    }

    // Stop the bar visualization
    if (this.barVisualizer) {
      this.barVisualizer.stop();
    }

    // Reset everything
    this.recordingTime = new Date(0);
    this.audioChunks = [];
    this.mediaRecorder = null;
    this.audioStream = null;
    this.audioContext = null;
    this.analyser = null;
    this.audioProcessor = null;
    this.barVisualizer = null;

    console.log('Voice recording cancelled');
  }

  // Send the voice message
  async sendVoiceMessage(): Promise<void> {
    await this.stopRecording();
  }

  // Create audio file preview
  private async createAudioFilePreview(audioBlob: Blob): Promise<void> {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const duration = this.formatDuration(this.recordingDuration);
    const extension = this.getFileExtension(audioBlob.type);
    const fileName = `voice-message-${timestamp}.${extension}`;

    // Create a File object from the blob
    const audioFile = new File([audioBlob], fileName, {
      type: audioBlob.type,
      lastModified: Date.now()
    });

    // Create FilePreview
    const filePreview: FilePreview = {
      id: FilePreviewUtil.generateId(),
      file: audioFile,
      name: `Voice message (${duration})`,
      size: audioFile.size,
      sizeFormatted: FilePreviewUtil.formatFileSize(audioFile.size),
      type: FileType.AUDIO,
      mimeType: audioFile.type,
      uploadStatus: UploadStatus.PENDING
    };

    // Add to file previews
    this.filePreviews = [...this.filePreviews, filePreview];
    this.filesSelected.emit(this.filePreviews);

    console.log('Audio file created:', filePreview);
  }

  // Get file extension from MIME type
  private getFileExtension(mimeType: string): string {
    const typeMap: { [key: string]: string } = {
      'audio/webm': 'webm',
      'audio/ogg': 'ogg',
      'audio/mp4': 'm4a',
      'audio/mpeg': 'mp3',
      'audio/wav': 'wav'
    };

    return typeMap[mimeType.split(';')[0]] || 'webm';
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

  // The time-based bar visualization has replaced these methods
  private drawSmoothWaveformWithFill(): void {
    // This method is kept as a stub for backward compatibility
    // The actual visualization is now handled by TimeBasedBarVisualizer
    console.log('drawSmoothWaveformWithFill is deprecated, using TimeBasedBarVisualizer instead');
  }

  // Start waveform animation - replaced by TimeBasedBarVisualizer
  private startWaveformAnimation(): void {
    // This method is completely replaced with a stub
    // The actual visualization is now handled by TimeBasedBarVisualizer
    console.log('startWaveformAnimation is deprecated, using TimeBasedBarVisualizer instead');

    // No implementation needed as this method is no longer used
    // All functionality has been moved to the TimeBasedBarVisualizer class
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

    // Clean up audio resources
    if (this.audioStream) {
      this.audioStream.getTracks().forEach(track => track.stop());
    }
    if (this.audioContext && this.audioContext.state !== 'closed') {
      this.audioContext.close();
    }

    // Revoke any object URLs to free memory
    this.filePreviews.forEach(preview => {
      if (preview.preview && preview.preview.startsWith('blob:')) {
        URL.revokeObjectURL(preview.preview);
      }
    });
  }
}
