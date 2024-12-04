import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { Message } from '../data/interfaces/message';
import { DBService } from '../data/db.service';
import { ApiService } from '../api/api.service';
import { ConversationConverter } from '../data/interfaces/conversation';


@Injectable({
  providedIn: 'root'
})
export class ChatService {
  // The conversation this service is managing
  private conversation = {id: 1, userId: 1, name: "default", participants: ["user"]}

  // The ChatService is responsible for managing and exposing the messages.
  private messagesSubject: BehaviorSubject<Message[]> = new BehaviorSubject<Message[]>([]);
  public messages: Observable<Message[]> = this.messagesSubject.asObservable();

  // Constructor
  constructor(
    private dbService: DBService, 
    private apiService: ApiService
  ) {
    // Wait for the database to be ready
    this.dbService.getDatabaseReadyPromise().then(() => {
      // Load the default conversation from the database
      this.dbService.getConversation(this.conversation.id).then((conversation: any) => {
        // Check if the conversation exists
        if (conversation != undefined) {
          // Load the conversation messages from the database
          this.dbService.getMessagesByConversationId(conversation.id).then((messages: Message[]) => {
            // Check if the conversation has any messages
            if(messages !== undefined) {
              // Sort the messages by time
              messages.sort((a, b) => a.time!.getTime()! - b.time!.getTime())

              // Add each message to the messages array
              this.messagesSubject.next([...this.messagesSubject.getValue(), ...messages]);
            }
            console.log("Conversation loaded!");
          });
        } else {          
          // Add the default conversation to the database
          this.dbService.addConversation(this.conversation).then(() => {
          console.log("New conversation created!");
          });
        }

        // Check for new messages
        this.refreshConversation();
      });
    });
  }

  // Refresh the conversation
private async refreshConversation() {
  try {
    const conversations = await this.apiService.getConversationsByUser(1);
    if (conversations.length === 0) {
      console.log('No conversation found.');
      return;
    }

    const currentMessages = this.messagesSubject.getValue();
    const localHash = ConversationConverter.toApiConversationCheck(
      this.conversation, 
      currentMessages.slice(-20)
    ).hashsum;

    if (localHash !== conversations[0].hashsum) {
      console.log('Conversation hashes didnt match!');
      // TODO: Fetch the conversation
      // this.addMessage(messages);
    }
  } catch (error) {
    console.error('Error refreshing conversation:', error);
    throw error;
  }
}

  // TODO: Implement a way to call the refreshConversation method at regular intervals (e.g. every minute and when the app is opened)

  // Add one or more messages to the conversation
  public addMessage(message: Message | Message[]) {
    // Check if the message is an array
    if (Array.isArray(message)) {
      // Add the conversation ID to each message
      message.forEach((message) => {
        message.conversationId = this.conversation.id;
      });

      // Sort the messages by time
      message.sort((a, b) => a.time!.getTime()! - b.time!.getTime())

      // Add each message to the messages array
      this.messagesSubject.next([...this.messagesSubject.getValue(), ...message]);

      // Add the messages to the database
      message.forEach((message) => {
        this.dbService.addMessage(message);
      });
    } else {
      // Add the conversation ID to the message
      message.conversationId = this.conversation.id;

      // Send the messages to the backend
      this.apiService.sendMessage(message).then((msg) => {
        // Add the message to the database
        this.dbService.addMessage(msg);

        // Add the message to the messages array
        this.messagesSubject.next([...this.messagesSubject.getValue(), msg]);
      });
    }
  }

  // Generate a message
  public async generateMessage(participant: string) {
    const currentMessages = this.messagesSubject.getValue();
    const lastMessage = currentMessages[currentMessages.length - 1];

    try {
      const generatedMessage = await this.apiService.generateMessage(lastMessage, participant);
      
      // Add to local state and database
      this.addMessage(generatedMessage);
    } catch (error) {
      console.error('Error generating message:', error);
      throw error;
    }
  }

  // Patch a message in the conversation
  public async patchMessage(messageId: number, content: string) {
    try {
      // Get the conversation ID
      const conversationId = this.conversation.id;

      // Call the API to patch the message
      const updatedMessage = await this.apiService.patchMessage(conversationId, messageId, content);
      
      // Update the message in the local state
      const currentMessages = this.messagesSubject.getValue();
      const messageIndex = currentMessages.findIndex(msg => msg.id === messageId);
      
      if (messageIndex !== -1) {
        currentMessages[messageIndex] = { ...currentMessages[messageIndex], ...updatedMessage };
        this.messagesSubject.next([...currentMessages]);
        
        // Update in database
        await this.dbService.updateMessage(currentMessages[messageIndex]);
      }
    } catch (error) {
      console.error('Error patching message:', error);
      throw error;
    }
  }

  // Delete a message from the conversation
  public async deleteMessage(messageId: number) {
    try {
      await this.apiService.deleteMessage(this.conversation.id, messageId);
      
      // Remove from local state
      const currentMessages = this.messagesSubject.getValue();
      const updatedMessages = currentMessages.filter(msg => msg.id !== messageId);
      this.messagesSubject.next(updatedMessages);
      
      // Remove from database
      await this.dbService.deleteMessage(messageId);
    } catch (error) {
      console.error('Error deleting message:', error);
      throw error;
    }
  }

  // Regenerate a message in the conversation
  public regenerateMessage(message: Message) {
    console.log('Regenerating message');
  }
}
