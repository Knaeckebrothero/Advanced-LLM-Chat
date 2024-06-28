import { Component, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { ChatService } from '../chat/chat.service';
import { Message } from '../data/interfaces/message';

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

  // Utility function to detect mobile devices
  isMobileDevice(): boolean {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  }

  // Function to handle Enter key in textarea
  handleEnterKeyPress(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      if (this.isMobileDevice()) {
        // It's a mobile device, allow line breaks on Enter
        event.preventDefault(); // This line might be removed if you want to allow new lines
      } else {
        // It's not a mobile device, send the message
        this.inputUserMessage();
        event.preventDefault(); // Prevents new line even on desktop after sending message
      }
    }
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

  // Generate a new message
  generateMessage() {
    console.log('Generating message');
    this.chatService.generateMessage();
  }

  // The inputSystemMessage method is called to add a new system message
  inputSystemMessage(messageId: number) {
    // The ChatService is used to add a new system message to the history.
    this.chatService.systemAddMessage(messageId);
  }

  // Method to delete a message
  deleteMessage(messageId: number) {
    // Call the ChatService to delete the message
    this.chatService.deleteMessage(messageId);
  }

  // Method to change a message
  changeMessage(message: Message) {
    // Call the ChatService to alter the message
    this.chatService.alterMessage(message)
  }
}
