import { DBSchema } from 'idb';
import { Message } from './interfaces/message';
import { Conversation } from './interfaces/conversation';
import { User } from './interfaces/user';


export interface MainAppDB extends DBSchema {
  // Messages store
  chatMessages: {
    key: number;
    value: Message;
    indexes: {
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
    value: User;
  };
}
