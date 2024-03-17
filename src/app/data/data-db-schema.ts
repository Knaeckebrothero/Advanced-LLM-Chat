import { DBSchema } from 'idb';
import { Message } from './interfaces/message';
import { OpenAIChatCompleteRequest } from './interfaces/api-openai-request';
import { ConversationData } from './interfaces/conversation';
import { Agent } from './interfaces/agent';


export interface MainAppDB extends DBSchema {
  // Messages store
  chatMessages: {
    key: string;
    value: Message;
    indexes: { 'by-time': Date };
  };
  // LLM Agents store
  llmAgents: {
    key: string;
    value: Agent;
  };
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
