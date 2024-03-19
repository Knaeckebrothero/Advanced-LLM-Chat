import { Component, Input } from '@angular/core';
import { Message } from '../../data/interfaces/message';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

@Component({
  selector: 'app-chat-ui-message',
  templateUrl: './chat-ui-message.component.html',
  styleUrls: ['./chat-ui-message.component.scss']
})
export class ChatUiMessageComponent {
  
  // Pass the message object from the parent component
  @Input() message!: Message;

  constructor(private sanitizer: DomSanitizer) { }

  // Function to replace text enclosed in asterisks with <em> tags
  formatMessage(message: string): SafeHtml {
    const replacedMessage = message
    .replace(/\*(.*?)\*/g, '<em>$1</em>');
    return this.sanitizer.bypassSecurityTrustHtml(replacedMessage);
  }
}
