// Frontend Message interface
export interface Message {
  // The unique identifier, used as the key in the database
  id: number;
  // Surrogate Key referencing a conversation
  conversationId: number;
  // Whether the message was sent by the user (important for styling and alignment)
  roleName: string;
  // The message contents (text, image, etc.)
  content: any;
  // Timestamp of the message (used for sorting and display)
  time: Date;
}

// API Message interfaces
export interface ApiMessageBase {
  // The identifier of the conversation this message belongs to
  conversationId: number;
  // The content of the message
  content: string;
}
  
// Interface for sending messages to API
export interface ApiMessageRequest extends ApiMessageBase {
  // The timestamp of the message
  time: string;
}
  
// Interface for receiving messages from API
export interface ApiMessageResponse extends ApiMessageBase {
  // The unique identifier of the message
  messageId: number;
  // The role of the message sender
  roleName: string;
  // The timestamp of the message
  time: string;
}


  
// Message conversion utilities
export class MessageConverter {
  // Convert frontend Message to API request format
  static toApiRequest(message: Message, conversationId: number): ApiMessageRequest {
    return {
      conversationId: conversationId,
      roleName: message.roleName,
      content: message.content
    };
  }
  
  // Convert API response to frontend Message format
  static fromApiResponse(apiMessage: ApiMessageResponse): Message {
    return {
      id: apiMessage.messageId,
      conversationId: apiMessage.conversationId,
      roleName: apiMessage.roleName,
      content: apiMessage.content,
      time: new Date(apiMessage.time)
    };
  }
  
  // Convert frontend Message to API patch request format
  static toApiPatchRequest(message: Message, conversationId: number): ApiMessageRequest & { messageId: number } {
    if (!message.id) {
      throw new Error('Cannot patch message without ID');
    }
    return {
      messageId: message.id,
      conversationId: conversationId,
      roleName: message.roleName,
      content: message.content
    };
  }
}
