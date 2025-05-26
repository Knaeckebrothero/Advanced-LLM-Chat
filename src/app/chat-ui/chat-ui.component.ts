import { Component, ViewChild, ElementRef, AfterViewChecked, OnInit, OnDestroy } from '@angular/core';
import { ChatService } from '../chat/chat.service';
import { Message } from '../data/objects/message';
import { Conversation } from '../data/objects/conversation'; // Import Conversation
import { User } from '../data/objects/user'; // Import User
import { Subscription } from 'rxjs';


@Component({
  selector: 'app-chat-ui',
  templateUrl: './chat-ui.component.html',
  styleUrls: ['./chat-ui.component.scss'],
  standalone: false // Assuming this is intended for a non-standalone setup
})
export class ChatUiComponent implements OnInit, AfterViewChecked, OnDestroy {

  // The messageContainer property is bound to the message container in the template.
  @ViewChild('messageContainer') private messageContainer!: ElementRef;

  // Variables
  // These will be dynamically set based on the current user and conversation
  userName: string = 'User';
  aiName: string = 'Assistant';
  currentConversationInfo: string = 'Loading conversation...'; // For display

  // The inputField property is bound to the input field in the template.
  inputField: string = '';

  // Messages are managed by the ChatService and are passed to this component via observable.
  // Corrected to use messages$
  messages$ = this.chatService.messages$; // Use the Observable directly in the template with async pipe

  private conversationSubscription: Subscription | undefined;
  private currentUserSubscription: Subscription | undefined; // If ChatService exposes currentUser

  // Constructor
  constructor(private chatService: ChatService) {}

  ngOnInit() {
    // Subscribe to the current conversation to update UI elements if needed
    this.conversationSubscription = this.chatService.currentConversation$.subscribe(conversation => {
      if (conversation) {
        this.currentConversationInfo = `Chat: ${conversation.name} (ID: ${conversation.id || 'New'})`;
        // Attempt to set user and AI names from participants if logic allows
        // This is a simple example; your participant logic might be more complex
        if (conversation.participants.length > 0) {
          // Heuristic: find a participant that isn't the AI, assume it's the user
          // This might need to be tied to the actual logged-in user's name from ChatService.currentUser
          const humanParticipant = conversation.participants.find(p => p.toLowerCase() !== this.aiName.toLowerCase());
          if (humanParticipant) {
            this.userName = humanParticipant;
          }
        }
        const assistantParticipant = conversation.participants.find(p => p.toLowerCase() === this.aiName.toLowerCase() || p.toLowerCase().includes('assistant'));
        if (assistantParticipant) {
          this.aiName = assistantParticipant; // Update AI name if it's dynamic from participants
        }

      } else {
        this.currentConversationInfo = 'No active conversation.';
      }
    });

    // If ChatService exposes the current user, you could subscribe to it:
    // Example: (Assuming ChatService has a public currentUser$ observable)
    // this.currentUserSubscription = this.chatService.currentUser$.subscribe(user => {
    //   if (user) {
    //     this.userName = user.name; // More reliable way to set userName
    //   }
    // });
  }

  // Method to scroll to the bottom of the chat window.
  private scrollToBottom(): void {
    try {
      if (this.messageContainer?.nativeElement) {
        this.messageContainer.nativeElement.scrollTop = this.messageContainer.nativeElement.scrollHeight;
      }
    } catch(err) {
      // console.error("Error scrolling to bottom:", err);
    }
  }

  // Use the AfterViewChecked lifecycle hook to trigger the scroll method.
  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  // Utility function to detect mobile devices
  isMobileDevice(): boolean {
    // This check can be simplified or made more robust if needed
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  }

  // Function to handle Enter key in textarea
  handleEnterKeyPress(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      if (!event.shiftKey && !this.isMobileDevice()) {
        // Desktop: Enter sends, Shift+Enter new line
        this.inputUserMessage();
        event.preventDefault();
      } else if (event.shiftKey && !this.isMobileDevice()) {
        // Desktop: Shift+Enter, allow new line (do nothing here, browser default)
      } else if (this.isMobileDevice() && !event.shiftKey) { // Mobile: Enter could be configured
        // For mobile, current logic prevents default. If you want Enter to send on mobile:
        this.inputUserMessage(); // Uncomment this if mobile Enter should send
        event.preventDefault();
        // If mobile Enter should create a new line, then do nothing or just:
        // this.inputField += '\n'; // Manually add newline if needed, then preventDefault
      }
    }
  }

  // The addMessage method is called when the user submits a new message.
  inputUserMessage() {
    const trimmedInput = this.inputField.trim();
    if (trimmedInput !== '') {
      // The ChatService is used to add a new user message.
      // The second argument to sendMessage (roleName) defaults to 'user' in ChatService,
      // and ChatService will use the current user's name.
      this.chatService.sendMessage(trimmedInput);
      console.log('User message sent to service:', trimmedInput);

      // The input field is cleared.
      this.inputField = '';
      // Scrolling to bottom will be handled by ngAfterViewChecked
    }
  }

  // Generate a new AI message
  // Corrected to use generateAiResponseMessage
  generateAiMessage() {
    // The aiName here is from the component's property.
    // ChatService.generateAiResponseMessage will use this participant name.
    this.chatService.generateAiResponseMessage(this.aiName);
    console.log(`AI message generation requested for participant: ${this.aiName}`);
  }

  /*
  // The inputSystemMessage method is called to add a new system message
  inputSystemMessage(messageId: number) {
    // The ChatService is used to add a new system message to the history.
    // this.chatService.systemAddMessage(messageId); // Assuming systemAddMessage exists in ChatService
  }
  */

  // Method to delete a message
  deleteMessage(message: Message) { // Changed parameter to Message for easier access to ID
    if (message.id !== null && message.id !== undefined) { // Ensure message.id is valid
      this.chatService.deleteMessage(message.id);
    } else {
      console.warn("Attempted to delete a message without a valid ID.");
    }
  }

  // Method to change a message
  patchMessage(message: Message) {
    if (message.id !== null && message.id !== undefined) { // Ensure message.id is valid
      const newContent = prompt("Enter the new content for the message:", message.content);
      if (newContent !== null && newContent.trim() !== '') { // Check if user provided content
        this.chatService.patchMessage(message.id, newContent);
      }
    } else {
      console.warn("Attempted to patch a message without a valid ID.");
    }
  }

  ngOnDestroy() {
    if (this.conversationSubscription) {
      this.conversationSubscription.unsubscribe();
    }
    if (this.currentUserSubscription) {
      this.currentUserSubscription.unsubscribe();
    }
  }
}
