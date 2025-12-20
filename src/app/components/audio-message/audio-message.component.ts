import { Component, Input, OnInit, OnDestroy, ViewChild, ElementRef, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { IFilePreview, UploadStatus } from '../../data/models';
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
      const oldAttachment = changes['attachment'].previousValue;

      console.log('AudioMessage: Attachment changed', {
        newId: newAttachment?.id,
        oldId: oldAttachment?.id,
        newStatus: newAttachment?.uploadStatus,
        oldStatus: oldAttachment?.uploadStatus,
        hasFile: !!newAttachment?.file,
        hasBase64: !!newAttachment?.base64Data
      });

      if (newAttachment?.transcript && !this.loadedTranscript) {
        this.loadedTranscript = newAttachment.transcript;
      }

      // Re-initialize audio URL if:
      // - We don't have one yet
      // - Or upload status changed from uploading to completed
      // - Or the attachment ID changed (server ID received)
      const statusChanged = oldAttachment?.uploadStatus === 'uploading' && newAttachment?.uploadStatus === 'completed';
      const idChanged = oldAttachment?.id !== newAttachment?.id;

      if (!this.audioUrl || statusChanged || idChanged || this.audioError) {
        // Reset error state and reinitialize
        this.audioError = false;
        this.triedBackendFallback = false;
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

  // Parse duration from filename to seconds (fallback when audio metadata unavailable)
  get parsedDurationSeconds(): number {
    const match = this.attachment.name.match(/\((\d+):(\d+)\)/);
    if (match) {
      return parseInt(match[1], 10) * 60 + parseInt(match[2], 10);
    }
    return 0;
  }

  // Get effective duration for progress calculations
  // Uses audio metadata if valid, otherwise falls back to parsed filename duration
  get effectiveDuration(): number {
    if (this.duration > 0 && Number.isFinite(this.duration)) {
      return this.duration;
    }
    return this.parsedDurationSeconds;
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

  onError(event?: Event): void {
    // Get more details about the error
    const audioEl = this.audioPlayerRef?.nativeElement;
    const error = audioEl?.error;

    console.error('AudioMessage: Audio error', {
      errorCode: error?.code,
      errorMessage: error?.message,
      audioUrl: this.audioUrl ? this.audioUrl.substring(0, 100) + '...' : null,
      attachmentId: this.attachment?.id,
      networkState: audioEl?.networkState,
      readyState: audioEl?.readyState
    });

    // Only handle error if we actually have a URL set
    // (avoid error on initial empty src)
    if (this.audioUrl) {
      // If we were using base64 data and it failed, try loading from backend
      if (this.audioUrl.startsWith('data:') && this.attachment?.id && !this.triedBackendFallback) {
        console.log('AudioMessage: Base64 failed, trying backend fallback');
        this.triedBackendFallback = true;
        this.audioUrl = null;
        this.loadAudio(); // Try loading from backend
      } else {
        this.audioError = true;
      }
    }
    this.isLoading = false;
  }

  // Track if we've already tried the backend fallback
  private triedBackendFallback = false;

  // Seek to position
  onSeek(event: MouseEvent): void {
    if (!this.audioPlayerRef?.nativeElement || !this.effectiveDuration) return;

    const progressBar = event.currentTarget as HTMLElement;
    const rect = progressBar.getBoundingClientRect();
    const percent = (event.clientX - rect.left) / rect.width;
    this.audioPlayerRef.nativeElement.currentTime = percent * this.effectiveDuration;
  }

  // Get progress percentage
  get progressPercent(): number {
    if (!this.effectiveDuration) return 0;
    return (this.currentTime / this.effectiveDuration) * 100;
  }

  // Check if duration is valid (finite number > 0)
  get hasValidDuration(): boolean {
    return this.duration > 0 && Number.isFinite(this.duration);
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
