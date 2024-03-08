import { Component, Input } from '@angular/core';
import { Message } from '../../data/interfaces/message-interface';

@Component({
  selector: 'app-chat-ui-message',
  templateUrl: './chat-ui-message.component.html',
  styleUrls: ['./chat-ui-message.component.scss']
})
export class ChatUiMessageComponent {
  
  // Pass the message object from the parent component
  @Input() message!: Message;
}
