import { Component, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { ChatService } from '../chat/chat.service';

@Component({
  selector: 'app-chat-ui',
  templateUrl: './chat-ui.component.html',
  styleUrls: ['./chat-ui.component.scss']
})
export class ChatUiComponent implements AfterViewChecked {
  
  // The messageContainer property is bound to the message container in the template.
  @ViewChild('messageContainer') private messageContainer!: ElementRef;
  
  // Variables
  userName: string = 'User';
  aiName: string = 'Assistant';

  // The inputField property is bound to the input field in the template.
  inputField: string = '';

  // Messages are managed by the ChatService and are passed to this component via observable.
  messages = this.chatService.messages;
  
  // Constructor
  constructor(private chatService: ChatService) { 
    const credentials = this.chatService.getConversationCredentials();
    this.userName = credentials.user;
    this.aiName = credentials.ai;
  }

  // Method to scroll to the bottom of the chat window.
  private scrollToBottom(): void {
    try {
      this.messageContainer.nativeElement.scrollTop = this.messageContainer.nativeElement.scrollHeight;
    } catch(err) { }
  }

  // Use the AfterViewChecked lifecycle hook to trigger the scroll method.
  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  // The inputUserMessage method is called when the user submits a new message.
  inputUserMessage() {
    // The inputField property is checked to ensure that it is not empty.
    if (this.inputField !== '') {
      // The ChatService is used to add a new usermessage to the history.
      this.chatService.userInputMessage(this.inputField);

      this.scrollToBottom();
      
      // The input field is cleared.
      this.inputField = '';
    }
  }
}
