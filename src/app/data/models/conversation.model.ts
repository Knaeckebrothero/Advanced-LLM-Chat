/**
 * Conversation Data Models
 */

import { PersonaValues } from './catalog.model';

/** Who set a hidden mark: the user's decision, which agents leave alone, or an agent's. */
export type HiddenBy = 'user' | 'agent';

export interface IConversation {
  id: string;
  userId: number;
  name: string;
  participants: string[];
  createdAt: Date;
  updatedAt: Date;
  // When the newest message was stored (the server's clock), the sidebar's order; undefined = none yet
  lastMessageAt?: Date;
  version: number;
  lastModified: number;
  hashsum?: number;
  // Model catalog selection (null = the user's default model / no persona,
  // undefined = not known yet, e.g. from a backend without the catalog)
  modelId?: number | null;
  personaId?: number | null;
  personaValues?: PersonaValues | null;
  // Local only: the selection changed offline and still has to be sent to the backend
  selectionPending?: boolean;
  // Hidden; a chat of a hidden agent is hidden too (isConversationHidden())
  hidden?: boolean;
  // Who set hidden: the user (agents leave it alone) or an agent; null/undefined = nobody
  hiddenBy?: HiddenBy | null;
  // Local only: the mark changed offline and still has to be sent to the backend
  hiddenPending?: boolean;
}

/**
 * The summary the model gets instead of a conversation's oldest messages, once they no
 * longer fit its context window. Only on the server: loaded with the conversation and
 * sent in the stream when a new one is written.
 */
export interface IConversationSummary {
  conversationId: string;
  coversUntil: number;   // id of the newest message it covers; it covers every message up to it
  messageCount: number;
  content: string;       // Markdown
  modelName?: string | null;
  createdAt: number;     // unix seconds
}

/**
 * About how many input tokens the next answer sends (POST /api/message/context-size): estimates
 * of about 3 characters per token, without the tools of MCP servers.
 */
export interface IContextSize {
  modelId?: number | null;
  contextWindow: number;
  inputTokens: number;     // systemTokens + toolTokens + historyTokens
  systemTokens: number;
  toolTokens: number;
  historyTokens: number;   // the summary, then the newest messages that fit
  historyBudget: number;
  messageCount: number;    // messages in the history, without the summary
  leftOutCount: number;    // messages that don't fit and are left out
  summarizes: boolean;     // the next answer first folds the oldest messages into the summary
}

/** The token estimate of the backend (backend/services/conversation_history.py CHARS_PER_TOKEN). */
export const CHARS_PER_TOKEN = 3;

// For sync checking
export interface IConversationState {
  id: string;
  hashsum: number;
}
