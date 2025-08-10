// src/app/chat-ui/chat-ui-message/chat-ui-message.component.ts
import { Component, Input, OnChanges, SimpleChanges, Renderer2 } from '@angular/core';
import { Message, VoiceContent } from '../../data/objects/message';
import { DomSanitizer, SafeHtml, SafeUrl } from '@angular/platform-browser';
import { ChatUiComponent } from '../chat-ui.component';
import { FileType, FilePreviewUtil, FilePreview } from '../../data/objects/file-preview';

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

  constructor(private sanitizer: DomSanitizer, private chatUI: ChatUiComponent,private renderer: Renderer2) { }

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

  // FIX: Removed 'private' to make it accessible from the template
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

  // Helper to format duration
  formatDuration(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }

  getVoiceMessageUrl(message: Message<VoiceContent>): SafeUrl {
    const src = `data:${message.content.mimeType};base64,${message.content.audioData}`;
    return this.sanitizer.bypassSecurityTrustUrl(src);
  }

  getAttachmentIcon(type: FileType): string {
    return FilePreviewUtil.getFileIcon(type);
  }

  onAttachmentClick(event: MouseEvent, attachment: FilePreview): void {
    if (attachment.type === 'image' && attachment.preview) {
      event.preventDefault();
      this.openImagePopup(attachment.preview);
    }
  }

  createDownloadUrl(file: File): SafeUrl {
    const objectUrl = URL.createObjectURL(file);
    return this.sanitizer.bypassSecurityTrustUrl(objectUrl);
  }

  openImagePopup(imageUrl: string): void {
    const overlay = this.renderer.createElement('div');
    this.renderer.addClass(overlay, 'image-popup-overlay');
    const img = this.renderer.createElement('img');
    this.renderer.addClass(img, 'image-popup-content');
    this.renderer.setAttribute(img, 'src', imageUrl);
    this.renderer.appendChild(overlay, img);
    this.renderer.appendChild(document.body, overlay);
    this.renderer.listen(overlay, 'click', () => {
      this.renderer.removeChild(document.body, overlay);
    });
  }

  editMessage() {
    if (!this.message.isText()) return;
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
}
