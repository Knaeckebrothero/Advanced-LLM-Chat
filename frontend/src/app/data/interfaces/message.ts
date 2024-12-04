// Frontend Message interface
export interface Message {
  id?: number;  // ID of the message
  conversationId: number;  // ID of the conversation
  roleName: string;  // Name of the sender
  content: any;  // Content of the message
  time: Date;  // Timestamp of the message
}

// API Message interfaces
interface ApiMessageBase {
  // id: number;  // ID of the message
  conversationId: number;  // ID of the conversation
  // roleName: string;  // Name of the sender
  // content: string;  // Text content of the message
  // time: number;   // ISO timestamp string from backend
}

// Interface for sending messages to API
export interface ApiMessageSend extends ApiMessageBase {
  roleName: string;
  content: string;
  time: number;
}

// Interface for sending messages to API
export interface ApiMessageGenerate extends ApiMessageBase {
  roleName: string;
  time: number;
}

// Interface for receiving messages from API
export interface ApiMessageGenerateResponse extends ApiMessageBase {
  id: number;
  roleName: string;
  content: string;
  time: number;
}

// Interface for patching a message via the API
export interface ApiMessagePatch extends ApiMessageBase {
  id: number;
  content: string;
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
      time: Math.floor(message.time.getTime() / 1000)  // Convert Date to Unix timestamp
    };
  }
  
  static fromApiMessageGenerateResponse(apiMessage: ApiMessageGenerateResponse): Message {
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
    };
  }
}
