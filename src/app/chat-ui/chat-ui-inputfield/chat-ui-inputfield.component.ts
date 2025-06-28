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
  waveformData: Array<{x: number, height: number}> = [];
  isHoldToRecord: boolean = true; // Toggle between hold-to-record and tap-to-record
  recordingDuration: number = 0; // Store duration in seconds

  // Audio recording properties
  mediaRecorder: MediaRecorder | null = null;
  audioStream: MediaStream | null = null;
  audioChunks: Blob[] = [];
  audioContext: AudioContext | null = null;
  analyser: AnalyserNode | null = null;
  dataArray: Uint8Array | null = null;

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

  // Set up audio analysis for real waveform
  private setupAudioAnalysis(stream: MediaStream): void {
    try {
      // Create audio context
      this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      console.log('AudioContext created, state:', this.audioContext.state);

      // Create analyser node
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 2048; // Increased for better resolution
      this.analyser.smoothingTimeConstant = 0.8; // Smooth out rapid changes

      // Create data array for time domain data
      const bufferLength = this.analyser.fftSize;
      this.dataArray = new Uint8Array(bufferLength);

      // Connect stream to analyser
      const source = this.audioContext.createMediaStreamSource(stream);
      source.connect(this.analyser);
      // Note: We don't connect to destination to avoid feedback

      console.log('Audio analysis setup complete');
      console.log('Analyser fftSize:', this.analyser.fftSize);
      console.log('Data array length:', this.dataArray.length);

      // Test if we're getting data
      setTimeout(() => {
        if (this.analyser && this.dataArray) {
          this.analyser.getByteTimeDomainData(this.dataArray);
          const hasSound = this.dataArray.some(value => Math.abs(value - 128) > 5);
          console.log('Audio test - has sound:', hasSound);
        }
      }, 500);
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

      // Start the waveform animation
      this.startWaveformAnimation();

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

    // Stop animation
    if (this.waveformAnimationId) {
      cancelAnimationFrame(this.waveformAnimationId);
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
    this.waveformData = [];
    this.mediaRecorder = null;
    this.audioStream = null;
    this.audioContext = null;
    this.analyser = null;
    this.dataArray = null;

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

    // Stop animation
    if (this.waveformAnimationId) {
      cancelAnimationFrame(this.waveformAnimationId);
    }

    // Reset everything
    this.recordingTime = new Date(0);
    this.waveformData = [];
    this.audioChunks = [];
    this.mediaRecorder = null;
    this.audioStream = null;
    this.audioContext = null;
    this.analyser = null;
    this.dataArray = null;

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

  // Optional: Add these helper methods for additional visual effects
  private drawSmoothWaveformWithFill(): void {
    // Alternative implementation with filled waveform (like SoundCloud style)
    // This can be called instead of the line-based waveform for a different look

    const canvas = this.waveformCanvas.nativeElement;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const centerY = canvas.height / 2;

    // Create gradient fill
    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
    gradient.addColorStop(0, 'rgba(76, 165, 220, 0.8)');
    gradient.addColorStop(0.5, 'rgba(76, 165, 220, 0.4)');
    gradient.addColorStop(1, 'rgba(76, 165, 220, 0.8)');

    ctx.fillStyle = gradient;

    // Draw filled waveform
    ctx.beginPath();
    ctx.moveTo(0, centerY);

    // Top edge
    for (let i = 0; i < this.waveformData.length; i++) {
      const x = i * 2;
      const amplitude = this.waveformData[i] * (canvas.height / 2 - 5);
      const y = centerY - amplitude;

      if (i === 0) {
        ctx.lineTo(x, y);
      } else {
        const prevX = (i - 1) * 2;
        const prevY = centerY - this.waveformData[i - 1] * (canvas.height / 2 - 5);
        const cpX = (prevX + x) / 2;
        const cpY = (prevY + y) / 2;
        ctx.quadraticCurveTo(prevX, prevY, cpX, cpY);
      }
    }

    // Bottom edge (mirrored)
    for (let i = this.waveformData.length - 1; i >= 0; i--) {
      const x = i * 2;
      const amplitude = this.waveformData[i] * (canvas.height / 2 - 5);
      const y = centerY + amplitude;

      if (i === this.waveformData.length - 1) {
        ctx.lineTo(x, y);
      } else {
        const nextX = (i + 1) * 2;
        const nextY = centerY + this.waveformData[i + 1] * (canvas.height / 2 - 5);
        const cpX = (nextX + x) / 2;
        const cpY = (nextY + y) / 2;
        ctx.quadraticCurveTo(nextX, nextY, cpX, cpY);
      }
    }

    ctx.closePath();
    ctx.fill();
  }

  // Start waveform animation
  private startWaveformAnimation(): void {
    // Wait for canvas to be ready
    setTimeout(() => {
      if (!this.waveformCanvas || !this.waveformCanvas.nativeElement) {
        console.error('Canvas not ready');
        return;
      }

      const canvas = this.waveformCanvas.nativeElement;
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        console.error('Could not get canvas context');
        return;
      }

      // Waveform configuration
      const config = {
        // Visual settings
        lineWidth: 2,
        primaryColor: '#4CA5DC',
        secondaryColor: '#66c2ff',
        glowColor: 'rgba(76, 165, 220, 0.3)',
        backgroundColor: 'rgba(255, 255, 255, 0.02)',

        // Waveform behavior
        samplesPerSecond: 60, // How many points to capture per second
        scrollSpeed: 1, // Pixels per frame
        smoothingFactor: 0.8, // How much to smooth between samples (0-1)
        amplitudeScale: 0.9, // Scale factor for amplitude (0-1)

        // Advanced effects
        enableGlow: true,
        enableGradient: true,
        enableMirror: true, // Mirror waveform for symmetrical look
      };

      // Waveform data storage
      const waveformData: number[] = [];
      const maxSamples = Math.floor(canvas.width / 2); // Store enough samples to fill the canvas

      // Smoothing variables
      let smoothedAmplitude = 0;
      let targetAmplitude = 0;

      // Animation variables
      let lastSampleTime = Date.now();
      const sampleInterval = 1000 / config.samplesPerSecond;

      // Clear and prepare canvas
      const prepareCanvas = () => {
        ctx.fillStyle = config.backgroundColor;
        ctx.fillRect(0, 0, canvas.width, canvas.height);
      };

      // Calculate amplitude from audio data
      const getAudioLevel = (): number => {
        if (!this.analyser || !this.dataArray) return 0;

        this.analyser.getByteTimeDomainData(this.dataArray);

        // Calculate RMS (Root Mean Square) for a more accurate representation
        let sum = 0;
        let max = 0;

        for (let i = 0; i < this.dataArray.length; i++) {
          const normalized = (this.dataArray[i] - 128) / 128; // Normalize to -1 to 1
          sum += normalized * normalized;
          max = Math.max(max, Math.abs(normalized));
        }

        const rms = Math.sqrt(sum / this.dataArray.length);

        // Use a combination of RMS and peak for better visual response
        const level = (rms * 0.7 + max * 0.3) * config.amplitudeScale;

        return Math.min(1, level * 3); // Scale up and cap at 1
      };

      // Draw smooth waveform using bezier curves
      const drawWaveform = () => {
        // Clear canvas with slight fade for trailing effect
        ctx.fillStyle = 'rgba(255, 255, 255, 0.05)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        if (waveformData.length < 2) return;

        const centerY = canvas.height / 2;

        // Set up glow effect if enabled
        if (config.enableGlow) {
          ctx.shadowColor = config.glowColor;
          ctx.shadowBlur = 10;
        }

        // Create gradient if enabled
        if (config.enableGradient) {
          const gradient = ctx.createLinearGradient(0, 0, canvas.width, 0);
          gradient.addColorStop(0, 'rgba(76, 165, 220, 0.1)');
          gradient.addColorStop(0.5, config.primaryColor);
          gradient.addColorStop(1, config.secondaryColor);
          ctx.strokeStyle = gradient;
        } else {
          ctx.strokeStyle = config.primaryColor;
        }

        ctx.lineWidth = config.lineWidth;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';

        // Draw upper waveform
        ctx.beginPath();

        for (let i = 0; i < waveformData.length; i++) {
          const x = i * 2; // Space between points
          const amplitude = waveformData[i] * (canvas.height / 2 - 5); // Leave some margin
          const y = centerY - amplitude;

          if (i === 0) {
            ctx.moveTo(x, y);
          } else {
            // Use quadratic bezier curves for smooth connections
            const prevX = (i - 1) * 2;
            const prevY = centerY - waveformData[i - 1] * (canvas.height / 2 - 5);
            const cpX = (prevX + x) / 2;
            const cpY = (prevY + y) / 2;

            ctx.quadraticCurveTo(prevX, prevY, cpX, cpY);
          }
        }

        // Extend to the current edge
        const lastX = (waveformData.length - 1) * 2;
        const lastY = centerY - waveformData[waveformData.length - 1] * (canvas.height / 2 - 5);
        ctx.lineTo(lastX + 2, lastY);

        ctx.stroke();

        // Draw mirrored lower waveform if enabled
        if (config.enableMirror) {
          ctx.beginPath();

          for (let i = 0; i < waveformData.length; i++) {
            const x = i * 2;
            const amplitude = waveformData[i] * (canvas.height / 2 - 5);
            const y = centerY + amplitude;

            if (i === 0) {
              ctx.moveTo(x, y);
            } else {
              const prevX = (i - 1) * 2;
              const prevY = centerY + waveformData[i - 1] * (canvas.height / 2 - 5);
              const cpX = (prevX + x) / 2;
              const cpY = (prevY + y) / 2;

              ctx.quadraticCurveTo(prevX, prevY, cpX, cpY);
            }
          }

          ctx.stroke();
        }

        // Draw center line
        ctx.strokeStyle = 'rgba(76, 165, 220, 0.2)';
        ctx.lineWidth = 1;
        ctx.shadowBlur = 0;
        ctx.beginPath();
        ctx.moveTo(0, centerY);
        ctx.lineTo(canvas.width, centerY);
        ctx.stroke();

        // Draw "live" indicator on the right edge
        const liveX = Math.min(waveformData.length * 2 + 10, canvas.width - 10);
        ctx.fillStyle = config.secondaryColor;
        ctx.shadowColor = config.secondaryColor;
        ctx.shadowBlur = 10;
        ctx.beginPath();
        ctx.arc(liveX, centerY, 3, 0, Math.PI * 2);
        ctx.fill();
      };

      // Main animation loop
      const animate = () => {
        const now = Date.now();

        // Sample audio at regular intervals
        if (now - lastSampleTime >= sampleInterval) {
          targetAmplitude = getAudioLevel();
          lastSampleTime = now;
        }

        // Smooth the amplitude changes
        smoothedAmplitude += (targetAmplitude - smoothedAmplitude) * config.smoothingFactor;

        // Add new sample
        waveformData.push(smoothedAmplitude);

        // Remove old samples that have scrolled off screen
        while (waveformData.length > maxSamples) {
          waveformData.shift();
        }

        // Draw the waveform
        drawWaveform();

        // Continue animation if still recording
        if (this.isRecording) {
          this.waveformAnimationId = requestAnimationFrame(animate);
        } else {
          // Cleanup
          ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
      };

      // Start the animation
      prepareCanvas();
      animate();

    }, 100); // Give canvas time to initialize
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
