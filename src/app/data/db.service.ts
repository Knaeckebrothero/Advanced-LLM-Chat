import { Injectable } from '@angular/core';
import { openDB, IDBPDatabase } from 'idb';
import { Message } from './interfaces/chat-message';
import { MainAppDB } from './data-db-schema';
import { OpenAIChatCompleteRequest } from './interfaces/api-openai-request';


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
    this.db = await openDB<MainAppDB>('chat-db', 1, {
      upgrade(db) {
        // Create a store for messages with 'id' as the key path and an index on 'time'
        const messageStore = db.createObjectStore('chatMessages', { keyPath: 'id' });
        messageStore.createIndex('by-time', 'time');

        // Create a store for API configurations with 'id' as the key path
        db.createObjectStore('llmConfigs', { keyPath: 'id' });
      }
    });
    console.log("Database started!");
  }

  private generateID(newEntry: any) {
    // Check if the message has an 'id' and it's not null
    if (!newEntry.id && newEntry.id !== null) {
      // Assign a unique ID using the current timestamp
      newEntry.id = new Date().toString() + "-" + Math.random().toString();
    }
    return newEntry;
  }

  // Get a promise that resolves when the database is ready
  public getDatabaseReadyPromise() {
    console.log("Waiting for database to be ready...");
    return this.status
  }

  /* Methods that do not work propperly or have to be implemented
  // Get API settings and config from the database
  async getApiSetup(settingsID: string) {
    this.db.get('llmConfigs', settingsID).then((setupSettings) => {
      if (setupSettings != undefined) {
        this.db.get('apiConfigs', where settingsID = setupSettings.settingsID).then((setupConfig) => {
        return setupConfig, setupSettings;
      } else {
        console.error("API setup not found!");
        return null;
      }
    });
  }

  // Get the API config by settingsID
  async getApiConfigBySettingsID(settingsID: string) {
    // Wait for the database to be ready
    await this.getDatabaseReadyPromise();

    // Start a transaction and open the 'apiConfigs' object store
    const transaction = this.db.transaction('apiConfigs', 'readonly');
    const store = transaction.objectStore('apiConfigs');

    // Create an array to hold the results
    let apiConfigs: any[] = [];

    // Open a cursor to iterate over all records in the store
    const request = store.openCursor();
    request.onsuccess = (event: any) => {
      const cursor = event.target.result;
      if (cursor) {
        // Check if the current record's settingsID matches the provided settingsID
        if (cursor.value.settingsID === settingsID) {
          apiConfigs.push(cursor.value);
        }
        cursor.continue(); // Move to the next record
      }
    };

    // Wait for the transaction to complete
    await transaction.done;

    // Return the first match or null if none
    return apiConfigs.length > 0 ? apiConfigs[0] : null;
  }
  */

  /*
  CRUD operations for messages
  */

  async addMessage(message: Message) {
    return await this.db.add('chatMessages', this.generateID(message));
  }

  async getMessage(id: string) {
    return await this.db.get('chatMessages', id);
  }

  async updateMessage(message: Message) {
    return await this.db.put('chatMessages', message);
  }

  async deleteMessage(id: string) {
    return await this.db.delete('chatMessages', id);
  }

  async deleteAllMessages() {
    return await this.db.clear('chatMessages');
  }

  async getAllMessages() {
    return await this.db.getAll('chatMessages');
  }

  /*
  CRUD operations for OpenAI LLM configurations
  */

  async addLLMConfig(config: OpenAIChatCompleteRequest) {
    return await this.db.add('llmConfigs', this.generateID(config));
  }

  async getLLMConfig(id: string) {
    return await this.db.get('llmConfigs', id);
  }

  async updateLLMConfig(config: OpenAIChatCompleteRequest) {
    return await this.db.put('llmConfigs', config);
  }

  async deleteLLMConfig(id: string) {
    return await this.db.delete('llmConfigs', id);
  }

  async getAllLLMConfigs() {
    return await this.db.getAll('llmConfigs');
  }
}
