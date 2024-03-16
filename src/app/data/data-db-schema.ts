import { DBSchema } from 'idb';
import { Message } from './interfaces/message';
import { OpenAIChatCompleteRequest } from './interfaces/api-openai-request';
import { ConversationData } from '../chat/conversation';

export interface MainAppDB extends DBSchema {
  // Messages store
  chatMessages: {
    key: string;
    value: Message;
    indexes: { 'by-time': Date };
  };
  /*
  // LLM Agents store
  chatAgents: {
    key: string;
    value: any;
  };
  */
  // OpenAI settings store
  llmConfigs: {
    key: string;
    value: OpenAIChatCompleteRequest;
  };
  // Conversations store
  conversations: {
    key: string;
    value: ConversationData;
  };
}
