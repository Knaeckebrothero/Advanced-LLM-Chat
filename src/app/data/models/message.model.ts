/**
 * Message Data Models
 *
 * These interfaces define the shape of message data throughout the application.
 * They serve as the single source of truth and mirror the backend Pydantic models.
 */

import { IFilePreview, IFileAttachment } from './file.model';

// ============================================================================
// Core Types
// ============================================================================

export type MessageType = 'text' | 'voice' | 'agent';
export type AgentStepType = 'thought' | 'tool_call' | 'tool_result' | 'observation';
export type AgentStatus = 'thinking' | 'responding' | 'complete' | 'error';
export type SyncStatus = 'pending' | 'synced' | 'error' | 'local-only';

/**
 * Display mode for agent steps UI
 * - unified: All steps in one collapsible dropdown (Gemini-style)
 * - grouped: Steps grouped by type in separate dropdowns (Claude-style)
 * - expanded: All steps visible, no dropdowns (debug view)
 */
export type AgentDisplayMode = 'unified' | 'grouped' | 'expanded';

// ============================================================================
// Message Metadata (shared by all message types)
// ============================================================================

export interface IMessageMetadata {
  id: number;
  conversationId: string;
  roleName: string;
  time: Date;
  version?: number;
  lastModified?: number;
  rating?: number | null;
  syncStatus?: SyncStatus;
}

// ============================================================================
// Content Types (discriminated union)
// ============================================================================

export interface ITextContent {
  type: 'text';
  content: string;
  attachments?: IFilePreview[];
}

export interface IVoiceContent {
  type: 'voice';
  audioData: string;
  duration: number;
  mimeType: string;
  transcript?: string;
  waveform?: number[];
}

export interface IAgentStep {
  id: string;
  type: AgentStepType;
  title: string;
  content: string;
  timestamp: number;
  duration?: number;
  callId?: string;
  metadata?: Record<string, unknown>;
}

export interface IAgentContent {
  type: 'agent';
  steps: IAgentStep[];
  finalResponse: string;
  status: AgentStatus;
  error?: string;
}

export type IMessageContent = ITextContent | IVoiceContent | IAgentContent;

// ============================================================================
// Complete Message Interface
// ============================================================================

export interface IMessage<T extends IMessageContent = IMessageContent> {
  metadata: IMessageMetadata;
  content: T;
}

// Convenience type aliases
export type ITextMessage = IMessage<ITextContent>;
export type IVoiceMessage = IMessage<IVoiceContent>;
export type IAgentMessage = IMessage<IAgentContent>;
