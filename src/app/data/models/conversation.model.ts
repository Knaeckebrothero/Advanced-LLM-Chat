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

// For sync checking
export interface IConversationState {
  id: string;
  hashsum: number;
}
