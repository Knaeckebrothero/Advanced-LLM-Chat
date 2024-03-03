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

  constructor() {
    this.initDB();
  }

  async initDB() {
    this.db = await openDB<ChatDB>('chat-db', 1, {
      upgrade(db) {
        // Create a store for messages with 'id' as the key path
        const messageStore = db.createObjectStore('messages', { keyPath: 'id' });
        // Create an index on the 'time' property of the messages
        messageStore.createIndex('by-time', 'time');
      }
    });
  }

  // CRUD operations for messages
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

  async getAllMessages() {
    return await this.db.getAll('messages');
  }
}