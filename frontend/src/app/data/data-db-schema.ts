import { DBSchema } from 'idb';
import { Message } from './interfaces/message';
import { Conversation } from './interfaces/conversation';


export interface MainAppDB extends DBSchema {
  // Messages store
  chatMessages: {
    key: number;
    value: Message;
    indexes: {
      'by-time': 'time';
      'by-conversationId': 'conversationId';
      'by-conversationId-time': ['conversationId', 'time'];
    };
  };
  // Conversations store
  conversations: {
    key: number;
    value: Conversation;
  };
}
