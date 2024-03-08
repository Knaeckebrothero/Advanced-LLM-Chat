import { DBSchema } from 'idb';
import { Message } from './message-interface';

export interface ChatDB extends DBSchema {
    messages: {
      key: string;
      value: Message;
      indexes: { 'by-time': Date };
    };
    agents: {
      key: string
      value: { id: string; name: string; email?: string };
    };
  }
