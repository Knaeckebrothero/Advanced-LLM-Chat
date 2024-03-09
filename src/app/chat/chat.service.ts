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
  private conversation = new Conversation(0, 
    [], 
    'This is a new conversation. There is no summary yet.', 
    []);

  // Inject the DataService and load the messages from the database
  constructor(private dbService: DBService, private apiService: OpenAIService) {
    // Wait for the database to be ready
    this.dbService.getDatabaseReadyPromise().then(() => {
      // Load the messages from the database once it has been started
      console.log("Loading messages from the database...");
      this.dbService.getAllMessages().then((messages: Message[]) => {
        // Add the messages to the messages array
        this.messagesSubject.next(messages);
      });
      console.log("Messages loaded!");
    });
  }

  // Generate a new message
  private generate() {
    // Extract the messages not part of the conversation summery
    const messages = this.messagesSubject.getValue();
    const messagesNotInSummary = messages.slice(messages.length - this.conversation.messagesPartOfSummery).map((message: Message) => {
      return {role: message.user, content: message.content};
    });
  
    // Generate a message using the OpenAI API, including only the last 10 messages
    this.apiService.chatComplete([
      {role: "system", content: this.conversation.conversationPromt},
      ...messagesNotInSummary
    ]);
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

    // Add the message to the database
    this.dbService.addMessage(newMessage);

    // Add the message to the messages array
    this.messagesSubject.next([...this.messagesSubject.getValue(), newMessage]);

    // Generate a response
    const response = this.generate();
    console.log(response);
  }
}
