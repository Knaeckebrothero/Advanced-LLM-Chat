// Interface for enviorement variables
interface EnviorementVariable {
  name: string
  value: string
  optional: boolean
}

// Interface for conversation data
export interface ConversationData {
  // The number of messages part of the conversation summery
  messagesPartOfSummery: number;
  // Summary of the conversation
  summary: string;
  // List holding enviorement variables
  enviorementVariables: EnviorementVariable[];
  // Characters participating in the conversation
  participants: string[];
}

export class Conversation implements ConversationData {
  messagesPartOfSummery: number;
  enviorementVariables: EnviorementVariable[];
  summary: string;
  participants: string[];
  conversationPromt: string;

  // Constructor
  constructor(messagesPartOfSummery: number, 
    enviorementVariables: EnviorementVariable[], 
    summary: string,
    participants: string[]) {
    this.messagesPartOfSummery = messagesPartOfSummery;
    this.enviorementVariables = enviorementVariables;
    this.summary = summary;
    this.participants = participants;
    this.conversationPromt = this.updateConversationPromt();
  }

  // Update the conversation
  public updateConversation(
    summary: string, 
    messagesPartOfSummery: number, 
    enviorementVariables: EnviorementVariable[], 
    participants: string[]) {
    // Update the summary and recent messages
    this.updateSummary(summary, messagesPartOfSummery);

    // Update the enviorement variables and participants
    this.enviorementVariables = enviorementVariables;
    this.participants = participants;
    
    // Update and return the conversation promt
    this.conversationPromt = this.updateConversationPromt();
    return this.conversationPromt;
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
    `The following data is about the course of the conversation. To stay within the context window and provide some additional information to keep the conversation consistent, the conversation will be summarized and only the last few messages will be provided. Keep in mind that these may or may not be part of the following conversation summery or variables.\n\n
    A list of the characters participating in the conversation or scenario:\n
    ${this.participants}\n\n
    A list of environment variables up to this point:\n
    ${envVarStr}\n\n
    Summary of the conversation up to this point:\n
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
