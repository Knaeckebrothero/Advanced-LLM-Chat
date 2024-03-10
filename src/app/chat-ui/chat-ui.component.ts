import { Component } from '@angular/core';
import { ChatService } from '../chat/chat.service';

@Component({
  selector: 'app-chat-ui',
  templateUrl: './chat-ui.component.html',
  styleUrls: ['./chat-ui.component.scss']
})
export class ChatUiComponent {
  
  // The inputField property is bound to the input field in the template.
  inputField: string = '';

  // Messages are managed by the ChatService and are passed to the ChatUiComponent via the observable.
  messages = this.chatService.messages;
  
  constructor(private chatService: ChatService) {}

  // The inputUserMessage method is called when the user submits a new message.
  inputUserMessage() {
    // The inputField property is checked to ensure that it is not empty.
    if (this.inputField !== '') {
      // The ChatService is used to add a new usermessage to the history.
      this.chatService.userInputMessage(this.inputField);
      
      // The input field is cleared.
      this.inputField = '';
    }
  }
}
