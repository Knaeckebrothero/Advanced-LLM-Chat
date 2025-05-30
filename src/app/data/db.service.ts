import { Injectable } from '@angular/core';
import { openDB, IDBPDatabase } from 'idb';
import { Message } from './objects/message';
import { MainAppDB } from './db-schema';
import { Conversation } from './objects/conversation';
import { User } from './objects/user';


@Injectable({
  providedIn: 'root'
})
export class DBService {

  private db!: IDBPDatabase<MainAppDB>;
  private status: Promise<void>;

  constructor() {
    this.status = this.initDB();
  }

  async initDB() {
    console.log("Starting database...");
    this.db = await openDB<MainAppDB>('main', 1, {
      upgrade(db) {
        if (!db.objectStoreNames.contains('user')) {
          db.createObjectStore('user', { keyPath: 'id' });
        }
        if (!db.objectStoreNames.contains('conversations')) {
          const conversationStore = db.createObjectStore('conversations', { keyPath: 'id' });
          if (!conversationStore.indexNames.contains('by-userId')) {
            conversationStore.createIndex('by-userId', 'userId');
          }
        }
        if (!db.objectStoreNames.contains('chatMessages')) {
          const messageStore = db.createObjectStore('chatMessages', { keyPath: 'id' });
          if (!messageStore.indexNames.contains('by-conversationId')) {
            messageStore.createIndex('by-conversationId', 'conversationId');
          }
          if (!messageStore.indexNames.contains('by-conversationId-time')) {
            messageStore.createIndex('by-conversationId-time', ['conversationId', 'time']);
          }
        }
      }
    });
    console.log("Database started!");
  }

  public getDatabaseReadyPromise() {
    console.log("Waiting for database to be ready...");
    return this.status;
  }

  // User operations
  async addUser(user: User) {
    const existingUser = await this.getUser(user.id);
    if (existingUser) {
      console.log(`User ${user.id} already in DB, updating.`);
      await this.db.put('user', user);
    } else {
      console.log(`Adding new user ${user.id} to DB.`);
      await this.db.add('user', user);
    }
    return user;
  }

  async getUser(id: number): Promise<User | undefined> {
    return await this.db.get('user', id);
  }

  async updateUser(user: User) {
    const key = await this.db.put('user', user);
    return key;
  }

  async deleteUser(id: number) {
    const result = await this.db.delete('user', id);
    return result;
  }

  async getAllUsers(): Promise<User[]> {
    return await this.db.getAll('user');
  }

  // CRUD operations for messages
  async addMessage(message: Message) {
    return await this.db.add('chatMessages', message);
  }

  async getMessage(id: number): Promise<Message | undefined> {
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
    for (const message of messages) {
      if (typeof message.id === 'number') {
        await this.deleteMessage(message.id);
      }
    }
  }

  async getMessagesByConversationId(conversationId: number | null = null): Promise<Message[]> {
    if(conversationId !== null) {
      return this.db.getAllFromIndex('chatMessages', 'by-conversationId', IDBKeyRange.only(conversationId));
    } else {
      return await this.db.getAll('chatMessages');
    }
  }

  // CRUD operations for conversations
  async addConversation(conversation: Conversation) {
    return await this.db.add('conversations', conversation);
  }

  async getConversation(id: number): Promise<Conversation | undefined> {
    return await this.db.get('conversations', id);
  }

  async updateConversation(conversation: Conversation) {
    return await this.db.put('conversations', conversation);
  }

  async deleteConversation(id: number) {
    return await this.db.delete('conversations', id);
  }

  async getConversationsByUserId(userId: number | null = null): Promise<Conversation[]> {
    if(userId !== null) {
      return this.db.getAllFromIndex('conversations', 'by-userId', IDBKeyRange.only(userId));
    } else {
      return await this.db.getAll('conversations');
    }
  }
}
