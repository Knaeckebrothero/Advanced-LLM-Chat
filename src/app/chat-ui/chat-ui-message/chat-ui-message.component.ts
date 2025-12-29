import { Component, Input, OnChanges, OnDestroy, SimpleChanges, Renderer2, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { Message, AgentStep, AgentStepType, AgentStatus } from '../../data/objects/message';
import { DomSanitizer, SafeHtml, SafeUrl } from '@angular/platform-browser';
import { MatDialog } from '@angular/material/dialog';
import { ChatUiComponent } from '../chat-ui.component';
import { FileType, FilePreviewUtil, FilePreview } from '../../data/objects/file-preview';
import { FilePreviewDialogComponent, FilePreviewDialogData } from '../../components/file-preview-dialog/file-preview-dialog.component';
import { ApiService } from '../../services/api.service';
import { SettingsStateService } from '../../services/settings-state.service';
import { MarkdownService } from '../../services/markdown.service';

@Component({
  selector: 'app-chat-ui-message',
  templateUrl: './chat-ui-message.component.html',
  styleUrls: ['./chat-ui-message.component.scss'],
  standalone: false
})
export class ChatUiMessageComponent implements OnChanges, OnDestroy, AfterViewChecked {
  // Pass the message object from the parent component
  @Input() message!: Message;
  @Input() isLastAiMessage: boolean = false;

  // Variables
  editing: boolean = false;
  backupContent!: string;
  formattedTextContent: SafeHtml = '';
  private buttonsInjected = false;

  constructor(
    private sanitizer: DomSanitizer,
    private chatUI: ChatUiComponent,
    private renderer: Renderer2,
    private dialog: MatDialog,
    private apiService: ApiService,
    private settingsState: SettingsStateService,
    private markdownService: MarkdownService,
    private elementRef: ElementRef
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
      this.buttonsInjected = false; // Reset to allow button re-injection
      this.updateFormattedContent();
    }
  }

  private updateFormattedContent() {
    if (this.message && this.message.isText()) {
      const textContent = this.message.getDisplayContent();
      this.formattedTextContent = this.formatText(textContent);
    }
  }

  // Helper to format text content with markdown and replacements
  formatText(text: string): SafeHtml {
    if (!text) return '';

    // Apply user/AI name replacements before markdown parsing
    let processedText = text
      .replace(/\{\{user\}\}/g, this.chatUI.userName)
      .replace(this.chatUI.aiName + ':', '')
      .replace(/"/ + this.chatUI.aiName + ':' + /"/, '');

    // Parse markdown
    return this.markdownService.parse(processedText);
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

  // Format agent final response with markdown
  formatAgentResponse(response: string): SafeHtml {
    if (!response) return '';
    return this.markdownService.parse(response);
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

  // ===== Copy/Download Buttons for Tables & Code Blocks =====

  ngAfterViewChecked(): void {
    // Only try to inject if not already done and message exists
    if (!this.buttonsInjected && this.message) {
      this.injectCopyDownloadButtons();
    }
  }

  private injectCopyDownloadButtons(): void {
    const hostElement = this.elementRef.nativeElement;
    let elementsProcessed = 0;

    // Inject buttons for tables (check for tables that aren't already wrapped)
    const tables = hostElement.querySelectorAll('.message-text table, .response-text table');
    tables.forEach((table: HTMLTableElement) => {
      if (!table.parentElement?.classList.contains('table-wrapper')) {
        this.wrapTableWithButtons(table);
        elementsProcessed++;
      }
    });

    // Inject buttons for code blocks (check for pre that aren't already wrapped)
    const codeBlocks = hostElement.querySelectorAll('.message-text pre, .response-text pre');
    codeBlocks.forEach((pre: HTMLPreElement) => {
      if (!pre.parentElement?.classList.contains('code-wrapper')) {
        this.wrapCodeBlockWithButtons(pre);
        elementsProcessed++;
      }
    });

    // Check if raw message content SHOULD have tables/code blocks
    const rawContent = this.getRawMessageContent();
    const contentHasCodeBlocks = /```[\s\S]*?```/.test(rawContent);
    const contentHasTables = /\|.+\|/.test(rawContent) && /\|[-:]+\|/.test(rawContent);

    // Check if DOM has any tables/code (wrapped or not)
    const domHasTables = tables.length > 0;
    const domHasCodeBlocks = codeBlocks.length > 0;

    // Only mark as injected if:
    // 1. We processed some elements, OR
    // 2. Content doesn't expect tables/code AND DOM has none (nothing to do), OR
    // 3. Content expects tables/code AND DOM has them all wrapped already
    const allTablesWrapped = !hostElement.querySelectorAll('.message-text table:not(.table-wrapper table), .response-text table:not(.table-wrapper table)').length;
    const allCodeWrapped = !hostElement.querySelectorAll('.message-text pre:not(.code-wrapper pre), .response-text pre:not(.code-wrapper pre)').length;

    if (elementsProcessed > 0) {
      // We processed elements, mark as done
      this.buttonsInjected = true;
    } else if (!contentHasCodeBlocks && !contentHasTables) {
      // Content has no code/tables, nothing to inject
      this.buttonsInjected = true;
    } else if ((contentHasTables === domHasTables) && (contentHasCodeBlocks === domHasCodeBlocks) && allTablesWrapped && allCodeWrapped) {
      // DOM matches expectations and everything is wrapped
      this.buttonsInjected = true;
    }
    // Otherwise, keep buttonsInjected = false to retry on next check
  }

  /** Get raw message content for pattern checking */
  private getRawMessageContent(): string {
    if (this.message.isText()) {
      return this.message.textContent || '';
    }
    if (this.message.isAgent()) {
      return this.message.content?.finalResponse || '';
    }
    return '';
  }

  private wrapTableWithButtons(table: HTMLTableElement): void {
    const wrapper = this.renderer.createElement('div');
    this.renderer.addClass(wrapper, 'table-wrapper');

    const buttonContainer = this.renderer.createElement('div');
    this.renderer.addClass(buttonContainer, 'copy-download-buttons');

    // Copy button
    const copyBtn = this.createActionButton('content_copy', 'Copy as CSV', () => this.copyTableAsCSV(table));
    // Download button
    const downloadBtn = this.createActionButton('download', 'Download CSV', () => this.downloadTableAsCSV(table));

    this.renderer.appendChild(buttonContainer, copyBtn);
    this.renderer.appendChild(buttonContainer, downloadBtn);

    // Wrap table
    const parent = table.parentNode;
    this.renderer.insertBefore(parent, wrapper, table);
    this.renderer.appendChild(wrapper, table);
    this.renderer.appendChild(wrapper, buttonContainer);
  }

  private wrapCodeBlockWithButtons(pre: HTMLPreElement): void {
    const wrapper = this.renderer.createElement('div');
    this.renderer.addClass(wrapper, 'code-wrapper');

    const buttonContainer = this.renderer.createElement('div');
    this.renderer.addClass(buttonContainer, 'copy-download-buttons');

    // Get language from class if available
    const code = pre.querySelector('code');
    const langClass = code?.className.match(/language-(\w+)/);
    const language = langClass ? langClass[1] : 'txt';

    // Copy button
    const copyBtn = this.createActionButton('content_copy', 'Copy code', () => this.copyCodeBlock(pre));
    // Download button
    const downloadBtn = this.createActionButton('download', 'Download', () => this.downloadCodeBlock(pre, language));

    this.renderer.appendChild(buttonContainer, copyBtn);
    this.renderer.appendChild(buttonContainer, downloadBtn);

    // Wrap code block
    const parent = pre.parentNode;
    this.renderer.insertBefore(parent, wrapper, pre);
    this.renderer.appendChild(wrapper, pre);
    this.renderer.appendChild(wrapper, buttonContainer);
  }

  private createActionButton(icon: string, title: string, onClick: () => void): HTMLButtonElement {
    const button = this.renderer.createElement('button');
    this.renderer.addClass(button, 'action-icon-btn');
    this.renderer.setAttribute(button, 'title', title);
    this.renderer.setAttribute(button, 'type', 'button');

    // Create icon span (using mat-icon text content approach)
    const iconSpan = this.renderer.createElement('span');
    this.renderer.addClass(iconSpan, 'material-icons');
    const iconText = this.renderer.createText(icon);
    this.renderer.appendChild(iconSpan, iconText);
    this.renderer.appendChild(button, iconSpan);

    this.renderer.listen(button, 'click', (event: Event) => {
      event.stopPropagation();
      onClick();
    });

    return button;
  }

  private copyTableAsCSV(table: HTMLTableElement): void {
    const csv = this.tableToCSV(table);
    navigator.clipboard.writeText(csv).then(() => {
      console.log('Table copied as CSV');
    }).catch(err => {
      console.error('Failed to copy table:', err);
    });
  }

  private downloadTableAsCSV(table: HTMLTableElement): void {
    const csv = this.tableToCSV(table);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    this.downloadBlob(blob, 'table-export.csv');
  }

  private copyCodeBlock(pre: HTMLPreElement): void {
    const code = pre.querySelector('code');
    const text = code?.textContent || pre.textContent || '';
    navigator.clipboard.writeText(text).then(() => {
      console.log('Code copied to clipboard');
    }).catch(err => {
      console.error('Failed to copy code:', err);
    });
  }

  private downloadCodeBlock(pre: HTMLPreElement, language: string): void {
    const code = pre.querySelector('code');
    const text = code?.textContent || pre.textContent || '';

    // Map common languages to file extensions
    const extMap: { [key: string]: string } = {
      javascript: 'js', typescript: 'ts', python: 'py', java: 'java',
      csharp: 'cs', cpp: 'cpp', c: 'c', ruby: 'rb', go: 'go',
      rust: 'rs', php: 'php', swift: 'swift', kotlin: 'kt',
      html: 'html', css: 'css', json: 'json', xml: 'xml',
      yaml: 'yaml', markdown: 'md', sql: 'sql', bash: 'sh', shell: 'sh'
    };
    const ext = extMap[language.toLowerCase()] || language || 'txt';

    const blob = new Blob([text], { type: 'text/plain;charset=utf-8;' });
    this.downloadBlob(blob, `code-export.${ext}`);
  }

  private tableToCSV(table: HTMLTableElement): string {
    const rows: string[] = [];

    // Process header rows
    const headerRow = table.querySelector('thead tr');
    if (headerRow) {
      const cells = Array.from(headerRow.querySelectorAll('th, td'));
      rows.push(cells.map(cell => this.escapeCSVCell(cell.textContent || '')).join(','));
    }

    // Process body rows
    const bodyRows = table.querySelectorAll('tbody tr');
    bodyRows.forEach(row => {
      const cells = Array.from(row.querySelectorAll('td, th'));
      rows.push(cells.map(cell => this.escapeCSVCell(cell.textContent || '')).join(','));
    });

    return rows.join('\n');
  }

  private escapeCSVCell(value: string): string {
    // Remove extra whitespace
    value = value.trim();
    // Escape quotes and wrap in quotes if needed
    if (value.includes(',') || value.includes('"') || value.includes('\n')) {
      return `"${value.replace(/"/g, '""')}"`;
    }
    return value;
  }

  private downloadBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  /**
   * Cleanup on destroy
   */
  ngOnDestroy(): void {
    this.closeTTSPlayer();
  }
}
