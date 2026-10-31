/**
 * Conversation Data Models
 */

import { PersonaValues } from './catalog.model';

export interface IConversation {
  id: string;
  userId: number;
  name: string;
  participants: string[];
  createdAt: Date;
  updatedAt: Date;
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

// For sync checking
export interface IConversationState {
  id: string;
  hashsum: number;
}
