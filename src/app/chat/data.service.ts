import { Injectable } from '@angular/core';
import { openDB, DBSchema, IDBPDatabase } from 'idb';
import { Message } from './message-interface';

interface ChatDB extends DBSchema {
  messages: {
    key: string;
    value: Message;
    indexes: { 'by-time': Date };
  };
  agents: {
    key: string;
    value: { id: string; name: string; email?: string };
  };
}

@Injectable({
  providedIn: 'root'
})
export class DataService {

  // The database instance
  private db!: IDBPDatabase<ChatDB>;
  private status: Promise<void>;

  constructor() {
    this.status = this.initDB();
  }

  // Initialize the database
  async initDB() {
    console.log("Starting database...");
    this.db = await openDB<ChatDB>('chat-db', 1, {
      upgrade(db) {
        // Create a store for messages with 'id' as the key path
        const messageStore = db.createObjectStore('messages', { keyPath: 'id' });
        // Create an index on the 'time' property of the messages
        messageStore.createIndex('by-time', 'time');
      }
    });
    console.log("Database started!");
  }

  // Get a promise that resolves when the database is ready
  public getDatabaseReadyPromise() {
    console.log("Waiting for database to be ready...");
    return this.status
  }

  // Get all messages from the database
  async getAllMessages() {
    return await this.db.getAll('messages');
  }

  /*
  CRUD operations for messages
  */

  async addMessage(message: Message) {
    return await this.db.add('messages', message);
  }

  async getMessage(id: string) {
    return await this.db.get('messages', id);
  }

  async updateMessage(message: Message) {
    return await this.db.put('messages', message);
  }

  async deleteMessage(id: string) {
    return await this.db.delete('messages', id);
  }
}