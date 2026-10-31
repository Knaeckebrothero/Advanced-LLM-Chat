import { Component, Input, Output, EventEmitter, OnChanges, OnDestroy, SimpleChanges, ViewChild, ElementRef } from '@angular/core';
import { Message, AgentStatus } from '../../data/objects/message';
import { DomSanitizer, SafeUrl } from '@angular/platform-browser';
import { MatDialog } from '@angular/material/dialog';
import { ChatUiComponent } from '../chat-ui.component';
import { FileType, FilePreviewUtil, FilePreview } from '../../data/objects/file-preview';
import { FilePreviewDialogComponent, FilePreviewDialogData } from '../../components/file-preview-dialog/file-preview-dialog.component';
import { ApiService } from '../../services/api.service';
import { SettingsStateService } from '../../services/settings-state.service';
import { CatalogService } from '../../services/catalog.service';
import { IMessageUsage, IPublicModel } from '../../data/models/catalog.model';
import { TranslateService } from '@ngx-translate/core';
import { Observable } from 'rxjs';
import { describeHttpError } from '../../catalog-admin/catalog-admin.utils';

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

  // Event emitter for agent steps expansion (for scroll adjustment)
  @Output() stepsExpanded = new EventEmitter<{ expanded: boolean; messageElement: HTMLElement }>();

  // Variables
  editing: boolean = false;
  backupContent!: string;
  messageTextContent: string = '';
  @ViewChild('editableDiv') editableDiv?: ElementRef<HTMLDivElement>;
  // Why the last edit couldn't be saved
  editError: string | null = null;

  // Manual editing: a message inserted above or below this one
  inserting = false;
  insertPosition: 'before' | 'after' = 'after';
  insertRole: 'user' | 'Assistant' = 'user';
  insertText = '';
  insertBusy = false;
  insertError: string | null = null;
  readonly insertRoles: { value: 'user' | 'Assistant'; label: string }[] = [
    { value: 'user', label: 'message.insertUser' },
    { value: 'Assistant', label: 'message.insertAssistant' },
  ];
  readonly insertPositions: { value: 'before' | 'after'; label: string }[] = [
    { value: 'after', label: 'message.insertBelow' },
    { value: 'before', label: 'message.insertAbove' },
  ];

  // Phones: your own messages show edit and delete only after a tap on them
  actionsOpen = false;

  // Model catalog: per-message model and usage
  showUsage = false;
  catalogModels$: Observable<IPublicModel[]>;

  constructor(
    private sanitizer: DomSanitizer,
    private chatUI: ChatUiComponent,
    private dialog: MatDialog,
    private apiService: ApiService,
    private settingsState: SettingsStateService,
    private elementRef: ElementRef,
    private catalogService: CatalogService,
    private translate: TranslateService
  ) {
    this.catalogModels$ = this.catalogService.models$;
  }

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
      textToCopy = this.message.content.content || '';
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
      return this.message.content?.content || '';
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

  // Edit message button: the text of a text message, the answer text of an agent message
  editMessage() {
    if (!this.isEditable) {
      return;
    }

    // Backup the current content
    this.backupContent = this.editableText;
    this.editError = null;

    // Enable editing
    this.editing = true;
    setTimeout(() => this.editableDiv?.nativeElement.focus());
  }

  /** The text an edit changes. */
  get editableText(): string {
    if (this.message.isAgent()) {
      return this.message.content.content || '';
    }
    return this.message.isText() ? this.message.textContent || '' : '';
  }

  // A tap on your own message shows or hides its actions (only phones hide them, see the styles)
  toggleActions(event: MouseEvent) {
    if (this.message.roleName !== 'user' || this.editing) {
      return;
    }
    // Taps on links, buttons, attachments and the audio player keep their own meaning
    const target = event.target as HTMLElement;
    if (target.closest('a, button, input, audio, .message-attachments, .editable-message')) {
      return;
    }
    this.actionsOpen = !this.actionsOpen;
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

  /**
   * Save the edit. Manual editing only changes the text; guided editing answers your
   * message again, which deletes the messages after it (asked first if more than its answer).
   */
  async doneEditing() {
    const content = this.editableDiv?.nativeElement.innerText ?? this.backupContent;
    if (content === undefined || content === this.editableText) {
      this.editing = false;
      return;
    }

    const resend = this.resendsOnEdit;
    if (resend) {
      const following = this.chatUI.countMessagesAfter(this.message);
      if (following > 1 && !confirm(this.translate.instant('message.resendConfirm', { count: following }))) {
        return;
      }
    }

    this.editing = false;
    this.editError = null;
    try {
      if (resend) {
        await this.chatUI.resendEditedMessage(this.message.id, content);
      } else {
        await this.chatUI.patchMessage(this.message.id, content);
      }
    } catch (error) {
      console.error('Failed to save the edited message:', error);
      this.editError = this.translate.instant('message.editFailed', { error: describeHttpError(error, this.translate) });
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

  /** Manual editing (the setting): edit any message and insert messages; nothing is generated. */
  get manualEditing(): boolean {
    return this.settingsState.getCurrentSettings()?.editingMode === 'manual';
  }

  /**
   * Manual: any stored message (an agent message once complete). Guided: only your own
   * messages. Not while an answer streams, nor for messages only this browser has.
   */
  get isEditable(): boolean {
    if (this.message.isLocal || this.chatUI.isStreaming) {
      return false;
    }
    if (this.manualEditing) {
      return this.message.isText() || (this.message.isAgent() && this.message.content.status === 'complete');
    }
    return this.message.isText() && this.message.roleName === 'user';
  }

  /** Whether saving an edit answers the message again (guided editing of your own message). */
  get resendsOnEdit(): boolean {
    return !this.manualEditing && this.message.roleName === 'user';
  }

  get canInsert(): boolean {
    return this.manualEditing && !this.message.isLocal && !this.chatUI.isStreaming;
  }

  startInsert() {
    this.inserting = true;
    this.insertError = null;
  }

  cancelInsert() {
    this.inserting = false;
    this.insertText = '';
    this.insertError = null;
    this.insertRole = 'user';
    this.insertPosition = 'after';
  }

  async submitInsert() {
    const content = this.insertText.trim();
    if (!content || this.insertBusy) {
      return;
    }
    this.insertBusy = true;
    this.insertError = null;
    try {
      await this.chatUI.insertMessage(this.message, this.insertPosition, this.insertRole, content);
      this.cancelInsert();
    } catch (error) {
      console.error('Failed to insert the message:', error);
      this.insertError = this.translate.instant('message.insertFailed', { error: describeHttpError(error, this.translate) });
    } finally {
      this.insertBusy = false;
    }
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

  // Regenerate once with another catalog model
  regenerateWith(modelId: number | null) {
    if (modelId === null) return;
    this.chatUI.regenerateMessage(this.message, modelId);
  }

  // ===== Model and Usage =====

  /** Display name of the model that wrote this answer (agent messages from a catalog-aware backend). */
  get modelName(): string | null {
    return this.message.isAgent() ? this.message.content.modelName || null : null;
  }

  get currentModelId(): number | null {
    return this.message.isAgent() ? this.message.content.modelId ?? null : null;
  }

  get usage(): IMessageUsage | null {
    return this.message.isAgent() ? this.message.content.usage || null : null;
  }

  /** One line for the tooltip and screen readers: tokens in/out (reasoning), cost. */
  get usageSummary(): string {
    const usage = this.usage;
    if (!usage) return '';
    const parts = [
      this.translate.instant('catalog.message.inputTokens', { count: this.formatCount(usage.inputTokens) }),
      this.translate.instant('catalog.message.outputTokens', { count: this.formatCount(usage.outputTokens) })
    ];
    if (usage.reasoningTokens) {
      parts.push(this.translate.instant('catalog.message.reasoningTokens', { count: this.formatCount(usage.reasoningTokens) }));
    }
    const cost = this.costText;
    if (cost) {
      parts.push(this.translate.instant('catalog.message.cost', { cost }));
    }
    return parts.join(' · ');
  }

  /** The cost with its currency; empty when the model has no prices. */
  get costText(): string {
    const usage = this.usage;
    if (!usage || usage.cost === null || usage.cost === undefined) return '';
    const digits = usage.cost !== 0 && Math.abs(usage.cost) < 0.01 ? 4 : 2;
    if (usage.currency) {
      try {
        return new Intl.NumberFormat(this.locale, {
          style: 'currency',
          currency: usage.currency,
          minimumFractionDigits: 2,
          maximumFractionDigits: digits
        }).format(usage.cost);
      } catch {
        // Unknown currency code: fall through to the plain number
      }
    }
    const amount = new Intl.NumberFormat(this.locale, { maximumFractionDigits: digits }).format(usage.cost);
    return usage.currency ? `${amount} ${usage.currency}` : amount;
  }

  formatCount(value: number | null | undefined): string {
    return new Intl.NumberFormat(this.locale).format(value ?? 0);
  }

  private get locale(): string {
    return this.translate.currentLang || this.settingsState.getCurrentSettings()?.language || 'en';
  }

  // ===== Agent Message Helper Methods =====

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

  // Handle steps panel expansion change - emit event for scroll adjustment
  onStepsExpandedChange(expanded: boolean): void {
    // Emit event with the message element for scroll adjustment
    this.stepsExpanded.emit({
      expanded,
      messageElement: this.elementRef.nativeElement
    });
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
      return !!(this.message.content?.content?.trim());
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
