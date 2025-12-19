// src/app/chat-ui/chat-ui-message/chat-ui-message.component.ts
import { Component, Input, OnChanges, SimpleChanges, Renderer2 } from '@angular/core';
import { Message, AgentStep, AgentStepType, AgentStatus } from '../../data/objects/message';
import { DomSanitizer, SafeHtml, SafeUrl } from '@angular/platform-browser';
import { MatDialog } from '@angular/material/dialog';
import { ChatUiComponent } from '../chat-ui.component';
import { FileType, FilePreviewUtil, FilePreview } from '../../data/objects/file-preview';
import { FilePreviewDialogComponent, FilePreviewDialogData } from '../../components/file-preview-dialog/file-preview-dialog.component';

@Component({
  selector: 'app-chat-ui-message',
  templateUrl: './chat-ui-message.component.html',
  styleUrls: ['./chat-ui-message.component.scss'],
  standalone: false
})
export class ChatUiMessageComponent implements OnChanges {
  // Pass the message object from the parent component
  @Input() message!: Message;
  @Input() isLastAiMessage: boolean = false;

  // Variables
  editing: boolean = false;
  backupContent!: string;
  formattedTextContent: SafeHtml = '';

  constructor(
    private sanitizer: DomSanitizer,
    private chatUI: ChatUiComponent,
    private renderer: Renderer2,
    private dialog: MatDialog
  ) { }

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
      const formattedText = this.formatText(textContent);
      this.formattedTextContent = this.sanitizer.bypassSecurityTrustHtml(formattedText);
    }
  }

  // Helper to format text content with replacements
  formatText(text: string): string {
    if (!text) return '';
    return text
      // First, convert line breaks to <br> tags to preserve formatting
      .replace(/\n/g, '<br>')
      // Then do the other replacements
      .replace(/\{\{user\}\}/g, this.chatUI.userName) // Replace {{user}} with the user's name
      .replace(this.chatUI.aiName + ':', '') // Remove the AI's name from the message
      .replace(/"/ + this.chatUI.aiName + ':' + /"/, '') // Remove the AI's name from the message
      .replace(/\*(.*?)\*/g, '<em>$1</em>'); // Replace asterix with <em> tags, *text* -> <em>text</em>
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

  // Format agent final response (reuse formatText)
  formatAgentResponse(response: string): SafeHtml {
    if (!response) return '';
    const formatted = this.formatText(response);
    return this.sanitizer.bypassSecurityTrustHtml(formatted);
  }
}
