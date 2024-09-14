import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { Message } from '../data/interfaces/message';
import { DBService } from '../data/db.service';
import { Conversation } from '../data/interfaces/conversation';


@Injectable({
  providedIn: 'root'
})
export class ChatService {
  // The conversation this service is managing
  private conversation = {id: 0, name: "", participants: []};

  // The ChatService is responsible for managing and exposing the messages.
  private messagesSubject: BehaviorSubject<Message[]> = new BehaviorSubject<Message[]>([]);
  public messages: Observable<Message[]> = this.messagesSubject.asObservable();

  // Constructor
  constructor(private dbService: DBService) {
    // Wait for the database to be ready
    this.dbService.getDatabaseReadyPromise().then(() => {
      // Load the default conversation from the database
      this.dbService.getConversation(1).then((conversation: any) => {
        // Check if the conversation exists
        if (conversation != 0) {
          // Load the conversation messages from the database
          this.dbService.getMessagesByConversationId(conversation.id).then((messages: Message[]) => {
            // Check if the conversation has any messages
            if(messages !== undefined) {
              this.addMessage(messages);
            }
            console.log("Conversation loaded!");
          });
        } else {          
          // Add the default conversation to the database
          this.dbService.addConversation({id: 1, name: "default conversation", participants: ["user"]}).then(() => {
            console.log("New conversation created!");
          });
        }
      });
    });
  }

  // Add one or more messages to the conversation
  public addMessage(message: Message | Message[]) {
    // Check if the message is an array
    if (Array.isArray(message)) {
      // Sort the messages by time
      message.sort((a, b) => a.time!.getTime() - b.time!.getTime())

      // Add each message to the messages array
      this.messagesSubject.next([...this.messagesSubject.getValue(), ...message]);
    } else {
    // Add the message to the messages array
    this.messagesSubject.next([...this.messagesSubject.getValue(), message]);
    }
  }

  // Patch a message in the conversation
  public patchMessage(content: string) {
    console.log('Editing message content');
  }

  // Regenerate a message in the conversation
  public regenerateMessage(message: Message) {
    console.log('Regenerating message');
  }

  // Delete a message from the conversation
  public deleteMessage(messageId: number) {
    console.log('Deleting message with ID:', messageId);
  }

  // Generate a message
  public generateMessage(participant?: string) {
    if (participant) {
      console.log(`Generating message for ${participant}`);
    } else {
    console.log('Generating message');
    }
  }
}
