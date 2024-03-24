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
  // Variables
  private conversation: Conversation = new Conversation(1, 0, [], "", []);
  private summaryAgent: Agent = {id: 1, role: "Assistant", prompt: "You are an assistant that specializes in summarizing conversations."};
  private agentA: Agent = {id: 2, role: "GoodAssistant", prompt: "You are a good assistant, like an angel on the users left shoulder."};
  private agentB: Agent = {id: 3, role: "BadAssistant", prompt: "You are an evil assistant, like the devil on the users right shoulder."};
  conversationPromt: Message[] = []; // Old way of converting messages, should be removed later on!

  // The ChatService is responsible for managing and exposing the messages.
  private messagesSubject: BehaviorSubject<Message[]> = new BehaviorSubject<Message[]>([]);
  public messages: Observable<Message[]> = this.messagesSubject.asObservable();

  // Constructor
  constructor(private dbService: DBService, private apiService: OpenAIService) {
    // Wait for the database to be ready
    this.dbService.getDatabaseReadyPromise().then(() => {
      // Load the default conversation from the database
      this.dbService.getConversation(1).then((conversation: any) => {
        // Check if the conversation exists
        if (conversation != undefined) {
          // Load the conversation messages from the database
          this.dbService.getAllMessages(conversation.id).then((messages: Message[]) => {
            // Check if the conversation has any messages
            if(messages !== undefined) {
              this.addMessage(messages);
            }

            // Initialize the conversation
            this.conversation = new Conversation(
              conversation.id,
              conversation.messagesPartOfSummary,
              conversation.enviorementVariables,
              conversation.summary,
              conversation.participants
            );
            console.log("Conversation loaded!");
          });
        } else {          
          // Add the default conversation to the database
          this.dbService.addConversation(this.conversation.toConversationData()).then(() => {
            console.log("New conversation created!");
          });
        }
      });

      // Load the agent from the database
      this.dbService.getAgent(1).then((agent: any) => {
        // Check if the agent exists
        if (agent !== undefined) {
          // Initialize the agent
          this.summaryAgent = agent;
          console.log("Agent loaded!");
        } else {
          console.error("Agent not found!");
        }
      });

      // Load the agent from the database
      this.dbService.getAgent(2).then((agent: any) => {
        // Check if the agent exists
        if (agent !== undefined) {
          // Initialize the agent
          this.agentA = agent;
          console.log("Agent loaded!");
        } else {
          console.error("Agent not found!");
        }
      });

      // Load the second agent from the database
      this.dbService.getAgent(3).then((agent: any) => {
        // Check if the agent exists
        if (agent !== undefined) {
          // Initialize the agent
          this.agentB = agent;
          console.log("Agent loaded!");
        } else {
          console.error("Agent not found!");
        }
      });
    });
  }

  // Add one or more messages to the conversation
  private addMessage(message: Message | Message[]) {
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

  // Generate a new message
  private generate(agentPrompt: string) {
    const messagePrompt = this.conversation.getMessagePrompt(agentPrompt, this.messagesSubject.getValue());
    console.log(this.messages)

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
      conversationID: this.conversation.id,
      content: content,
      role: 'user',
      time: new Date()
    };
  
    // Add the message to the database and messages array
    this.dbService.addMessage(newMessage);
    this.addMessage(newMessage);
    console.log("Usermessage added!");
  
    // Generate a response for agent a
    const responseA = this.generate(this.agentA.prompt).then((generatedMessage) => {
      // Check if the agent has decided to say something
      if (generatedMessage.content !== 'NO_MESSAGE') {
        // Add the message to the messages array and save it in the database
        this.addMessage(generatedMessage);
        this.dbService.addMessage(generatedMessage);
      }
    });
  
    // Generate a response for agent b
    const responseB = this.generate(this.agentB.prompt).then((generatedMessage) => {
      // Check if the agent has decided to say something
      if (generatedMessage.content !== 'NO_MESSAGE') {
        // Add the message to the messages array and save it in the database
        this.addMessage(generatedMessage);
        this.dbService.addMessage(generatedMessage);
      }
    });
  
    // Trigger conversation update once both agents have responded
    Promise.all([responseA, responseB]).then(() => {
      // This code is executed once both agents have responded
      console.log("Both agents have responded. Updating conversation...");
  
      // Update the conversation
      this.conversation.updateSummary(this.summaryAgent.prompt, this.apiService, this.messagesSubject.getValue()).then(() => {
        this.dbService.updateConversation(this.conversation.toConversationData());
      });
    });
  }

  // Get summary
  public getSummary(): string{
    return this.conversation.summary;
  }

  // Set summary
  public setSummary(summary: string) {
    this.conversation.summary = summary;
  }
}
