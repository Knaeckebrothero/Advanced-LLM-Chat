import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { Message } from '../data/interfaces/message';
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

  // Variables
  conversation = new Conversation("default-conv-01", 0, [], 'This is a new conversation. There is no summary yet.', []);
  conversationPromt: Message[] = [];  

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

  // Convert a message to the format used by the openai API
  private converMessage(message: Message) {
    return {
      role: message.role,
      content: message.content
    };
  }

  // Convert a conversation to an array of messages used by the openai API
  private convertConversation(): Message[] {
    // Prepare the messages array
    const messages: Message[] = [];

    // Prepare the enviorement variables
    var envVarStr: string = 'A list of environment variables up to this point:\n';
    for(let i = 0; i < this.conversation.enviorementVariables.length; i++) {
      envVarStr += `${this.conversation.enviorementVariables[i].name}: ${this.conversation.enviorementVariables[i].value}\n`;
    };

    // Convert the conversation variables to system messages
    // messages.push({role: "system", content: "The following data is about the course of the conversation. To stay within the context window and provide some additional information to keep the conversation consistent, the conversation will be summarized and only the last few messages will be provided."});
    // messages.push({role: "system", content: `A list of the characters participating in the conversation or scenario: ${this.conversation.participants}`});
    // messages.push({role: "system", content: `Summary of the conversation up to this point: ${this.conversation.summary}`});
    // messages.push({role: "system", content: envVarStr});
    // messages.push({role: "system", content: "The last few messages of the conversation (these are not part of the summary):"});

    return messages;
  }

  // Generate a new message
  private generate() {
    console.log("Preparing to generate a message...");
    // Update the conversation
    this.conversationPromt = this.convertConversation()
    
    // Extract the messages not part of the conversation summery
    var messages = this.messagesSubject.getValue();
    const messagesNotInSummary = messages.slice(- this.conversation.messagesPartOfSummery).map((message: Message) => {
      return {role: message.role, content: message.content};
    });

    // Combine the messages
    messages = this.conversationPromt.concat(messagesNotInSummary);

    // Generate a message using the OpenAI API
    const newMessage = this.apiService.chatComplete(messages).then((response) => {
      console.log("Message generated!");
      console.log(response);

      // Create a new message object
      const message = {
        content: response.choices[0].message.content,
        role: response.choices[0].message.role,
        time: new Date()
      };
      return message;
    });
    return newMessage;
  }

  // Add a new message to the messages array and save it in the db
  public userInputMessage(content: any) {
    // Create a new message object
    const newMessage = {
      content: content,
      role: 'user',
      time: new Date()
    };

    // Add the message to the database and messages array
    this.dbService.addMessage(newMessage);
    this.messagesSubject.next([...this.messagesSubject.getValue(), newMessage]);
    console.log("Usermessage added!");

    // Generate a response
    this.generate().then((generatedMessage) => {
    // Add the message to the messages array
    this.messagesSubject.next([...this.messagesSubject.getValue(), generatedMessage]);

    // Save the message in the database
    this.dbService.addMessage(generatedMessage);
    });
  }
}
