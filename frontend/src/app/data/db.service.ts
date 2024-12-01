import { Injectable } from '@angular/core';
import { openDB, IDBPDatabase } from 'idb';
import { Message } from './interfaces/message';
import { MainAppDB } from './data-db-schema';
import { Conversation } from './interfaces/conversation';


@Injectable({
  providedIn: 'root'
})
export class DBService {

  // The database instance
  private db!: IDBPDatabase<MainAppDB>;
  private status: Promise<void>;

  constructor() {
    this.status = this.initDB();
  }

  // Initialize the database
  async initDB() {
    console.log("Starting database...");

    // Open the database
    this.db = await openDB<MainAppDB>('main', 1, {
      upgrade(db) {
        // Create a store for messages with 'id' as the key path and a compound index
        const messageStore = db.createObjectStore('chatMessages', { keyPath: 'id' });
        messageStore.createIndex('by-time', 'time');
        messageStore.createIndex('by-conversationId', 'conversationId');
        messageStore.createIndex('by-conversationId-time', ['conversationId', 'time']);

        // Create a store for conversations with 'id' as the key path
        db.createObjectStore('conversations', { keyPath: 'id' });
      }
    });
    console.log("Database started!");
  }

  // Method to add a new entry and generate an ID if needed
  private async addEntry(collectionName: any, newEntry: any) {
    // Check if the message has an 'id' and it's not null
    if (!newEntry.id && newEntry.id !== null) {
      // Variables
      let entryNotAdded = true;
      let retries = 0;

      // Assign a unique ID using the current timestamp
      newEntry.id = Math.floor(new Date().getTime() / 1000);
  
      // Start a loop to retry if an error occurs
      do {
        try {
          // Attempt to add the entry to the database
          await this.db.add(collectionName, newEntry);
          console.log("Entry added to: " + collectionName + " id: " + newEntry.id);

           // If successful, exit the loop by setting the flag to false
          entryNotAdded = false;
        } catch (error) {
          // Increment the ID and try again
          newEntry.id += 1;
          retries += 1;
        }
        // Limit retries to avoid infinite loop
      } while (entryNotAdded && retries < 10);
  
      // If the entry was not added after multiple attempts, throw an error
      if (entryNotAdded) {
        throw new Error('Failed to add entry after multiple attempts.');
      }
    } else {
      // If the message already has an ID, add it to the database
      await this.db.add(collectionName, newEntry);
      console.log("Entry added to: " + collectionName + " id: " + newEntry.id);
    }
  }  

  // Get a promise that resolves when the database is ready
  public getDatabaseReadyPromise() {
    console.log("Waiting for database to be ready...");
    return this.status
  }

  /*
  CRUD operations for messages
  */

  async addMessage(message: Message) {
    return await this.addEntry('chatMessages', message);
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

  async getMessagesByConversationId(conversationId = null) {
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
    return await this.addEntry('conversations', conversation);
  }

  async getConversation(id: number) {
    return await this.db.get('conversations', id);
  }

  async updateConversation(conversation: Conversation) {
    return await this.db.put('conversations', conversation);
  }

  async deleteConversation(id: number) {
    return await this.db.delete('conversations', id);
  }
}
