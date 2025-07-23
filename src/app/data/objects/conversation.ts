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

        let hashValue = 0;
        for (const message of messages) {
            const content = message.getDisplayContent();
            if (!content) {
                hashValue += 0;
                continue;
            }

            hashValue += content.charCodeAt(0);
            hashValue += content.charCodeAt(content.length - 1);
            hashValue *= content.length;

            // Use modulo to stay within safe integer range
            hashValue %= (2**32);
        }
        return hashValue;
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
