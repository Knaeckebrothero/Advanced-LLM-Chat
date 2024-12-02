import { DBSchema } from 'idb';
import { Message } from './interfaces/message';
import { Conversation } from './interfaces/conversation';


export interface MainAppDB extends DBSchema {
  // Messages store
  chatMessages: {
    key: [number, number];  // Composite key [conversationId, messageId]
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
    indexes: {
      'by-userId': 'userId';
    };
  };
  // User store
  user: {
    key: number;
    value: any;
  };
}
