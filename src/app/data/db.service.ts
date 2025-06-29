import { Injectable } from '@angular/core';
import { openDB, IDBPDatabase } from 'idb';
import { Message } from './objects/message';
import { MainAppDB } from './db-schema';
import { Conversation } from './objects/conversation';
import { User } from './objects/user';
import { FilePreview } from './objects/file-preview';


@Injectable({
  providedIn: 'root'
})
export class DBService {

  // The database instance
  private db!: IDBPDatabase<MainAppDB>;
  private status: Promise<void>;

  constructor() {
    this.status = this.initDB().then(() => this.initializeDefaultState());;
  }

  // Initialize the database
  async initDB() {
    console.log("Starting database...");

    // Open the database
    this.db = await openDB<MainAppDB>('main', 1, {
      upgrade(db) {
        // Create a store for the user
        db.createObjectStore('user', { keyPath: 'id' });

        // Create a store for conversations with 'id' as the key path and an index
        const conversationStore = db.createObjectStore('conversations', { keyPath: 'id' });
        conversationStore.createIndex('by-userId', 'userId');

        // Create a store for messages with indexes and conversationId + id as a composite key
        const messageStore = db.createObjectStore('chatMessages', { keyPath: 'id' });
        messageStore.createIndex('by-conversationId', 'conversationId');
        messageStore.createIndex('by-conversationId-time', ['conversationId', 'time']);
      }
    });
    console.log("Database started!");
  }

  private async initializeDefaultState() {
    console.log("Checking db state...");

    // Check if user exists
    const user = await this.getAllUsers();
    if (!user) {
      console.log("Creating default user...");
      const defaultUser = {
        id: 0,
        accessToken: "defaultUser",
        email: "defaultUser",
        name: "defaultUser"
      };
      await this.addUser(defaultUser);
    }
  }

  // Get a promise that resolves when the database is ready
  public getDatabaseReadyPromise() {
    console.log("Waiting for database to be ready...");
    return this.status
  }

  // Method to add an entry to the collection
  private async addEntry(collectionName: any, newEntry: any) {
    if (!newEntry.id && newEntry.id !== null) {
      let entryNotAdded = true;
      let retries = 0;
      newEntry.id = Math.floor(new Date().getTime() / 1000);

      do {
        try {
          await this.db.add(collectionName, newEntry);
          console.log("Entry added to: " + collectionName + " id: " + newEntry.id);
          entryNotAdded = false;
        } catch (error) {
          newEntry.id += 1;
          retries += 1;
        }
      } while (entryNotAdded && retries < 10);

      if (entryNotAdded) {
        throw new Error('Failed to add entry after multiple attempts.');
      }
    } else {
      await this.db.add(collectionName, newEntry);
      console.log("Entry added to: " + collectionName + " id: " + newEntry.id);
    }
  }

  /*
  CRUD operations for messages
  */

  async addMessage(message: Message) {
    return await this.db.add('chatMessages', message);
  }

  async getMessage(id: number) {
    return await this.db.get('chatMessages', id);
  }

  async updateMessage(message: Message) {
    return await this.db.put('chatMessages', message);
  }

  async deleteMessage(id: number) {
    return await this.db.delete('chatMessages', id);
  }

  async deleteAllMessages() {
    return await this.db.clear('chatMessages');
  }

  async deleteMessagesByConversationId(conversationId: number) {
    const messages = await this.getMessagesByConversationId(conversationId);
    messages.forEach(async (message: any) => {
      await this.deleteMessage(message.id);
    });
  }

  async getMessagesByConversationId(conversationId: any = null) {
    if(conversationId) {
      return this.db.getAllFromIndex('chatMessages', 'by-conversationId', conversationId);
    } else {
      return await this.db.getAll('chatMessages');
    }
  }

  /*
  CRUD operations for conversations
  */

  async addConversation(conversation: Conversation) {
    return await this.db.add('conversations', conversation);
  }

  async getConversation(id: number) {
    return await this.db.get('conversations', id);
  }

  // Retrieves all conversations from the local IndexedDB, sorted by most recently updated first.
  public async getAllConversations(): Promise<Conversation[]> {
    const db = this.db;
    await this.status;
    const conversations = await this.db.getAll('conversations');

    // Sort by updatedAt descending (newest first)
    conversations.sort((a, b) => {
      const dateA = new Date(a.updatedAt).getTime();
      const dateB = new Date(b.updatedAt).getTime();
      return dateB - dateA;
    });

    return conversations;
  }


  async updateConversation(conversation: Conversation) {
    return await this.db.put('conversations', conversation);
  }

  async deleteConversation(id: number) {
    return await this.db.delete('conversations', id);
  }

  async getConversationsByUserId(userId: any = null) {
    if(userId) {
      return this.db.getAllFromIndex('conversations', 'by-userId', userId);
    } else {
      return await this.db.getAll('conversations');
    }
  }

  /*
  CRUD operations for the user
  */

  async addUser(user: User) {
    return await this.db.add('user', user);
  }

  async getUser(id: number) {
    return await this.db.get('user', id);
  }

  async updateUser(user: any) {
    return await this.db.put('user', user);
  }

  async deleteUser(id: number) {
    return await this.db.delete('user', id);
  }

  async getAllUsers() {
    return await this.db.getAll('user');
  }

  /*
  CRUD operations for documents
  */
  // TODO: Implement all methods for storing file data

  // Methods for storing file metadata
  async storeFileMetadata(messageId: number, files: FilePreview[]): Promise<void> {
    // TODO: Implement store file info in IndexedDB
  }

}
