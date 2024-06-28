import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { Message } from '../data/interfaces/message';
import { DBService } from '../data/db.service';
import { OpenAIService } from '../api/api.service';
import { Conversation } from '../chat/conversation';
import { Agent } from '../data/interfaces/agent';


@Injectable({
  providedIn: 'root'
})
export class ChatService {
  // Variables
  private conversation: Conversation = new Conversation(1, 0, [], "", []);
  private summaryAgent: Agent = {id: 1, role: "Summary Assistant", prompt: "You are an assistant that specializes in summarizing conversations."};
  private mainAgent: Agent = {id: 2, role: "Assistant", prompt: "You are a helpful assistant."};

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
          this.mainAgent = agent;
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
        conversationID: this.conversation.id,
        content: response.choices[0].message.content,
        role: response.choices[0].message.role, // this.mainAgent.role
        time: new Date()
      };
      return message;
    });
    return newMessage;
  }

  // Function to adjust message time and id by 1
  private decrementMessage(message: Message): Message {
    if (message.time === undefined) {
      return message;
    } else {
      // Convert original time to Unix timestamp (milliseconds since epoch)
      let timestamp = message.time!.getTime();

      // Subtract 1 millisecond
      timestamp -= 1;

      // Convert back to JavaScript Date object
      message.time = new Date(timestamp);

      if (message.id === null) {
        return message;
      } else {
        message.id = message.id! - 1;
        return message;
      }
    }
  }

  // Generate a new message
  public generateMessage() {  
    // Generate a response for main agent
    this.generate(this.mainAgent.prompt).then((generatedMessage) => {
      // Add the message to the messages array and save it in the database
      this.addMessage(generatedMessage);
      
      this.dbService.addMessage(generatedMessage).then(() => {
        // Update the conversation 
        this.conversation.updateSummary(this.summaryAgent.prompt, this.apiService, this.messagesSubject.getValue()).then(() => {
          this.dbService.updateConversation(this.conversation.toConversationData());
        });
      });
    });
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


  }

  // Alter message
  public alterMessage(updatedMessage: Message) {
    console.log('Altering Message: ', updatedMessage.id);
    var logOutput = 'Message was not found in message array!'

    // Create new array with the altered message
    const updatedMessages = this.messagesSubject.getValue().map(message => {
      if (message.id === updatedMessage.id) {
        logOutput = 'Message altered!';

        // Update the message in the database
        this.dbService.updateMessage(updatedMessage);

        // Return updated message if the id matches
        return updatedMessage;
      } else {
        // Return the message as is if the id does not match
        return message;
      }
    });

    // Emit the updated messages array through the BehaviorSubject
    this.messagesSubject.next(updatedMessages);

    // Log the result
    console.log(logOutput);
  }

  // Add a new system message to the messages array
  public systemAddMessage(messageId: number) {
    console.log('Inserting Systemmessage above: ', messageId);
    var logOutput = 'Message was not found in message array!';

    // Create new array with the altered message
    const updatedMessages = this.messagesSubject.getValue().reduce<Message[]>((acc, message) => {
      // If the message ID matches, insert both the new and old message
      if (message.id === messageId) {
        logOutput = 'Message inserted!';

        // Create an empty system message object and decrement the message id and time by 1 to set it above the current message
        const newMessage = this.decrementMessage({
          id: message.id,
          conversationID: this.conversation.id,
          content: "",
          role: 'system',
          time: message.time
        });

        // Update the message in the database
        this.dbService.addMessage(newMessage);

        // Add both the new system message and the original message to the accumulator
        acc.push(newMessage, message);
      } else {
        // Add the current message to the accumulator
        acc.push(message);
      }
      return acc;
    }, []);

    // Emit the updated messages array through the BehaviorSubject
    this.messagesSubject.next(updatedMessages);

    // Log the result
    console.log(logOutput);
  }

  // Delete a message from the messages array
  public deleteMessage(messageId: number) {
    console.log('Deleting message: ', messageId);
    var logOutput = 'Message was not found in message array!';

    // Create new array without the deleted message
    const updatedMessages = this.messagesSubject.getValue().filter(message => {
      if (message.id === messageId) {
        logOutput = 'Message deleted!';

        // Delete the message from the database
        this.dbService.deleteMessage(messageId);

        // Return false if the id matches to remove the message
        return false;
      } else {
        // Return true if the id does not match to keep the message
        return true;
      }
    });

    // Emit the updated messages array through the BehaviorSubject
    this.messagesSubject.next(updatedMessages);

    // Log the result
    console.log(logOutput);
  }

  // Get conversation credentials
  public getConversationCredentials() {
    return {user: this.summaryAgent.role, ai: this.mainAgent.role};
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
