import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { Message } from '../data/interfaces/message';
import { DBService } from '../data/db.service';
import { OpenAIService } from '../api/api-openai.service';
import { Conversation } from '../chat/conversation';
import { Agent } from '../data/interfaces/agent';


@Injectable({
  providedIn: 'root'
})
export class ChatService {
  // Variables
  private conversation: Conversation;
  private agent!: Agent;
  conversationPromt: Message[] = []; // Old way of converting messages, should be removed later on!

  // The ChatService is responsible for exposing the messages as an observable.
  public messages: Observable<Message[]> = this.conversation.messagesObservable;

  // Constructor
  constructor(private dbService: DBService, private apiService: OpenAIService) {
    // Wait for the database to be ready
    this.dbService.getDatabaseReadyPromise().then(() => {
      // Load the default conversation from the database
      this.dbService.getConversation("default-conv-01").then((conversation: any) => {
        // Check if the conversation exists
        if (conversation != undefined) {
          // Load the conversation messages from the database
          this.dbService.getAllMessages(conversation.id).then((messages: Message[]) => {
            // Check if the conversation has any messages
            if(messages == undefined) {
              messages = []
            }

            // Initialize the conversation
            this.conversation = new Conversation(
              conversation.id,
              messages,
              conversation.messagesPartOfSummary,
              conversation.enviorementVariables,
              conversation.summary,
              conversation.participants
            );
            console.log("Conversation loaded!");
          });
        } else {
          // Create a new conversation
          this.conversation = new Conversation("default-conv-01", [], 0, [], "", []);
          
          // Add the new conversation to the database
          this.dbService.addConversation(this.conversation).then(() => {
            console.log("New conversation created!");
          });
        }
      });

      // Load the agent from the database
      this.dbService.getAgent("default-agent-01").then((agent: any) => {
        // Check if the agent exists
        if (agent !== undefined) {
          // Initialize the agent
          this.agent = agent;
          console.log("Agent loaded!");
        } else {
          // Create a new agent
          this.agent = {
            id: "default-agent-01",
            role: "Assistant",
            prompt: "You are a helpfull assistant."
          };
          console.error("Agent not found!");
        }
      });

      // Initialize the messages observable once everything is setup.
      this.messages = this.conversation.messagesObservable;
    });
  }

  // Generate a new message
  private generate() {
    const messagePrompt = this.conversation.getMessagePrompt(this.agent.prompt)

    // Generate a message using the OpenAI API
    const newMessage = this.apiService.chatComplete(messagePrompt).then((response) => {
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
    this.conversation.addMessage(newMessage);
    console.log("Usermessage added!");

    // Generate a response
    this.generate().then((generatedMessage) => {
      // Add the message to the messages array
      this.conversation.addMessage(generatedMessage);

      // Save the message in the database
      this.dbService.addMessage(generatedMessage);

      // Update the conversation
      this.conversation.updateSummary(this.agent.prompt, this.apiService).then(() => {
        this.dbService.updateConversation(this.conversation);
      });
    });
  }
}
