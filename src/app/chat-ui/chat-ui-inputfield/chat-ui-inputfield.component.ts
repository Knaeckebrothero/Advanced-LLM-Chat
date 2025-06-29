import { Component, EventEmitter, Output, ViewChild, ElementRef, AfterViewInit, OnInit, OnDestroy, Input, NgZone } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatChipsModule } from '@angular/material/chips';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { DomSanitizer, SafeUrl } from '@angular/platform-browser';
import { FilePreview, FileType } from '../../data/objects/file-preview';
import { DeviceCapabilitiesService } from '../services/device-capabilities.service';
import { VoiceRecordingService } from './voice-recording.service';
import { FileHandlingService } from '../services/file-handling.service';
import { RecordingConfig } from '../../data/objects/recording';
import { Subscription } from 'rxjs';


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
    private sanitizer: DomSanitizer,
    private deviceCapabilitiesService: DeviceCapabilitiesService,
    private voiceRecordingService: VoiceRecordingService,
    private fileHandlingService: FileHandlingService
  ) {}

  @ViewChild('messageTextarea') private messageTextarea!: ElementRef<HTMLTextAreaElement>;
  @ViewChild('fileInput') private fileInput!: ElementRef<HTMLInputElement>;
  @ViewChild('cameraInput') private cameraInput!: ElementRef<HTMLInputElement>;
  @ViewChild('waveformCanvas') private waveformCanvas!: ElementRef<HTMLCanvasElement>;

  messageText: string = '';

  @Input() set externalFiles(files: FilePreview[]) {
    if (files && files.length > 0) {
      this.filePreviews = [...files];
    }
  }

  @Input() isMobile: boolean = false;

  filePreviews: FilePreview[] = [];

  @Output() messageSent = new EventEmitter<string>();
  @Output() audioRequested = new EventEmitter<void>();
  @Output() filesSelected = new EventEmitter<FilePreview[]>();
  @Output() cameraRequested = new EventEmitter<void>();
  @Output() locationRequested = new EventEmitter<void>();

  hasCamera: boolean = false;
  hasGeolocation: boolean = false;

  isRecording: boolean = false;
  recordingTime: Date = new Date(0);
  canvasWidth: number = 800;
  canvasHeight: number = 80;
  isHoldToRecord: boolean = true;
  recordingDuration: number = 0;

  get hasContent(): boolean {
    return this.messageText.trim().length > 0 || this.filePreviews.length > 0;
  }

  private recordingStateSubscription!: Subscription;

  ngOnInit() {
    this.deviceCapabilitiesService.getCapabilities().subscribe(capabilities => {
      this.hasCamera = capabilities.hasCamera;
      this.hasGeolocation = capabilities.hasGeolocation;
      this.isMobile = this.isMobile || capabilities.isMobile;
    });

    this.recordingStateSubscription = this.voiceRecordingService.getRecordingState().subscribe(state => {
      this.isRecording = state.isRecording;
      this.recordingDuration = state.duration;

      if (state.isRecording) {
        this.recordingTime = new Date(state.duration * 1000);
      } else {
        this.recordingTime = new Date(0);
      }
    });
  }

  ngAfterViewInit() {
    this.adjustTextareaHeight();
    this.updateCanvasDimensions();
    window.addEventListener('resize', () => this.updateCanvasDimensions());
  }

  handleKeyPress(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  onTextareaInput(): void {
    this.adjustTextareaHeight();
  }

  private adjustTextareaHeight(): void {
    const textarea = this.messageTextarea.nativeElement;
    textarea.style.height = 'auto';
    const newHeight = Math.min(textarea.scrollHeight, 150);
    textarea.style.height = newHeight + 'px';
  }

  sendMessage(): void {
    const trimmedMessage = this.messageText.trim();
    if (trimmedMessage || this.filePreviews.length > 0) {
      this.messageSent.emit(trimmedMessage);
      this.messageText = '';
      this.clearFilePreviews();
      setTimeout(() => this.adjustTextareaHeight(), 0);
    }
  }

  handleFileMenuClick(action: 'file' | 'camera' | 'location'): void {
    switch(action) {
      case 'file':
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

  handleCameraClick(): void {
    if (this.isMobileDevice()) {
      this.cameraInput.nativeElement.click();
    } else {
      this.showDesktopCamera();
    }
  }

  handleLocationClick(): void {
    this.locationRequested.emit();
  }

  async handleFileSelection(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const files = input.files;
    if (files && files.length > 0) {
      const newPreviews = await this.fileHandlingService.createFilePreviews(Array.from(files));
      this.filePreviews.push(...newPreviews);
      this.filesSelected.emit(this.filePreviews);
    }
    input.value = ''; // Clear input for next selection
  }

  removeFilePreview(fileId: string): void {
    const previewToRemove = this.filePreviews.find(fp => fp.id === fileId);
    if (previewToRemove?.preview) {
      // Since preview is a string (data URL), there's no blob to revoke.
    }
    this.filePreviews = this.filePreviews.filter(fp => fp.id !== fileId);
    this.filesSelected.emit(this.filePreviews);
  }

  clearFilePreviews(): void {
    this.filePreviews = [];
    this.filesSelected.emit(this.filePreviews);
  }

  getFileIcon(type: FileType): string {
    return this.fileHandlingService.getFileIcon(type);
  }

  isMobileDevice(): boolean {
    return this.isMobile;
  }

  private async showDesktopCamera(): Promise<void> {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      const container = document.createElement('div');
      container.style.cssText = `...`; // Styling omitted for brevity
      const video = document.createElement('video');
      video.srcObject = stream;
      video.autoplay = true;
      // ... more UI creation and logic
    } catch (error) {
      console.error('Camera error:', error);
    }
  }

  startRecording(): void {
    if (!this.isHoldToRecord) {
      this.toggleRecording();
    }
  }

  private toggleRecording(): void {
    if (this.isRecording) {
      this.stopRecording();
    } else {
      this.beginRecording();
    }
  }

  private async beginRecording(): Promise<void> {
    try {
      this.updateCanvasDimensions();
      const config: RecordingConfig = {
        isHoldToRecord: this.isHoldToRecord,
        maxDuration: 300,
        audioConstraints: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      };
      await this.voiceRecordingService.startRecording(config, this.waveformCanvas?.nativeElement);
    } catch (error) {
      console.error('Error starting recording:', error);
      // ... error handling
    }
  }

  private async stopRecording(): Promise<void> {
    try {
      const result = await this.voiceRecordingService.stopRecording();
      if (result) {
        const filePreview = this.fileHandlingService.createAudioFilePreview(result);
        this.filePreviews = [...this.filePreviews, filePreview];
        this.filesSelected.emit(this.filePreviews);
      }
    } catch (error) {
      console.error('Error stopping recording:', error);
    }
  }

  cancelRecording(): void {
    this.voiceRecordingService.cancelRecording();
  }

  async sendVoiceMessage(): Promise<void> {
    await this.stopRecording();
  }

  private updateCanvasDimensions(): void {
    const container = document.querySelector('.input-field-container');
    if (container) {
      const rect = container.getBoundingClientRect();
      this.canvasWidth = Math.floor(rect.width);
      this.canvasHeight = Math.floor(rect.height) || 80;
    }
  }

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

  ngOnDestroy(): void {
    window.removeEventListener('resize', () => this.updateCanvasDimensions());
    if (this.recordingStateSubscription) {
      this.recordingStateSubscription.unsubscribe();
    }
    if (this.isRecording) {
      this.voiceRecordingService.cancelRecording();
    }
    this.clearFilePreviews();
  }
}
