import { Component, Input, OnChanges, OnDestroy, SimpleChanges, ViewChild, ElementRef } from '@angular/core';
import { Message, AgentStep, AgentStepType, AgentStatus } from '../../data/objects/message';
import { DomSanitizer, SafeUrl } from '@angular/platform-browser';
import { MatDialog } from '@angular/material/dialog';
import { ChatUiComponent } from '../chat-ui.component';
import { FileType, FilePreviewUtil, FilePreview } from '../../data/objects/file-preview';
import { FilePreviewDialogComponent, FilePreviewDialogData } from '../../components/file-preview-dialog/file-preview-dialog.component';
import { ApiService } from '../../services/api.service';
import { SettingsStateService } from '../../services/settings-state.service';

@Component({
  selector: 'app-chat-ui-message',
  templateUrl: './chat-ui-message.component.html',
  styleUrls: ['./chat-ui-message.component.scss'],
  standalone: false
})
export class ChatUiMessageComponent implements OnChanges, OnDestroy {
  // Pass the message object from the parent component
  @Input() message!: Message;
  @Input() isLastAiMessage: boolean = false;

  // Variables
  editing: boolean = false;
  backupContent!: string;
  messageTextContent: string = '';

  constructor(
    private sanitizer: DomSanitizer,
    private chatUI: ChatUiComponent,
    private dialog: MatDialog,
    private apiService: ApiService,
    private settingsState: SettingsStateService
  ) { }

  // TTS Audio Player reference
  @ViewChild('ttsAudioPlayer') ttsAudioPlayerRef!: ElementRef<HTMLAudioElement>;

  // TTS state
  ttsAudioUrl: string | null = null;
  isGeneratingTTS = false;
  isTTSPlaying = false;
  ttsCurrentTime = 0;
  ttsDuration = 0;
  ttsError = false;

  // Copy message content to clipboard
  copyMessage(): void {
    let textToCopy = '';
    if (this.message.isText()) {
      textToCopy = this.message.textContent || '';
    } else if (this.message.isAgent()) {
      textToCopy = this.message.content.finalResponse || '';
    }

    if (textToCopy) {
      navigator.clipboard.writeText(textToCopy).then(() => {
        console.log('Message copied to clipboard');
      }).catch(err => {
        console.error('Failed to copy message:', err);
      });
    }
  }


  ngOnChanges(changes: SimpleChanges) {
    if (changes['message']) {
      this.updateFormattedContent();
    }
  }

  private updateFormattedContent() {
    if (this.message && this.message.isText()) {
      const textContent = this.message.getDisplayContent();
      // Apply user/AI name replacements - markdown will be parsed by ngx-markdown
      this.messageTextContent = textContent
        .replace(/\{\{user\}\}/g, this.chatUI.userName)
        .replace(this.chatUI.aiName + ':', '')
        .replace(/"/ + this.chatUI.aiName + ':' + /"/, '');
    }
  }

  // Getter for agent response content (for ngx-markdown)
  get agentResponseContent(): string {
    if (this.message?.isAgent()) {
      return this.message.content?.finalResponse || '';
    }
    return '';
  }

  getAttachmentIcon(type: FileType): string {
    return FilePreviewUtil.getFileIcon(type);
  }

  onAttachmentClick(event: MouseEvent, attachment: FilePreview): void {
    event.preventDefault();
    this.openFilePreviewDialog(attachment);
  }

  createDownloadUrl(file: File): SafeUrl {
    const objectUrl = URL.createObjectURL(file);
    return this.sanitizer.bypassSecurityTrustUrl(objectUrl);
  }

  openFilePreviewDialog(attachment: FilePreview): void {
    const dialogData: FilePreviewDialogData = {
      fileId: attachment.id,
      fileName: attachment.name,
      fileSize: attachment.sizeFormatted,
      fileType: attachment.type as FileType,
      mimeType: attachment.mimeType,
      // Pass local content if available
      localUrl: attachment.preview,
      localFile: attachment.file,
      // Pass message info for thumbnail regeneration on synced images
      messageId: this.message.id,
      conversationId: this.message.conversationId
    };

    this.dialog.open(FilePreviewDialogComponent, {
      data: dialogData,
      panelClass: 'file-preview-dialog-panel',
      hasBackdrop: false, // Component handles its own backdrop
      maxWidth: '100vw',
      maxHeight: '100vh',
      width: '100vw',
      height: '100vh'
    });
  }

  // Edit message button
  editMessage() {
    // Only allow editing text messages
    if (!this.message.isText()) {
      console.log('Cannot edit non-text messages');
      return;
    }

    console.log('Started editing message:', this.message.id);

    // Backup the current content
    this.backupContent = this.message.textContent || '';

    // Enable editing
    this.editing = true;
  }

  // Delete message button
  deleteMessage() {
    this.chatUI.deleteMessage(this.message.id!);
  }

  /*
  Method for editing the messages content
  */
  updateContent(newContent: string) {
    // Store the new content temporarily
    this.backupContent = newContent;
  }

  doneEditing() {
    console.log('Successfully edited message:', this.message.id);

    // Disable editing
    this.editing = false;

    // Trigger a request to update the message with the new content
    if (this.message.isText() && this.backupContent !== undefined) {
      this.chatUI.patchMessage(this.message.id!, this.backupContent);
    }
  }

  abortEditing() {
    console.log('Aborted editing message:', this.message.id);

    // Disable editing
    this.editing = false;

    // Reset backup content
    this.backupContent = '';
  }

  // Get the display content for the template
  get displayContent(): string {
    return this.message.getDisplayContent();
  }

  // Check if this is a voice message (text with only audio attachment)
  // In this case, we don't show the text content separately since
  // the AudioMessageComponent handles the transcript display
  isVoiceMessageWithTranscript(): boolean {
    if (!this.message.isText() || !this.message.hasAttachments()) {
      return false;
    }
    const attachments = this.message.attachments;
    // If there's exactly one audio attachment and the text looks like a transcript
    // (not manually typed text), treat it as a voice message
    if (attachments && attachments.length === 1 && attachments[0].type === FileType.AUDIO) {
      // Check if the attachment name indicates it's a voice message
      return attachments[0].name.includes('Voice message');
    }
    return false;
  }

  // Check if message is editable
  get isEditable(): boolean {
    return this.message.isText();
  }

  // Check if message can be regenerated
  get canRegenerate(): boolean {
    // Only AI messages can be regenerated
    if (this.message.roleName === 'user') {
      return false;
    }

    // Check if this is the last AI message in the conversation
    return this.isLastAiMessage;
  }

  // Regenerate the message
  regenerateMessage() {
    console.log('Regenerating message:', this.message.id);
    this.chatUI.regenerateMessage(this.message);
  }

  // Rate the message
  rateMessage(rating: number) {
    console.log('Rating message:', this.message.id, 'with rating:', rating);

    // Toggle rating if clicking the same rating
    if (this.message.rating === rating) {
      // If already rated with this value, remove the rating
      this.chatUI.rateMessage(this.message, null);
    } else {
      // Otherwise, set the new rating
      this.chatUI.rateMessage(this.message, rating);
    }
  }

  // ===== Agent Message Helper Methods =====

  // Get icon for agent step type
  getStepIcon(type: AgentStepType): string {
    const icons: Record<AgentStepType, string> = {
      thought: 'psychology',
      tool_call: 'build',
      tool_result: 'check_circle',
      observation: 'visibility',
    };
    return icons[type] || 'circle';
  }

  // Get status text for agent status
  getStatusText(status: AgentStatus): string {
    const texts: Record<AgentStatus, string> = {
      thinking: 'Reasoning...',
      responding: 'Generating response...',
      complete: '',
      error: 'An error occurred',
    };
    return texts[status];
  }

  // TrackBy function for agent steps
  trackStep(index: number, step: AgentStep): string {
    return step.id;
  }

  // ===== TTS Methods =====

  /**
   * Toggle TTS playback - generates audio if not available, or toggles player visibility
   */
  async toggleReadOutLoud(): Promise<void> {
    // If we have an error, retry
    if (this.ttsError) {
      this.ttsError = false;
      this.ttsAudioUrl = null;
    }

    // If already have audio, toggle player visibility
    if (this.ttsAudioUrl) {
      this.closeTTSPlayer();
      return;
    }

    this.isGeneratingTTS = true;
    this.ttsError = false;

    try {
      // Get current language from settings
      const settings = this.settingsState.getCurrentSettings();
      const language = settings?.language || 'en';

      // Generate TTS
      const audioBlob = await this.apiService.generateTTS(
        this.message.conversationId,
        this.message.id!,
        language
      );

      // Create object URL
      this.ttsAudioUrl = URL.createObjectURL(audioBlob);

      // Wait for next tick, then auto-play
      setTimeout(() => {
        if (this.ttsAudioPlayerRef?.nativeElement) {
          this.ttsAudioPlayerRef.nativeElement.play().catch(err => {
            console.error('Auto-play failed:', err);
          });
        }
      }, 100);

    } catch (error) {
      console.error('TTS generation failed:', error);
      this.ttsError = true;
    } finally {
      this.isGeneratingTTS = false;
    }
  }

  /**
   * Toggle TTS playback (play/pause)
   */
  toggleTTSPlayback(): void {
    if (this.ttsAudioPlayerRef?.nativeElement) {
      if (this.isTTSPlaying) {
        this.ttsAudioPlayerRef.nativeElement.pause();
      } else {
        this.ttsAudioPlayerRef.nativeElement.play();
      }
    }
  }

  /**
   * Close TTS player and clean up
   */
  closeTTSPlayer(): void {
    if (this.ttsAudioPlayerRef?.nativeElement) {
      this.ttsAudioPlayerRef.nativeElement.pause();
    }
    if (this.ttsAudioUrl) {
      URL.revokeObjectURL(this.ttsAudioUrl);
      this.ttsAudioUrl = null;
    }
    this.isTTSPlaying = false;
    this.ttsCurrentTime = 0;
    this.ttsDuration = 0;
  }

  // TTS Audio event handlers
  onTTSPlay(): void {
    this.isTTSPlaying = true;
  }

  onTTSPause(): void {
    this.isTTSPlaying = false;
  }

  onTTSEnded(): void {
    this.isTTSPlaying = false;
    this.ttsCurrentTime = 0;
  }

  onTTSTimeUpdate(event: Event): void {
    const audio = event.target as HTMLAudioElement;
    this.ttsCurrentTime = audio.currentTime;
  }

  onTTSLoadedMetadata(event: Event): void {
    const audio = event.target as HTMLAudioElement;
    this.ttsDuration = audio.duration;
  }

  onTTSError(): void {
    this.ttsError = true;
    this.isGeneratingTTS = false;
  }

  /**
   * Get TTS progress percentage
   */
  get ttsProgressPercent(): number {
    if (!this.ttsDuration) return 0;
    return (this.ttsCurrentTime / this.ttsDuration) * 100;
  }

  /**
   * Format time in MM:SS
   */
  formatTime(seconds: number): string {
    if (!seconds || !Number.isFinite(seconds)) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }

  /**
   * Seek to position in TTS audio
   */
  onTTSSeek(event: MouseEvent): void {
    if (!this.ttsAudioPlayerRef?.nativeElement || !this.ttsDuration) return;

    const progressBar = event.currentTarget as HTMLElement;
    const rect = progressBar.getBoundingClientRect();
    const percent = (event.clientX - rect.left) / rect.width;
    this.ttsAudioPlayerRef.nativeElement.currentTime = percent * this.ttsDuration;
  }

  /**
   * Check if TTS is available for this message
   */
  get canReadOutLoud(): boolean {
    // Only for AI messages (not user)
    if (this.message.roleName === 'user') return false;

    // Must have text content
    if (this.message.isText()) {
      return !!(this.message.textContent?.trim());
    }
    if (this.message.isAgent()) {
      return !!(this.message.content?.finalResponse?.trim());
    }
    return false;
  }

  /**
   * Cleanup on destroy
   */
  ngOnDestroy(): void {
    this.closeTTSPlayer();
  }
}
