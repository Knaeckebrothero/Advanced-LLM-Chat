import { ConversationData, ConversationVariable } from '../data/interfaces/conversation';

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
  private updateSummary(summary: string, messagesPartOfSummery: number) {
    this.summary = summary;
    this.messagesPartOfSummery = messagesPartOfSummery;
  }
}
