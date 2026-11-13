import { Component, Input, Output, EventEmitter, OnChanges, OnDestroy, SimpleChanges, ViewChild, ElementRef } from '@angular/core';
import { Message, AgentStatus } from '../../data/objects/message';
import { DomSanitizer, SafeUrl } from '@angular/platform-browser';
import { Router } from '@angular/router';
import { MatDialog } from '@angular/material/dialog';
import { ChatUiComponent } from '../chat-ui.component';
import { FileType, FilePreviewUtil, FilePreview } from '../../data/objects/file-preview';
import {
  FilePreviewDialogComponent, FilePreviewDialogData, openFilePreview
} from '../../components/file-preview-dialog/file-preview-dialog.component';
import { ApiService } from '../../services/api.service';
import { SettingsStateService } from '../../services/settings-state.service';
import { CatalogService } from '../../services/catalog.service';
import { IMessageUsage, IPublicModel } from '../../data/models/catalog.model';
import { TranslateService } from '@ngx-translate/core';
import { Observable } from 'rxjs';
import { describeHttpError } from '../../catalog-admin/catalog-admin.utils';
import { NOTE_ROUTE, noteMarkdown, noteSlugFromHref } from '../../knowledge-base/kb-markdown';
import { FilePreviewsService } from '../../services/file-previews.service';
import { ConversationFilesService } from '../../services/conversation-files.service';
import { MessageWithSyncStatus } from '../../repositories/message.repository';
import { IFileRef } from '../../data/models/file.model';
import { stepFiles, unplacedFiles } from './answer-files/answer-files.component';
import { AnswerPart, FILE_LINK, answerParts, findFile } from './answer-parts';

// The IDs the server gives stored files (backend FILE_ID_PATTERN); a file not uploaded yet has another
const SERVER_FILE_ID = /^file_\d+_[0-9a-f]+$/;

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
  insertRole: 'user' | 'Assistant' | 'system' = 'user';
  insertText = '';
  insertBusy = false;
  insertError: string | null = null;
  readonly insertRoles: { value: 'user' | 'Assistant' | 'system'; label: string }[] = [
    { value: 'user', label: 'message.insertUser' },
    { value: 'Assistant', label: 'message.insertAssistant' },
    { value: 'system', label: 'message.insertSystem' },
  ];
  readonly insertPositions: { value: 'before' | 'after'; label: string }[] = [
    { value: 'after', label: 'message.insertBelow' },
    { value: 'before', label: 'message.insertAbove' },
  ];

  // Phones: your own messages show edit and delete only after a tap on them
  actionsOpen = false;

  // The copy button shows a check for a moment after copying
  copied = false;
  private copiedTimer: ReturnType<typeof setTimeout> | null = null;

  // The message's text as parts (Markdown, and the files placed in it), worked out again only
  // when the text, the answer's steps or the known files change
  private partsSource: string | null = null;
  private partsState = '';
  private parts: AnswerPart[] = [];
  private placed: ReadonlySet<string> = new Set<string>();
  private images: IFileRef[] = [];

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
    private translate: TranslateService,
    private router: Router,
    private filePreviews: FilePreviewsService,
    private conversationFiles: ConversationFilesService
  ) {
    this.catalogModels$ = this.catalogService.models$;
  }

  /**
   * The message's only attachment is an image: it is shown large, as in a messenger, and the
   * bubble is as wide as the image, with the text under it. Several attachments are tiles.
   */
  get singlePhoto(): boolean {
    const attachments = this.message?.attachments;
    return !!attachments && attachments.length === 1 && attachments[0].type === 'image';
  }

  // The server's previews of this message's uploaded files, by file ID
  private serverPreviews = new Map<string, string>();
  private requestedPreviews = new Set<string>();

  /**
   * The server's preview of an attachment: of an image that has none in the browser (a message
   * that came from the server: another device, or after the browser's data was cleared), and
   * the first page of a PDF. Asked for once; null until it is there, and for a file the server
   * has no preview of.
   */
  serverPreview(attachment: FilePreview): string | null {
    const wanted = attachment.type === 'image' ? !attachment.preview : attachment.mimeType === 'application/pdf';
    if (!wanted || !SERVER_FILE_ID.test(attachment.id)) {
      return null;
    }
    if (!this.requestedPreviews.has(attachment.id)) {
      this.requestedPreviews.add(attachment.id);
      // A photo on its own is shown large, so it needs the large preview
      this.filePreviews.url(attachment.id, this.singlePhoto ? 'large' : 'small').then(
        url => this.serverPreviews.set(attachment.id, url),
        () => undefined
      );
    }
    return this.serverPreviews.get(attachment.id) ?? null;
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
        this.copied = true;
        if (this.copiedTimer) clearTimeout(this.copiedTimer);
        this.copiedTimer = setTimeout(() => {
          this.copied = false;
          this.copiedTimer = null;
        }, 1500);
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

  /**
   * The message's text for the chat: its Markdown ([[note]] links open the note on the Knowledge
   * base page), and between that the files it places in its text (answer-parts.ts): an agent's
   * answer shows files of the conversation that way. While an answer is written only its last
   * part changes, so what stands above it is not drawn again.
   */
  get textParts(): AnswerPart[] {
    if (!this.message) return [];
    const answer = this.message.isAgent() ? this.message.content : null;
    const content = answer ? answer.content || '' : this.messageTextContent;
    const streaming = answer?.status === 'responding';
    const steps = answer?.steps ?? [];
    const state = `${streaming}:${steps.length}:${this.conversationFiles.version}`;
    if (content === this.partsSource && state === this.partsState) return this.parts;
    this.partsSource = content;
    this.partsState = state;

    const conversationId = this.message.conversationId;
    // The message's own files come first: what the answer's tools created, or what a message attaches
    const own: IFileRef[] = answer
      ? steps.flatMap(step => [...stepFiles(step, 'files'), ...stepFiles(step, 'shownFiles')])
      : (this.message.attachments ?? []).filter(attachment => SERVER_FILE_ID.test(attachment.id)).map(attachment => (
        { fileId: attachment.id, name: attachment.name, mimeType: attachment.mimeType, size: attachment.size }));
    const parts = answerParts(
      content,
      reference => {
        const file = findFile(reference, own, this.conversationFiles.files(conversationId), this.message.id);
        // Not in the list: the file may be newer than it
        return file === null && this.conversationFiles.retry(conversationId, reference) ? undefined : file;
      },
      streaming,
      name => this.translate.instant('files.notFound', { name: '`' + name.replace(/`/g, '') + '`' })
    );
    for (const part of parts) {
      if (part.type === 'text') part.text = noteMarkdown(part.text);
    }
    this.parts = parts;
    this.placed = new Set(parts.flatMap(part => part.items.map(item => item.file?.fileId ?? '')));
    // The message's images as they follow each other on the page: what stands above the text,
    // then what the text places
    const above = unplacedFiles(steps, this.placed);
    const images = new Map<string, IFileRef>();
    for (const file of [...above.shown, ...above.created, ...parts.flatMap(part => part.items.map(item => item.file))]) {
      if (file?.mimeType.startsWith('image/') && !images.has(file.fileId)) images.set(file.fileId, file);
    }
    this.images = [...images.values()];
    return parts;
  }

  /** The files the answer places in its text (their IDs): they are not shown again above it. */
  get placedFileIds(): ReadonlySet<string> {
    void this.textParts;  // Worked out with the parts, whichever the template asks for first
    return this.placed;
  }

  /**
   * The images this message shows, in their order: an image opened from the message steps to
   * the one before and the one after it in the preview, without closing it in between. The
   * same list until the message's files change.
   */
  get gallery(): IFileRef[] {
    void this.textParts;
    return this.images;
  }

  /** The parts keep their place while the answer grows, so only the last one is drawn again. */
  trackPart(index: number, part: AnswerPart): string {
    return `${index}:${part.type}`;
  }

  trackPlaced(index: number, item: { reference: string }): string {
    return `${index}:${item.reference}`;
  }

  /** Once the Markdown is rendered: links to notes get their look, web links open in a new tab. */
  decorateLinks(): void {
    const host = this.elementRef.nativeElement as HTMLElement;
    host.querySelectorAll<HTMLAnchorElement>('.message-body markdown a[href]').forEach(anchor => {
      if (noteSlugFromHref(anchor.getAttribute('href'))) {
        anchor.classList.add('note-link');
      } else if (/^https?:/i.test(anchor.getAttribute('href') ?? '')) {
        anchor.target = '_blank';
        anchor.rel = 'noopener noreferrer';
      }
    });
  }

  /**
   * A link to a note opens it in the app instead of loading the page again; a link to a file
   * of the conversation (one placed in a table) opens the file.
   */
  onBodyClick(event: MouseEvent): void {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) {
      return;
    }
    const anchor = (event.target as HTMLElement | null)?.closest('a');
    const href = anchor?.getAttribute('href') ?? '';
    if (href.startsWith(FILE_LINK)) {
      event.preventDefault();
      const fileId = href.slice(FILE_LINK.length);
      const file = this.conversationFiles.files(this.message.conversationId)?.find(known => known.fileId === fileId)
        ?? this.ownFile(fileId);
      if (file) this.openFile(file);
      return;
    }
    const slug = noteSlugFromHref(href || null);
    if (!anchor || !slug) {
      return;
    }
    event.preventDefault();
    this.router.navigate([NOTE_ROUTE, slug]);
  }

  /** A file of this answer's steps, by its ID. */
  private ownFile(fileId: string): IFileRef | undefined {
    if (!this.message.isAgent()) return undefined;
    return this.message.content.steps
      .flatMap(step => [...stepFiles(step, 'files'), ...stepFiles(step, 'shownFiles')])
      .find(file => file.fileId === fileId);
  }

  /** Open a stored file in the preview dialog; an image of this message steps to its other images. */
  private openFile(file: IFileRef): void {
    openFilePreview(this.dialog, file, this.gallery);
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

  /** An attachment of this message as the preview dialog takes it. */
  private attachmentData(attachment: FilePreview): FilePreviewDialogData {
    return {
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
  }

  openFilePreviewDialog(attachment: FilePreview): void {
    const dialogData = this.attachmentData(attachment);
    // An image of several: the preview steps through the message's images
    const images = (this.message.attachments ?? []).filter(other => other.type === FileType.IMAGE);
    if (images.length > 1 && images.includes(attachment)) {
      dialogData.gallery = images.map(other => other === attachment ? dialogData : this.attachmentData(other));
    }

    this.dialog.open(FilePreviewDialogComponent, {
      data: dialogData,
      panelClass: 'file-preview-dialog-panel',
      autoFocus: 'dialog',  // As openFilePreview()
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

  /**
   * Your message the server didn't take: only this browser has it, it isn't being sent, and
   * nothing answered it. (A voice message waiting for its transcript isn't sent yet either, but
   * counts as 'synced' until then.)
   */
  get notSent(): boolean {
    const status = (this.message as MessageWithSyncStatus).syncStatus;
    return this.message.isLocal && this.message.isText() && this.message.roleName === 'user'
      && status !== 'pending' && status !== 'synced';
  }

  /** Sending it again answers it, so not while another answer streams. */
  get canResend(): boolean {
    return this.notSent && !this.chatUI.isStreaming;
  }

  resendMessage(event: Event) {
    event.stopPropagation();
    this.chatUI.resendMessage(this.message.id!).catch(error => console.error('Error resending message:', error));
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

  /** An agent answer that is still being written: no actions on it until it is done. */
  get inProgress(): boolean {
    return this.chatUI.isStreaming && this.message.isAgent()
      && (this.message.content.status === 'thinking' || this.message.content.status === 'responding');
  }

  /** An answer of the assistant: not your message, nor a system message (an instruction to the model). */
  get isAnswer(): boolean {
    return this.message.roleName !== 'user' && this.message.roleName !== 'system';
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
    if (!this.isAnswer) {
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
    return status === 'complete' ? '' : this.translate.instant(`message.status.${status}`);
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
    // Only for AI messages (not user or system)
    if (!this.isAnswer) return false;

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
    if (this.copiedTimer) {
      clearTimeout(this.copiedTimer);
    }
  }
}
