import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { Message } from '../data/objects/message';
import { DBService } from '../data/db.service';
import { ApiService } from '../api/api.service';
import { Conversation } from '../data/objects/conversation';


@Injectable({
  providedIn: 'root'
})
export class ChatService {
  // The conversation this service is managing
  private conversation: Conversation = new Conversation(1, 1, "default", ["user"])

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
    // TODO: Add a way to handle / load conversations that don't exist on the client side
    try {
      const conversations = await this.apiService.getConversationsByUser();
      if (conversations.length === 0) {
        console.log('No refresh of conversations nessessary!');
        return;
      }
      const hashsum = await this.conversation.computeHash(this.dbService);

      if (hashsum !== conversations[0].hashsum) {
        console.log('Conversation hashes didnt match!');

        console.log('Refreshing conversation:', conversations[0]);

        // Get the latest messages and add them to the conversation
        this.apiService.getConversationMessages(conversations[0].id, 20).then((messages) => {
          console.log('Adding messages to conversation:', messages);
          this.addMessage(messages);
        });
      }
    } catch (error) {
      console.error('Error refreshing conversation:', error);
      throw error;
    }
  }

  // TODO: Implement a way to call the refreshConversation method at regular intervals (e.g. every minute and when the app is opened)

  // Add one or more messages to the conversation
  private addMessage(message: Message | Message[]) {
    // Check if the message is an array
    if (Array.isArray(message)) {
      // Add the conversation ID to each message
      //message.forEach((message) => {
      //  message.conversationId = this.conversation.id;
      //});

      // Sort the messages by time
      message.sort((a, b) => a.time!.getTime()! - b.time!.getTime())

      // Add each message to the messages array
      this.messagesSubject.next([...this.messagesSubject.getValue(), ...message]);

      // Add the messages to the database
      message.forEach((message) => {
        this.dbService.addMessage(message);
      });
    } else {
      // Add the message to the database
      this.dbService.addMessage(message);

      // Add the message to the messages array
      this.messagesSubject.next([...this.messagesSubject.getValue(), message]);
    }
  }

  // Send a message
  public async sendMessage(content: string, roleName: string = 'user') {
    // Create a new message object
    const message = new Message({
      id: Math.floor(new Date().getTime() / 1000) ,
      conversationId: this.conversation.id,
      roleName: roleName,
      content: content,
      time: new Date()
    });

    // Add the message to the conversation
    this.addMessage(message);

    // Send the message to the backend
    this.apiService.sendMessage(message).then((response) => {
      if(message.id != response.id){
        console.error('Message ID mismatch:', message.id, response.id);

        // Update the message in the local state
        this.dbService.addMessage(response);
        this.dbService.deleteMessage(message.id);

        console.log('Message ID mismatch resolved:', message.id, response.id);
      } else {
        console.log('Message sent:', response);
      }
    });
  }

  // Generate a message
  public async generateMessage(participant: string) {
    const currentMessages = this.messagesSubject.getValue();
    // Convert the last message to a Message instance if it's not already one
    const lastMessage = currentMessages[currentMessages.length - 1] instanceof Message 
    ? currentMessages[currentMessages.length - 1]
    : new Message(currentMessages[currentMessages.length - 1]);

    console.log('Generating message:', lastMessage, participant);

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
        currentMessages[messageIndex] = new Message({
          ...currentMessages[messageIndex],
          ...updatedMessage,
        });
        // currentMessages[messageIndex] = { ...currentMessages[messageIndex], ...updatedMessage };
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
