import { DBSchema } from 'idb';
import { Message } from './interfaces/chat-message';
import { OpenAi } from './interfaces/api-config';

export interface MainAppDB extends DBSchema {
  // Messages store
  messages: {
    key: string;
    value: Message;
    indexes: { 'by-time': Date };
  };
  // LLM Agents store
  agents: {
    key: string;
    value: any;
  };
  // API settings store
  settings: {
    key: string;
    value: OpenAi | {};
  };
}
