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

  // 
  constructor(private sanitizer: DomSanitizer, private chatUI: ChatUiComponent) { }

  // Function to replace prompt relevant elements to format the message
  formatMessage(message: string): SafeHtml {
    const replacedMessage = message
    .replace(/\{\{user\}\}/g, this.chatUI.userName) // Replace {{user}} with the user's name
    .replace(this.chatUI.aiName + ':', '') // Remove the AI's name from the message
    .replace(/"/ + this.chatUI.aiName + ':' + /"/, '') // Remove the AI's name from the message
    .replace(/\*(.*?)\*/g, '<em>$1</em>'); // Replace asterix with <em> tags, *text* -> <em>text</em>
    return this.sanitizer.bypassSecurityTrustHtml(replacedMessage);
  }

  editMessage() {
    // Logic to enable editing the message's content
    console.log('Editing message:', this.message.id);
  }

  regenerateMessage() {
    // Logic for regenerating the message content, perhaps with AI assistance
    console.log('Regenerating message:', this.message.id);
  }

  insertMessageAbove() {
    // Logic for inserting a new message below the current one
    console.log('Inserting message above:', this.message.id);
  }
}
