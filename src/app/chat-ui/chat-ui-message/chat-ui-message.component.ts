import { Component, Input } from '@angular/core';
import { Message } from '../message.model';

@Component({
  selector: 'app-chat-ui-message',
  templateUrl: './chat-ui-message.component.html',
  styleUrls: ['./chat-ui-message.component.scss']
})
export class ChatUiMessageComponent {
  
  // Pass the message object from the parent component
  @Input() message!: Message;

  // The formattedTime property converts the Unix timestamp to a Date object
  get formattedTime(): Date {
    // Convert Unix timestamp (seconds) to milliseconds and return as a new Date object
    return new Date(this.message.time * 1000);
  }
}
