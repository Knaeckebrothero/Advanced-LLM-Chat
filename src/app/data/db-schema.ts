import { DBSchema } from 'idb';
import { Message } from './objects/message';
import { Conversation } from './objects/conversation';
import { User } from './objects/user';
import { SettingsWithMetadata } from '../repositories/settings.repository';


export interface MainAppDB extends DBSchema {
  // Messages store
  chatMessages: {
    key: number;
    value: Message;
    indexes: {
      'by-conversationId': string;
      'by-conversationId-time': [string, Date];
    };
  };
  // Conversations store
  conversations: {
    key: string;
    value: Conversation;
    indexes: {
      'by-userId': number;
    };
  };
  // User store
  user: {
    key: number;
    value: User;
  };
  // Settings store
  settings: {
    key: string;
    value: SettingsWithMetadata;
  };
}
