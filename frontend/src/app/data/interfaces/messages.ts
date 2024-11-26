// Frontend Message interface
export interface Message {
  id: number;  // ID of the message
  conversationId: number;  // ID of the conversation
  roleName: string;  // Name of the sender
  content: any;  // Content of the message
  time: Date;  // Timestamp of the message
}

// API Message interfaces
interface ApiMessageBase {
  //  id: number;  // ID of the message
  conversationId: number;  // ID of the conversation
  // roleName: string;  // Name of the sender
  content: string;  // Text content of the message
  time: number;   // ISO timestamp string from backend
}

// Interface for sending messages to API
export interface ApiMessageSend extends ApiMessageBase {
  roleName: string;
}

// Interface for sending messages to API
export interface ApiMessageGenerate {
  conversationId: number,
  roleName: string,
  lastTimestamp: number
}

// Interface for receiving messages from API
export interface ApiMessageReceive extends ApiMessageBase {
  id: number;
  roleName: string;
}

// Interface for patching a message via the API
export interface ApiMessagePatch extends ApiMessageBase {
  id: number;
}
  
// Class to convert between frontend and API message formats
export class MessageConverter {
  static toApiSend(message: Message): ApiMessageSend {
    return {
      conversationId: message.conversationId,
      roleName: message.roleName,
      content: message.content,
      time: Math.floor(message.time.getTime() / 1000)  // Convert Date to Unix timestamp
    };
  }

  static toApiMessageGenerate(message: Message, participant: string): ApiMessageGenerate {
    return {
      conversationId: message.conversationId,
      roleName: participant,
      lastTimestamp: Math.floor(message.time.getTime() / 1000)  // Convert Date to Unix timestamp
    };
  }
  
  static fromApiReceive(apiMessage: ApiMessageReceive): Message {
    return {
      id: apiMessage.id,
      conversationId: apiMessage.conversationId,
      roleName: apiMessage.roleName,
      content: apiMessage.content,
      time : new Date(apiMessage.time * 1000)  // Convert Unix timestamp to Date
    };
  }
  
  static toApiPatch(message: Message): ApiMessagePatch & {  id: number } {
    if (!message.id) {
      throw new Error('Cannot patch message without ID');
    }
    return {
      id: message.id,
      conversationId: message.conversationId,
      content: message.content,
      time: Math.floor(new Date().getTime() / 1000)  // Convert Date to Unix timestamp
    };
  }
}
