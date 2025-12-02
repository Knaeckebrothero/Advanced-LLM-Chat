/**
 * Conversation Class Implementation
 *
 * This file implements the IConversation interface from models/.
 * Note: DB operations have been removed from this class.
 * Use the ConversationRepository for database operations.
 */

import { IConversation } from '../models';

/**
 * Conversation class that implements IConversation interface.
 * Pure data object - no database dependencies.
 */
export class Conversation implements IConversation {
  id: string;
  userId: number;
  name: string;
  participants: string[];
  hashsum?: number;
  createdAt: Date;
  updatedAt: Date;
  version: number;
  lastModified: number;

  constructor(
    id: string,
    userId: number,
    name: string,
    participants: string[],
  ) {
    this.id = id;
    this.userId = userId;
    this.name = name;
    this.participants = participants;
    this.createdAt = new Date();
    this.updatedAt = new Date();
    this.version = 1;
    this.lastModified = Math.floor(Date.now() / 1000);
  }

  // =========================================================================
  // Hash Computation
  // =========================================================================

  /**
   * Compute hash from a list of message content strings.
   * This method is now a pure function that doesn't require DB access.
   *
   * @param messageContents Array of message content strings
   * @returns Computed hash value
   */
  computeHashFromContents(messageContents: string[]): number {
    if (!messageContents.length) return 0;

    const allContent = messageContents
      .filter(content => content && content.length > 0)
      .join('|');

    if (!allContent) return 0;

    return this.computeNumericHash(allContent);
  }

  private computeNumericHash(data: string): number {
    let hash = 0;
    if (data.length === 0) return hash;

    for (let i = 0; i < data.length; i++) {
      const char = data.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }

    return Math.abs(hash);
  }

  // =========================================================================
  // Factory Methods
  // =========================================================================

  /**
   * Create Conversation from API response
   */
  static fromApiResponse(data: any): Conversation {
    const participants = typeof data.participants === 'string'
      ? JSON.parse(data.participants)
      : data.participants;

    const conv = new Conversation(
      data.id,
      data.userId,
      data.name,
      participants || [],
    );
    conv.createdAt = new Date(data.createdAt);
    conv.updatedAt = new Date(data.updatedAt);
    conv.version = data.version || 1;
    conv.lastModified = data.lastModified || Math.floor(Date.now() / 1000);
    if (data.hashsum !== undefined) {
      conv.hashsum = data.hashsum;
    }
    return conv;
  }

  /**
   * Create Conversation from IndexedDB plain object
   */
  static fromPlainObject(data: any): Conversation {
    const conv = new Conversation(
      data.id,
      data.userId,
      data.name,
      data.participants || []
    );
    conv.createdAt = new Date(data.createdAt);
    conv.updatedAt = new Date(data.updatedAt);
    if (data.hashsum !== undefined) {
      conv.hashsum = data.hashsum;
    }
    conv.version = data.version || 1;
    conv.lastModified = data.lastModified || Math.floor(Date.now() / 1000);
    return conv;
  }

  // =========================================================================
  // Serialization
  // =========================================================================

  /**
   * Serialize for IndexedDB storage
   */
  toJSON(): any {
    return {
      id: this.id,
      userId: this.userId,
      name: this.name,
      participants: this.participants,
      createdAt: this.createdAt.toISOString(),
      updatedAt: this.updatedAt.toISOString(),
      version: this.version,
      lastModified: this.lastModified,
      hashsum: this.hashsum
    };
  }
}
