import { Message } from '../data/interfaces/chat-message';

// Interface for enviorement variables
interface Variable {
  name: string,
  value: string
}

// Interface for conversation data
export interface ConversationData {
  // List holding the last few messages
  recentMessages: Message[];
  // List holding enviorement variables
  enviorementVariables: Variable[];
}

export class Conversation implements ConversationData {
  // Variables
  recentMessages: Message[];
  enviorementVariables: Variable[];

  // Constructor
  constructor() {
    this.recentMessages = [];
    this.enviorementVariables = [];
  }

  // Update recent messages
  private updateRecentMessages() {
  }

  // Update enviorement variables
  private updateEnviorementVariables() {
    this.enviorementVariables = enviorementVariables;
  }
}