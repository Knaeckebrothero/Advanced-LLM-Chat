import { inject } from '@angular/core';
import { DBService } from '../db.service';
import { Message } from './message';


export class Conversation {
    id: string;  // Id of the conversation (UUID string)
    userId: number;  // Id of the user the conversation belongs to
    name: string;  // Name or title of the conversation
    participants: string[];  // Characters or Agents participating in the conversation
    hashsum?: number;  // Hashsum of the conversation
    createdAt: Date = new Date(); // Creation date of the conversation
    updatedAt: Date = new Date(); // Last update date of the conversation

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
    }

    // Get latest messages
    async getLatestMessages(db: DBService, count: number = 20): Promise<Message[]> {
        try {
            const messages = await db.getMessagesByConversationId(this.id);

            // Check if the db returned any messages
            if (messages !== undefined) {
                // Sort the messages by time
                messages.sort((a, b) => a.time!.getTime()! - b.time!.getTime());
                return [...messages.slice(-count)];
            }

            return [];
        } catch (error) {
            console.error('Error getting messages:', error);
            return [];
        }
    }

    // Compute conversation hash
    async computeHash(db: DBService): Promise<number> {
        const messages = await this.getLatestMessages(db);

        if (!messages.length) return 0;

        // Concatenate all message contents for hashing
        const allContent = messages
            .map(m => m.getDisplayContent() || '')
            .filter(content => content.length > 0)
            .join('|'); // Use separator to ensure different message combinations produce different hashes

        if (!allContent) return 0;

        return this.computeNumericHash(allContent);
    }

    private computeNumericHash(data: string): number {
        let hash = 0;
        if (data.length === 0) return hash;
        
        for (let i = 0; i < data.length; i++) {
            const char = data.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash; // Convert to 32-bit integer
        }
        
        return Math.abs(hash);
    }

  // Convert to API check format
  //toApiCheck() {
  //    return {
  //        id: this.id,
  //        hashsum: this.computeHash()
  //    };
  //}

  static fromApiResponse(data: any): Conversation {
    const participants = typeof data.participants === 'string' ? JSON.parse(data.participants) : data.participants;
    const conv = new Conversation(
      data.id,
      data.userId,
      data.name,
      participants || [],
    );
    conv.createdAt = new Date(data.createdAt);
    conv.updatedAt = new Date(data.updatedAt);
    return conv;
  }

  // Create Conversation instance from plain object (IndexedDB)
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
    return conv;
  }
}
