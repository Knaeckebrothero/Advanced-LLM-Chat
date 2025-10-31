import { DBSchema } from 'idb';
import { Message } from './objects/message';
import { Conversation } from './objects/conversation';
import { User } from './objects/user';
import { AppSettings } from '../models/settings.model';

export interface ConversationSyncMetadata {
  id: string;
  lastSynced: Date;
  messageCount: number;
  hash: number;
  lastMessageTimestamp?: Date;
  lastSyncedMessageId?: number;
  lastSyncedTimestamp?: number;
  expiresAt?: Date;
  lastMessageSent?: Date;
}

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
    value: AppSettings;
  };
  // Sync metadata store
  syncMetadata: {
    key: string; // conversation ID
    value: ConversationSyncMetadata;
  };
}
