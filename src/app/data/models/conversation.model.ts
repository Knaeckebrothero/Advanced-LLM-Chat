/**
 * Conversation Data Models
 */

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
}

// For sync checking
export interface IConversationState {
  id: string;
  hashsum: number;
}
