/**
 * API Request/Response Models
 * Mirrors backend Pydantic models for API communication
 */

import { IAgentStep, IAgentContent, IMessageContent } from './message.model';
import { IMessageUsage, PersonaValues } from './catalog.model';

// ============================================================================
// Message API Models
// ============================================================================

export interface IApiMessageSend {
  conversationId: string;
  roleName: string;
  type: 'text' | 'voice' | 'agent';
  content: string | IMessageContent;
  time: number;
  version?: number;
  lastModified?: number;
}

export interface IApiMessageGenerate {
  conversationId: string;
  roleName: string;
  time: number;
  temperature?: number;
  top_p?: number;
  systemPrompt?: string;
}

export interface IApiMessageResponse {
  id: number;
  conversationId: string;
  roleName: string;
  content: string | IAgentContent;
  time: number;
  type?: string;
  version?: number;
  lastModified?: number;
  rating?: number | null;
  // Agent-specific fields (flattened)
  steps?: IAgentStep[];
  finalResponse?: string;
  status?: string;
  error?: string;
  // Model and usage (agent messages)
  modelId?: number | null;
  modelName?: string | null;
  usage?: IMessageUsage | null;
}

// ============================================================================
// Streaming API Models
// ============================================================================

export interface IStreamGenerateRequest {
  conversationId: string;
  aiParticipant?: string;
  modelId?: number;  // Answer with this catalog model instead of the conversation's
}

export interface IMessageStartEvent {
  messageId: number;
  conversationId: string;
  roleName: string;
  time: number;
  type: 'agent';
  modelId?: number | null;  // null for the environment model
  modelName?: string | null;
}

export type StreamEventType = 'message_start' | 'step' | 'step_delta' | 'token' | 'done' | 'error';

// ============================================================================
// Conversation API Models
// ============================================================================

export interface IApiConversationCreate {
  name: string;
  participants: string[];
  modelId?: number | null;
  personaId?: number | null;
  personaValues?: PersonaValues | null;
}

/** PATCH /api/conversation/{id}. The name is always sent, for backends that still require it. */
export interface IApiConversationUpdate {
  name: string;
  modelId?: number | null;
  personaId?: number | null;
  personaValues?: PersonaValues | null;
}

export interface IApiConversationResponse {
  id: string;
  userId: number;
  name: string;
  participants: string[];
  createdAt: string;
  updatedAt: string;
  hashsum: number;
  version: number;
  lastModified?: number;
  modelId?: number | null;
  personaId?: number | null;
  personaValues?: PersonaValues | null;
}
