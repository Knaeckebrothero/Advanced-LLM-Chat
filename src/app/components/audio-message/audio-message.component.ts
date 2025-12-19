import { Component, Input, OnInit, OnDestroy, ViewChild, ElementRef, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { IFilePreview, FileType, UploadStatus } from '../../data/models';
import { ApiService } from '../../services/api.service';

/**
 * AudioMessageComponent displays an audio message with a player and expandable transcript.
 * Used for voice messages that have been transcribed by the backend.
 */
@Component({
  selector: 'app-audio-message',
  standalone: true,
  imports: [
    CommonModule,
    MatIconModule,
    MatButtonModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './audio-message.component.html',
  styleUrls: ['./audio-message.component.scss']
})
export class AudioMessageComponent implements OnInit, OnDestroy, OnChanges {
  @Input() attachment!: IFilePreview;
  @Input() transcript?: string;
  @Input() messageId?: number;
  @Input() conversationId?: string;

  @ViewChild('audioPlayer') audioPlayerRef!: ElementRef<HTMLAudioElement>;

  // Audio state
  isPlaying = false;
  currentTime = 0;
  duration = 0;
  isLoading = false;
  audioError = false;

  // Transcript state
  showTranscript = false;
  loadedTranscript: string | null = null;
  isLoadingTranscript = false;

  // Audio URL
  audioUrl: string | null = null;
  private objectUrl: string | null = null;

  // Upload status helpers
  get isTranscribing(): boolean {
    return this.attachment?.uploadStatus === UploadStatus.UPLOADING;
  }

  get isUploadPending(): boolean {
    return this.attachment?.uploadStatus === UploadStatus.PENDING;
  }

  get isUploadFailed(): boolean {
    return this.attachment?.uploadStatus === UploadStatus.FAILED;
  }

  constructor(private apiService: ApiService) {}

  ngOnInit(): void {
    // If transcript is provided directly (from inline content), use it
    if (this.transcript) {
      this.loadedTranscript = this.transcript;
    }

    // Try to get audio URL from various sources
    this.initializeAudioUrl();
  }

  ngOnChanges(changes: SimpleChanges): void {
    // React to attachment changes (e.g., when transcript becomes available)
    if (changes['attachment'] && !changes['attachment'].firstChange) {
      const newAttachment = changes['attachment'].currentValue;
      if (newAttachment?.transcript && !this.loadedTranscript) {
        this.loadedTranscript = newAttachment.transcript;
      }
      // Re-initialize audio URL if needed
      if (!this.audioUrl && newAttachment?.base64Data) {
        this.initializeAudioUrl();
      }
    }

    // React to transcript input changes
    if (changes['transcript'] && !changes['transcript'].firstChange) {
      if (changes['transcript'].currentValue) {
        this.loadedTranscript = changes['transcript'].currentValue;
      }
    }
  }

  /**
   * Initialize audio URL from available sources:
   * 1. Local File object (best quality, works offline)
   * 2. Base64 data (works after deserialization from IndexedDB)
   * 3. Backend API (fallback, requires network)
   */
  private initializeAudioUrl(): void {
    console.log('AudioMessage: Initializing audio URL', {
      hasFile: !!this.attachment.file,
      fileSize: this.attachment.file?.size,
      hasBase64: !!this.attachment.base64Data,
      base64Length: this.attachment.base64Data?.length,
      attachmentId: this.attachment.id,
      uploadStatus: this.attachment.uploadStatus
    });

    // Priority 1: Local file object
    if (this.attachment.file && this.attachment.file.size > 0) {
      this.objectUrl = URL.createObjectURL(this.attachment.file);
      this.audioUrl = this.objectUrl;
      console.log('AudioMessage: Using File object URL');
      return;
    }

    // Priority 2: Base64 data (stored for offline playback)
    if (this.attachment.base64Data) {
      this.audioUrl = this.attachment.base64Data;
      console.log('AudioMessage: Using base64 data URL, prefix:', this.attachment.base64Data.substring(0, 50));
      return;
    }

    // Priority 3: Will be loaded from backend on first play via loadAudio()
    // audioUrl remains null, will be loaded when user clicks play
    console.log('AudioMessage: No local audio source, will load from backend on play');
  }

  ngOnDestroy(): void {
    // Revoke object URL if created
    if (this.objectUrl) {
      URL.revokeObjectURL(this.objectUrl);
    }
  }

  // Get duration from file name (e.g., "Voice message (01:23)")
  get displayDuration(): string {
    const match = this.attachment.name.match(/\((\d+:\d+)\)/);
    return match ? match[1] : '0:00';
  }

  // Format time in MM:SS
  formatTime(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }

  // Toggle play/pause
  async togglePlay(): Promise<void> {
    if (!this.audioUrl) {
      await this.loadAudio();
    }

    if (this.audioPlayerRef?.nativeElement) {
      if (this.isPlaying) {
        this.audioPlayerRef.nativeElement.pause();
      } else {
        await this.audioPlayerRef.nativeElement.play();
      }
    }
  }

  // Load audio from backend if not available locally
  private async loadAudio(): Promise<void> {
    if (this.audioUrl || this.isLoading) return;

    this.isLoading = true;
    this.audioError = false;

    try {
      const blob = await this.apiService.getFile(this.attachment.id);
      this.objectUrl = URL.createObjectURL(blob);
      this.audioUrl = this.objectUrl;
    } catch (error) {
      console.error('Error loading audio:', error);
      this.audioError = true;
    } finally {
      this.isLoading = false;
    }
  }

  // Audio event handlers
  onPlay(): void {
    this.isPlaying = true;
  }

  onPause(): void {
    this.isPlaying = false;
  }

  onEnded(): void {
    this.isPlaying = false;
    this.currentTime = 0;
  }

  onTimeUpdate(event: Event): void {
    const audio = event.target as HTMLAudioElement;
    this.currentTime = audio.currentTime;
  }

  onLoadedMetadata(event: Event): void {
    const audio = event.target as HTMLAudioElement;
    this.duration = audio.duration;
  }

  onError(): void {
    this.audioError = true;
    this.isLoading = false;
  }

  // Seek to position
  onSeek(event: MouseEvent): void {
    if (!this.audioPlayerRef?.nativeElement || !this.duration) return;

    const progressBar = event.currentTarget as HTMLElement;
    const rect = progressBar.getBoundingClientRect();
    const percent = (event.clientX - rect.left) / rect.width;
    this.audioPlayerRef.nativeElement.currentTime = percent * this.duration;
  }

  // Get progress percentage
  get progressPercent(): number {
    if (!this.duration) return 0;
    return (this.currentTime / this.duration) * 100;
  }

  // Toggle transcript visibility
  async toggleTranscript(): Promise<void> {
    this.showTranscript = !this.showTranscript;

    // Load transcript if showing and not already loaded
    if (this.showTranscript && !this.loadedTranscript && !this.isLoadingTranscript) {
      await this.loadTranscript();
    }
  }

  // Load transcript from backend
  private async loadTranscript(): Promise<void> {
    this.isLoadingTranscript = true;

    try {
      const text = await this.apiService.getFileText(this.attachment.id);
      this.loadedTranscript = text;
    } catch (error) {
      console.error('Error loading transcript:', error);
      this.loadedTranscript = 'Could not load transcript';
    } finally {
      this.isLoadingTranscript = false;
    }
  }

  // Retry loading audio
  async retryLoad(): Promise<void> {
    this.audioError = false;
    await this.loadAudio();
  }
}
