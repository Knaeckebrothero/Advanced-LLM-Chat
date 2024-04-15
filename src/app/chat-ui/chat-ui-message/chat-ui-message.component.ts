import { Component, Input } from '@angular/core';
import { Message } from '../../data/interfaces/message';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { ChatUiComponent } from '../chat-ui.component';


@Component({
  selector: 'app-chat-ui-message',
  templateUrl: './chat-ui-message.component.html',
  styleUrls: ['./chat-ui-message.component.scss']
})
export class ChatUiMessageComponent {
  // Pass the message object from the parent component
  @Input() message!: Message;
  
  // Variables
  editing: boolean = false;
  backupContent!: string;

  constructor(private sanitizer: DomSanitizer, private chatUI: ChatUiComponent) { }

  // Function to replace prompt relevant elements to format the message
  formatMessage(message: string): SafeHtml {
    if(!this.editing) {}
    const replacedMessage = message
    .replace(/\{\{user\}\}/g, this.chatUI.userName) // Replace {{user}} with the user's name
    .replace(this.chatUI.aiName + ':', '') // Remove the AI's name from the message
    .replace(/"/ + this.chatUI.aiName + ':' + /"/, '') // Remove the AI's name from the message
    .replace(/\*(.*?)\*/g, '<em>$1</em>'); // Replace asterix with <em> tags, *text* -> <em>text</em>
    return this.sanitizer.bypassSecurityTrustHtml(replacedMessage);
  }

  // Edit message button
  editMessage() {
    console.log('Started editing message:', this.message.id);

    // Backup the current content
    this.backupContent = this.message.content;

    // Enable editing
    this.editing = true;
  }

  // Regenerate message button
  deleteMessage() {
    console.log('Deleting message:', this.message.id);

    
  }

  // Insert message above and regenerate button
  insertMessageAbove() {
    // Creates a new message above the current message
    this.chatUI.inputSystemMessage(this.message.id!);
    console.log('Inserting message above:', this.message.id);
  }

  /*
  Method for editing the messages content
  */

  updateContent(newContent: any) {
    this.message.content = newContent;
  }

  doneEditing() {
    console.log('Sucessfully edited message:', this.message.id);

    // Disable editing
    this.editing = false;

    // Trigger a request to update the message
    this.chatUI.changeMessage(this.message);
  }

  abortEditing() {
    console.log('Aborted editing message:', this.message.id);

    // Disable editing
    this.editing = false;

    // Restore the original content
    this.message.content = this.backupContent;
    this.backupContent = '';
  }
}
