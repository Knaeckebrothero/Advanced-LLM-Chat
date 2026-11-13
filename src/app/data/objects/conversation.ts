/**
 * Conversation Class Implementation
 *
 * This file implements the IConversation interface from models/.
 * Note: DB operations have been removed from this class.
 * Use the ConversationRepository for database operations.
 */

import { IConversation, IConversationSelection, PersonaValues } from '../models';
import { HiddenBy } from '../models/conversation.model';

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
  // When the newest message was stored (the server's clock); undefined = none yet
  lastMessageAt?: Date;
  version: number;
  lastModified: number;
  // Model catalog selection: null = the user's default model / no persona,
  // undefined = unknown (not sent by the backend)
  modelId?: number | null;
  personaId?: number | null;
  personaValues?: PersonaValues | null;
  selectionPending?: boolean;
  // Hidden; undefined = not sent by the backend. hiddenPending: not sent yet
  hidden?: boolean;
  hiddenBy?: HiddenBy | null;  // Who set it: the user (agents leave it alone) or an agent
  hiddenPending?: boolean;

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
  // Order in the sidebar
  // =========================================================================

  /** What the sidebar sorts by: the newest message, or the creation of a conversation without one. */
  get lastActivity(): Date {
    return this.lastMessageAt ?? this.createdAt;
  }

  /** Newest activity first. */
  static compareByActivity(a: Conversation, b: Conversation): number {
    return b.lastActivity.getTime() - a.lastActivity.getTime();
  }

  /**
   * A message the server stored: its id is the server's clock in milliseconds. Messages only
   * in the browser (negative ids) don't count. Returns whether the conversation moved up.
   */
  recordMessage(messageId: number): boolean {
    return messageId > 0 && this.mergeLastMessageAt(new Date(messageId));
  }

  /** Takes a later time of the newest message (e.g. from the server); returns whether it changed. */
  mergeLastMessageAt(time: Date | undefined): boolean {
    if (!time || isNaN(time.getTime())) return false;
    if (this.lastMessageAt && this.lastMessageAt.getTime() >= time.getTime()) return false;
    this.lastMessageAt = time;
    return true;
  }

  // =========================================================================
  // Model Catalog Selection
  // =========================================================================

  /** The current selection, with unknown values read as "default model, no persona". */
  get selection(): IConversationSelection {
    return {
      modelId: this.modelId ?? null,
      personaId: this.personaId ?? null,
      personaValues: this.personaValues ?? null
    };
  }

  private static readSelection(conv: Conversation, data: any): void {
    if (typeof data.hidden === 'boolean') conv.hidden = data.hidden;
    if (data.hiddenBy !== undefined) conv.hiddenBy = data.hiddenBy;
    if (data.modelId !== undefined) conv.modelId = data.modelId;
    if (data.personaId !== undefined) conv.personaId = data.personaId;
    if (data.personaValues !== undefined) {
      conv.personaValues = typeof data.personaValues === 'string'
        ? JSON.parse(data.personaValues)
        : data.personaValues;
    }
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
    conv.mergeLastMessageAt(data.lastMessageAt ? new Date(data.lastMessageAt) : undefined);
    conv.version = data.version || 1;
    conv.lastModified = data.lastModified || Math.floor(Date.now() / 1000);
    if (data.hashsum !== undefined) {
      conv.hashsum = data.hashsum;
    }
    Conversation.readSelection(conv, data);
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
    conv.mergeLastMessageAt(data.lastMessageAt ? new Date(data.lastMessageAt) : undefined);
    if (data.hashsum !== undefined) {
      conv.hashsum = data.hashsum;
    }
    conv.version = data.version || 1;
    conv.lastModified = data.lastModified || Math.floor(Date.now() / 1000);
    Conversation.readSelection(conv, data);
    if (data.selectionPending) {
      conv.selectionPending = true;
    }
    if (data.hiddenPending) {
      conv.hiddenPending = true;
    }
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
      lastMessageAt: this.lastMessageAt?.toISOString(),
      version: this.version,
      lastModified: this.lastModified,
      hashsum: this.hashsum,
      modelId: this.modelId,
      personaId: this.personaId,
      personaValues: this.personaValues,
      selectionPending: this.selectionPending,
      hidden: this.hidden,
      hiddenBy: this.hiddenBy,
      hiddenPending: this.hiddenPending
    };
  }
}
