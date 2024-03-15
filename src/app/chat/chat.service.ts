import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { Message } from '../data/interfaces/chat-message';
import { DBService } from '../data/db.service';
import { OpenAIService } from '../api/api-openai.service';
import { Conversation } from '../chat/conversation';


@Injectable({
  providedIn: 'root'
})
export class ChatService {
  // The ChatService is responsible for managing the messages array and exposing it as an observable.
  private messagesSubject = new BehaviorSubject<Message[]>([]);
  public messages: Observable<Message[]> = this.messagesSubject.asObservable();

  // Declare a conversation
  private conversation = new Conversation("default-conv-01", 0, [], 
    'This is a new conversation. There is no summary yet. Keep in mind that the ohter attributes might not be filled as well and please do not mention this.', 
    []);

  // Inject the DataService and load the messages from the database
  constructor(private dbService: DBService, private apiService: OpenAIService) {
    // Wait for the database to be ready
    this.dbService.getDatabaseReadyPromise().then(() => {
      // Load the messages from the database once it has been started
      this.dbService.getAllMessages().then((messages: Message[]) => {
        // Add the messages to the messages array
        this.messagesSubject.next(messages);
      });
      console.log("Messages loaded!");

      // Load the conversation from the database
      this.dbService.getConversation("default-conv-01").then((conversation: any) => {
        if (conversation !== undefined) {
          this.conversation = conversation;
          console.log("Conversation loaded!");
        } else {
          this.dbService.addConversation(this.conversation).then(() => {
            console.log("New conversation created!");
          });
        }
      });
    });
  }

  // Generate a new message
  private generate() {
    console.log("Preparing to generate a message...");
    
    // Extract the messages not part of the conversation summery
    const messages = this.messagesSubject.getValue();
    const messagesNotInSummary = messages.slice(messages.length - this.conversation.messagesPartOfSummery).map((message: Message) => {
      return {role: message.user, content: message.content};
    });
  
    // Generate a message using the OpenAI API
    this.apiService.chatComplete([
      {role: "system", content: this.conversation.conversationPromt},
      ...messagesNotInSummary
    ]).then((response) => {
      console.log("Message generated!");
      console.log(response);
      
      // Create a new message object
      const newMessage = {
        content: response.choices[0].message.content,
        user: response.choices[0].message.role,
        time: new Date()
      };

      // Add the message to the messages array
      this.messagesSubject.next([...this.messagesSubject.getValue(), newMessage]);

      // Save the message in the database
      this.dbService.addMessage(newMessage);
    });
  }
  
  /*
  The ChatService exposes a veriety of methods for managing the message history.
  */

  // Add a new message to the messages array and save it in the db
  public userInputMessage(content: any) {
    // Create a new message object
    const newMessage = {
      content: content,
      user: 'user',
      time: new Date()
    };

    // Add the message to the database and messages array
    this.dbService.addMessage(newMessage);
    this.messagesSubject.next([...this.messagesSubject.getValue(), newMessage]);
    console.log("Usermessage added!");

    // Generate a response
    this.generate();
  }
}
