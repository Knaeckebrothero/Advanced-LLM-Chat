/**
 * API Request/Response Models
 * Mirrors backend Pydantic models for API communication
 */

import { IAgentStep, IAgentContent, IMessageContent } from './message.model';

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
}

// ============================================================================
// Streaming API Models
// ============================================================================

export interface IStreamGenerateRequest {
  conversationId: string;
  aiParticipant?: string;
}

export interface IMessageStartEvent {
  messageId: number;
  conversationId: string;
  roleName: string;
  time: number;
  type: 'agent';
}

export type StreamEventType = 'message_start' | 'step' | 'token' | 'done' | 'error';

// ============================================================================
// Conversation API Models
// ============================================================================

export interface IApiConversationCreate {
  name: string;
  participants: string[];
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
}
