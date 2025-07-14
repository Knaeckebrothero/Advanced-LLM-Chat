import { Component, Input } from '@angular/core';
import { Message } from '../../data/objects/message';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { ChatUiComponent } from '../chat-ui.component';


@Component({
  selector: 'app-chat-ui-message',
  templateUrl: './chat-ui-message.component.html',
  styleUrls: ['./chat-ui-message.component.scss'],
  standalone: false
})
export class ChatUiMessageComponent {
  // Pass the message object from the parent component
  @Input() message!: Message;

  // Variables
  editing: boolean = false;
  backupContent!: string;

  constructor(private sanitizer: DomSanitizer, private chatUI: ChatUiComponent) { }

  // Function to replace prompt relevant elements to format the message
  formatMessage(message: Message): SafeHtml {
    if(!this.editing) {
      // Handle different message types
      if (message.isVoice()) {
        // Format voice message
        const duration = this.formatDuration(message.content.duration);
        let voiceHtml = `
          <div class="voice-message">
            <div class="voice-header">
              <span class="voice-icon">🎤</span>
              <span class="voice-duration">Voice message (${duration})</span>
            </div>
        `;

        // Add transcript if available
        if (message.content.transcript) {
          voiceHtml += `
            <div class="voice-transcript">
              <em>${this.formatTextContent(message.content.transcript)}</em>
            </div>
          `;
        }

        // TODO: Add audio player controls when backend supports audio streaming
        // voiceHtml += `<audio controls src="data:${message.content.mimeType};base64,${message.content.audioData}"></audio>`;

        voiceHtml += '</div>';

        return this.sanitizer.bypassSecurityTrustHtml(voiceHtml);
      }

      // Handle text messages (default)
      const textContent = message.getDisplayContent();
      const formattedText = this.formatTextContent(textContent);

      // Add file attachments if present
      let html = formattedText;
      if (message.hasAttachments() && message.attachments) {
        html += '<div class="message-attachments">';
        message.attachments.forEach(attachment => {
          html += `
            <div class="attachment-item">
              <span class="attachment-icon">📎</span>
              <span class="attachment-name">${attachment.name}</span>
              <span class="attachment-size">(${attachment.sizeFormatted})</span>
            </div>
          `;
        });
        html += '</div>';
      }

      return this.sanitizer.bypassSecurityTrustHtml(html);
    }

    // Return the raw message when editing to preserve line breaks
    return message.getDisplayContent();
  }

  // Helper to format text content with replacements
  private formatTextContent(text: string): string {
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
  private formatDuration(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
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

  // Regenerate message button
  deleteMessage() {
    this.chatUI.deleteMessage(this.message.id!);
  }

  // Insert message above and regenerate button
  insertMessageAbove() {
    console.log('Inserting message above:', this.message.id);
    //this.chatUI.inputSystemMessage(this.message.id!);
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
      this.chatUI.chatService.patchMessage(this.message.id!, this.backupContent);
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
}
