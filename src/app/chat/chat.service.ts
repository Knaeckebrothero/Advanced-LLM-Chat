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
  conversation = new Conversation("default-conv-01", 0, [], '', []);
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
          this.conversation = new Conversation(
            conversation.id,
            conversation.messagesPartOfSummery,
            conversation.enviorementVariables,
            conversation.summary,
            conversation.participants
          );
          console.log("Conversation loaded!");
        } else {
          this.dbService.addConversation(this.conversation).then(() => {
            console.log("New conversation created!");
          });
        }
      });
    });
  }

  private getNonSummarizedMessages() {
    const messages = this.messagesSubject.getValue();
    // Start slicing from the index after the last summarized message
    return messages.slice(this.conversation.messagesPartOfSummery).map((message: Message) => {
      return {role: message.role, content: message.content};
    });
  }
  

  // Method to check if and update the conversation summary
  private async updateSummary(){

    console.log(this.getNonSummarizedMessages())
    // Convert the list of message objects to a JSON string
    const jsonString = JSON.stringify(this.getNonSummarizedMessages());

    // Check if the JSON string is long enough to be summarized
    if (jsonString.length > 16384) {
      console.log('Summarizing the conversation...');

      // Create a summary package to be sent to the API
      var summaryPackage = [
        {role: "system", content: "The conversation is summarized periodically to avoid going above the context window. You will now be provided with the current summary (of the previous conversation) and the messages that need to be summarized and incorporated into the summary. You will do your best to summarize the given messages and either add them to or incorporate them into the summary. Please be careful to not cut or alter any details of the previous summary when updating it."},
        {role: "system", content: `The current summary: ${this.conversation.summary}`}
      ];

      // Add the messages that are not part of the conversation summary to the summary package
      const messagesNotInSummary = this.getNonSummarizedMessages();
      summaryPackage = summaryPackage.concat();

      // Generate a summary
      await this.apiService.chatComplete(summaryPackage).then((response) => {
        // Update the conversation summary
        this.conversation.updateSummary(response.choices[0].message.content, messagesNotInSummary.length);
        console.log("Conversation summary updated!");
      });
    }
  }

  // Generate a new message
  private generate() {
    console.log("Preparing to generate a message...");
    // Update the conversation
    this.conversationPromt = this.conversation.getAsMessages()
    
    var generationMessages: Message[] = [];
    const messagesNotInSummary = this.getNonSummarizedMessages()

    // Combine the messages
    generationMessages = this.conversationPromt.concat(messagesNotInSummary);

    // Generate a message using the OpenAI API
    const newMessage = this.apiService.chatComplete(generationMessages).then((response) => {
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

    // Update the conversation
    this.updateSummary()
    });
  }
}
