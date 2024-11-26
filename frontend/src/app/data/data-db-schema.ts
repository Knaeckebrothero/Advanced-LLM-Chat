import { DBSchema } from 'idb';
import { Message } from './interfaces/messages';
import { Conversation } from './interfaces/conversation';


export interface MainAppDB extends DBSchema {
  // Messages store
  chatMessages: {
    key: number;
    value: Message;
    indexes: {
      'by-time': 'time';
      'by-conversationID': 'conversationID';
      'by-conversationID-time': ['conversationID', 'time'];
    };
  };
  // Conversations store
  conversations: {
    key: number;
    value: Conversation;
  };
}
