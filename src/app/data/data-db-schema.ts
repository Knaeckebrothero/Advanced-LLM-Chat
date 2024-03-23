import { DBSchema } from 'idb';
import { Message } from './interfaces/message';
import { OpenAIChatCompleteRequest } from './interfaces/api-openai-request';
import { ConversationData } from './interfaces/conversation';
import { Agent } from './interfaces/agent';


export interface MainAppDB extends DBSchema {
  // Messages store
  chatMessages: {
    key: number;
    value: Message;
    indexes: { 'by-time': 'time', 'by-conversationID': 'conversationID' };
  };
  // LLM Agents store
  llmAgents: {
    key: number;
    value: Agent;
  };
  // OpenAI settings store
  llmConfigs: {
    key: number;
    value: OpenAIChatCompleteRequest;
  };
  // Conversations store
  conversations: {
    key: number;
    value: ConversationData;
  };
}
