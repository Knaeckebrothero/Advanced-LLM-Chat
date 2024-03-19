import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { Message } from '../data/interfaces/message';
import { DBService } from '../data/db.service';
import { OpenAIService } from '../api/api-openai.service';
import { Conversation } from '../chat/conversation';
import { Agent } from '../data/interfaces/agent';


@Injectable({
  providedIn: 'root'
})
export class ChatService {
  // The ChatService is responsible for managing the messages array and exposing it as an observable.
  private messagesSubject = new BehaviorSubject<Message[]>([]);
  public messages: Observable<Message[]> = this.messagesSubject.asObservable();

  // Variables
  conversation = new Conversation(
    "default-conv-01", 
    0, 
    [], 
    'This is a new conversation, there is no summary of prior messages!', 
    []
  );
  conversationPromt: Message[] = [];
  agent: Agent = {role: "assistant", prompt: "You are a helpfull Assistant."};

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
        if (conversation != undefined) {
          this.conversation = new Conversation(
            conversation.id,
            conversation.messagesPartOfSummary,
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

      // Load the agent from the database
      this.dbService.getAgent("default-agent-01").then((agent: any) => {
        if (agent !== undefined) {
          this.agent = agent;
          console.log("Agent loaded!");
        } else {
          console.log("Agent not found!");
        }
      });
    });
  }

  private getNonSummarizedMessages(messages: Message[]) {
    // Start slicing from the index after the last summarized message
    return messages.slice(this.conversation.messagesPartOfSummary).map((message: Message) => {
      return {role: message.role, content: message.content};
    });
  }
  
  // Method to check if and update the conversation summary
  private async updateSummary(){
    const currentMessages = this.messagesSubject.getValue();
    const messagesNotInSummary = this.getNonSummarizedMessages(currentMessages);

    // Log the current state of the conversation
    console.log({
      totalMessages: currentMessages.length, 
      messagesInSummary: this.conversation.messagesPartOfSummary, 
      messagesNotInSummary: messagesNotInSummary.length,
    });

    // Check if the JSON string is long enough to be summarized
    if (JSON.stringify(messagesNotInSummary).length > 10240 && currentMessages.length - this.conversation.messagesPartOfSummary > 4) {
      console.log('Summarizing the conversation...');

      // Create a summary package to be sent to the API
      var summaryPackage = [{role: "system", content: this.agent.prompt}];

      // Add the messages that are not part of the conversation summary to the summary package
      summaryPackage = summaryPackage.concat(messagesNotInSummary.concat([
        {role: "system", content: `Your task now is to generate a summary of the ongoing conversation. 
        This involves periodically updating the summary to include new information while ensuring the coherence and accuracy of the overall context. 
        When updating, carefully integrate new details into the existing summary without omitting crucial elements or introducing inaccuracies. 
        Maintain the essence of the conversation, focusing on key points, decisions, and insights. \n
        Current summary: [${this.conversation.summary}].\n Please update this summary by incorporating the most recent exchanges, highlighting any new developments or conclusions. 
        Ensure the updated summary remains clear and succinct.`}
      ]));

      // Generate a summary
      await this.apiService.chatComplete(summaryPackage).then((response) => {
        // Update the conversation summary
        this.conversation.updateSummary(response.choices[0].message.content, currentMessages.length);
        console.log("Conversation summary updated!");
      });
    }
  }

  // Generate a new message
  private generate() {
    console.log("Preparing to generate a message...");
    // Update the conversation
    this.conversationPromt = this.conversation.getAsMessages()
    
    var generationMessages: Message[] = [
      {role: "system", content: this.agent.prompt}];
    const messagesNotInSummary = this.getNonSummarizedMessages(this.messagesSubject.getValue())

    if (messagesNotInSummary.length < 4) {
      // Get the last 4 messages
      generationMessages = generationMessages.concat(
        this.conversationPromt.concat(
          this.messagesSubject.getValue().slice(-4).map((message: Message) => {
            return {role: message.role, content: message.content};
          })));
    } else {
      // Combine the messages
      generationMessages = generationMessages.concat(this.conversationPromt.concat(messagesNotInSummary));
    }

    // Generate a message using the OpenAI API
    const newMessage = this.apiService.chatComplete(generationMessages).then((response) => {
      console.log("Message generated!");
      console.log(response);

      // Create a new message object
      const message = {
        content: response.choices[0].message.content.replace(/\{\{user\}\}/g, 'Simon'),
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
      this.updateSummary().then(() => {
        this.dbService.updateConversation(this.conversation);
      });
    });
  }
}
