import { ConversationData, ConversationVariable } from '../data/interfaces/conversation';
import { Message } from '../data/interfaces/message';


export class Conversation implements ConversationData {
  id: string;
  messagesPartOfSummery: number;
  enviorementVariables: ConversationVariable[];
  summary: string;
  participants: string[];

  // Constructor
  constructor(
    id: string,
    messagesPartOfSummery: number, 
    enviorementVariables: ConversationVariable[], 
    summary: string,
    participants: string[]) {
    this.id = id;
    this.messagesPartOfSummery = messagesPartOfSummery;
    this.enviorementVariables = enviorementVariables;
    this.summary = summary;
    this.participants = participants;
  }

  // Get conversation promt
  private updateConversationPromt() {
    // Prepare the enviorement variables
    var envVarStr: string = '';
    for(let i = 0; i < this.enviorementVariables.length; i++) {
      envVarStr += `${this.enviorementVariables[i].name}: ${this.enviorementVariables[i].value}\n`;
    };
    
    // Assemble the conversation promt
    var promt: string = 
    `The following data is about the course of the conversation. To stay within the context window and provide some additional information to keep the conversation consistent, the conversation will be summarized and only the last few messages will be provided. Keep in mind that these may or may not be part of the following conversation summery or variables. If any of the values are empty they have not been set yet.\n\n
    A list of the characters participating in the conversation or scenario:
    ${this.participants}\n\n
    A list of environment variables up to this point:
    ${envVarStr}\n\n
    Summary of the conversation up to this point:
    ${this.summary}\n\n
    The last 10 messages exchanged by the participants:\n`;
    return promt;
  }

  // Update the summary and recent messages
  public updateSummary(summary: string, messagesPartOfSummery: number) {
    this.summary = summary;
    this.messagesPartOfSummery = messagesPartOfSummery;
  }

  // Update the conversation
  public updateConversation(
    summary: string, 
    messagesPartOfSummery: number, 
    enviorementVariables: ConversationVariable[], 
    participants: string[]) {
    // Update the summary and recent messages
    this.updateSummary(summary, messagesPartOfSummery);

    // Update the enviorement variables and participants
    this.enviorementVariables = enviorementVariables;
    this.participants = participants;
  }
  
  // Convert a conversation to an array of messages used by the openai API
  public getAsMessages(){
    // Prepare the messages array
    const messages: Message[] = [];

    // Add the enviorement variables to the messages
    if (this.enviorementVariables.length > 0) {
      // Prepare the enviorement variables
      var envVarStr: string = 'A list of environment variables up to this point:\n';
      for(let i = 0; i < this.enviorementVariables.length; i++) {
        envVarStr += `${this.enviorementVariables[i].name}: ${this.enviorementVariables[i].value}\n`;
      };
      
      // Add the concatinated enviorement variables to the messages
      messages.push({role: "system", content: envVarStr});
    }

    // Add the summary to the messages
    if (this.summary !== '') {
      messages.push({role: "system", content: `Summary of the conversation up to this point: ${this.summary}`});
    }

    // Add the participants to the messages
    if (this.participants.length > 0) {
      messages.push({role: "system", content: `A list of the characters participating in the conversation or scenario: ${this.participants}`});
    }

    return messages;
  }
}
