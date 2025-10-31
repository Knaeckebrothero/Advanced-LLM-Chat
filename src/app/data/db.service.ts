import { Injectable } from '@angular/core';
import { openDB, IDBPDatabase } from 'idb';
import { Message } from './objects/message';
import { MainAppDB, ConversationSyncMetadata } from './db-schema';
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
    this.db = await openDB<MainAppDB>('main', 4, {
      upgrade: async (db, oldVersion, newVersion, transaction) => {
        // Upgrade from version 0 (new database) or version 1
        if (oldVersion < 1) {
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

        // Add settings store in version 2
        if (oldVersion < 2) {
          // Create a store for settings
          db.createObjectStore('settings', { keyPath: 'id' });
        }

        // Add version fields in version 3
        if (oldVersion < 3 && oldVersion > 0) {
          console.log('Migrating database to version 3: Adding version fields');
          
          // Add version to existing messages
          const messageStore = transaction.objectStore('chatMessages');
          const messageCursor = await messageStore.openCursor();
          
          let messageCount = 0;
          while (messageCursor) {
            const message = messageCursor.value;
            if (!message.version) {
              message.version = 1;
              message.lastModified = message.time ? Math.floor(new Date(message.time).getTime() / 1000) : Math.floor(Date.now() / 1000);
              await messageCursor.update(message);
              messageCount++;
            }
            await messageCursor.continue();
          }
          console.log(`Updated ${messageCount} messages with version information`);
          
          // Add version to existing conversations
          const conversationStore = transaction.objectStore('conversations');
          const conversationCursor = await conversationStore.openCursor();
          
          let conversationCount = 0;
          while (conversationCursor) {
            const conversation = conversationCursor.value;
            if (!conversation.version) {
              conversation.version = 1;
              conversation.lastModified = Math.floor(Date.now() / 1000);
              await conversationCursor.update(conversation);
              conversationCount++;
            }
            await conversationCursor.continue();
          }
          console.log(`Updated ${conversationCount} conversations with version information`);
        }
        
        // Add syncMetadata store in version 4
        if (oldVersion < 4) {
          console.log('Migrating database to version 4: Adding syncMetadata store');
          db.createObjectStore('syncMetadata', { keyPath: 'id' });
        }
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

  // Get the database instance (for repositories)
  public async getDb(): Promise<IDBPDatabase<MainAppDB>> {
    await this.status;
    return this.db;
  }

  // Helper method to generate UUID-like IDs
  public generateUUID(): string {
    // Simple UUID v4-like generator
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = Math.random() * 16 | 0;
      const v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
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
    // Serialize the message before storing
    const serialized = message.toJSON();
    return await this.db.add('chatMessages', serialized);
  }

  async getMessage(id: number) {
    const data = await this.db.get('chatMessages', id);
    // Deserialize the message when retrieving
    return data ? Message.fromJSON(data) : undefined;
  }

  async updateMessage(message: Message) {
    // Increment version and update lastModified before saving
    message.version = (message.version || 1) + 1;
    message.lastModified = Math.floor(Date.now() / 1000);
    
    // Serialize the message before updating
    const serialized = message.toJSON();
    return await this.db.put('chatMessages', serialized);
  }

  async deleteMessage(id: number) {
    return await this.db.delete('chatMessages', id);
  }

  async deleteAllMessages() {
    return await this.db.clear('chatMessages');
  }

  async deleteMessagesByConversationId(conversationId: string) {
    return this.executeTransaction(['chatMessages'], 'readwrite', async (tx) => {
      const store = tx.objectStore('chatMessages');
      const index = store.index('by-conversationId');
      const messages = await index.getAll(conversationId);
      
      // Delete all messages in the transaction
      for (const message of messages) {
        await store.delete(message.id);
      }
    });
  }

  async getMessagesByConversationId(conversationId: any = null) {
    let rawMessages;
    if(conversationId) {
      rawMessages = await this.db.getAllFromIndex('chatMessages', 'by-conversationId', conversationId);
    } else {
      rawMessages = await this.db.getAll('chatMessages');
    }
    // Deserialize all messages
    return rawMessages.map(data => Message.fromJSON(data));
  }

  async getAllMessages(): Promise<Message[]> {
    await this.status;
    const rawMessages = await this.db.getAll('chatMessages');
    // Deserialize all messages
    return rawMessages.map(data => Message.fromJSON(data));
  }

  /*
  CRUD operations for conversations
  */

  async addConversation(conversation: Conversation) {
    return await this.db.add('conversations', conversation);
  }

  async getConversation(id: string) {
    const data = await this.db.get('conversations', id);
    return data ? Conversation.fromPlainObject(data) : undefined;
  }

  // Retrieves all conversations from the local IndexedDB, sorted by most recently updated first.
  public async getAllConversations(): Promise<Conversation[]> {
    const db = this.db;
    await this.status;
    const rawConversations = await this.db.getAll('conversations');
    
    // Convert to Conversation instances
    const conversations = rawConversations.map(data => Conversation.fromPlainObject(data));

    // Sort by updatedAt descending (newest first)
    conversations.sort((a, b) => {
      const dateA = new Date(a.updatedAt).getTime();
      const dateB = new Date(b.updatedAt).getTime();
      return dateB - dateA;
    });

    return conversations;
  }


  async updateConversation(conversation: Conversation) {
    // Increment version and update lastModified before saving
    conversation.version = (conversation.version || 1) + 1;
    conversation.lastModified = Math.floor(Date.now() / 1000);
    
    return await this.db.put('conversations', conversation);
  }

  async deleteConversation(id: string) {
    return await this.db.delete('conversations', id);
  }

  /**
   * Clear all user data from IndexedDB
   * Used during logout to ensure clean state
   */
  async clearAllUserData() {
    console.log('Clearing all user data from IndexedDB...');
    
    await this.executeTransaction(['chatMessages', 'conversations', 'user'], 'readwrite', async (tx) => {
      // Clear all messages
      await tx.objectStore('chatMessages').clear();
      
      // Clear all conversations
      await tx.objectStore('conversations').clear();
      
      // Clear user store (settings, etc.)
      await tx.objectStore('user').clear();
      
      console.log('All user data cleared from IndexedDB (excluding syncMetadata)');
    });
    
    // Clear sync metadata separately
    await this.status;
    await this.db.clear('syncMetadata');
  }

  async getConversationsByUserId(userId: any = null) {
    let rawConversations;
    if(userId) {
      rawConversations = await this.db.getAllFromIndex('conversations', 'by-userId', userId);
    } else {
      rawConversations = await this.db.getAll('conversations');
    }
    // Convert to Conversation instances
    return rawConversations.map(data => Conversation.fromPlainObject(data));
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

  /**
   * Execute multiple database operations in a transaction
   * Ensures all operations succeed or all fail atomically
   */
  async executeTransaction<T>(
    storeNames: Array<'chatMessages' | 'conversations' | 'user' | 'settings'>, 
    mode: 'readonly' | 'readwrite', 
    operations: (tx: any) => Promise<T>
  ): Promise<T> {
    await this.status;
    const tx = this.db.transaction(storeNames as any, mode);
    
    try {
      const result = await operations(tx);
      await tx.done;
      return result;
    } catch (error) {
      // Transaction will automatically abort on error
      throw error;
    }
  }

  /**
   * Replace all messages for a conversation atomically
   * Used during sync to ensure data consistency
   */
  async replaceConversationMessages(
    conversationId: string, 
    messages: Message[]
  ): Promise<void> {
    return this.executeTransaction(['chatMessages'], 'readwrite', async (tx) => {
      const store = tx.objectStore('chatMessages');
      
      // Get all existing messages for this conversation
      const index = store.index('by-conversationId');
      const existingMessages = await index.getAll(conversationId);
      
      // Delete existing messages
      for (const msg of existingMessages) {
        await store.delete(msg.id);
      }
      
      // Add new messages
      for (const msg of messages) {
        // Ensure message has all required fields before adding
        if (!msg.id) {
          console.error('Message missing id:', msg);
          throw new Error('Cannot add message without id');
        }
        // Serialize message before storing
        const serialized = msg.toJSON();
        await store.add(serialized);
      }
    });
  }

  /**
   * Get messages for a conversation with a limit
   * Used for implementing the caching strategy
   */
  async getRecentMessagesByConversationId(
    conversationId: string, 
    limit: number = 20
  ): Promise<Message[]> {
    // Use the existing method to get all messages for the conversation
    const messages = await this.getMessagesByConversationId(conversationId);
    
    // Sort by time descending and take the limit
    messages.sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime());
    const recentMessages = messages.slice(0, limit);
    
    // Sort back to chronological order for display
    recentMessages.sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());
    
    return recentMessages;
  }

  /**
   * Update conversation with transaction support
   * Ensures atomicity when updating conversation metadata
   */
  async updateConversationTransactional(
    conversation: Conversation,
    messageUpdates?: { messages: Message[] }
  ): Promise<void> {
    const stores: Array<'conversations' | 'chatMessages'> = ['conversations'];
    if (messageUpdates) stores.push('chatMessages');
    
    return this.executeTransaction(stores, 'readwrite', async (tx) => {
      // Increment version and update lastModified
      conversation.version = (conversation.version || 1) + 1;
      conversation.lastModified = Math.floor(Date.now() / 1000);
      
      // Update conversation
      await tx.objectStore('conversations').put(conversation);
      
      // Update messages if provided
      if (messageUpdates) {
        const messageStore = tx.objectStore('chatMessages');
        for (const msg of messageUpdates.messages) {
          // Increment message version
          msg.version = (msg.version || 1) + 1;
          msg.lastModified = Math.floor(Date.now() / 1000);
          
          const serialized = msg.toJSON();
          await messageStore.put(serialized);
        }
      }
    });
  }

  /**
   * Delete conversation and all its messages atomically
   */
  async deleteConversationWithMessages(conversationId: string): Promise<void> {
    return this.executeTransaction(['conversations', 'chatMessages'], 'readwrite', async (tx) => {
      // Delete conversation
      await tx.objectStore('conversations').delete(conversationId);
      
      // Delete all messages
      const messageStore = tx.objectStore('chatMessages');
      const index = messageStore.index('by-conversationId');
      const messages = await index.getAll(conversationId);
      
      for (const message of messages) {
        await messageStore.delete(message.id);
      }
    });
  }

  /**
   * Add multiple messages in a single transaction
   * Used for batch operations during sync
   */
  async addMessagesTransactional(messages: Message[]): Promise<void> {
    return this.executeTransaction(['chatMessages'], 'readwrite', async (tx) => {
      const store = tx.objectStore('chatMessages');
      
      for (const msg of messages) {
        const serialized = msg.toJSON();
        await store.add(serialized);
      }
    });
  }

  /**
   * Update multiple messages in a single transaction
   */
  async updateMessagesTransactional(messages: Message[]): Promise<void> {
    return this.executeTransaction(['chatMessages'], 'readwrite', async (tx) => {
      const store = tx.objectStore('chatMessages');
      
      for (const msg of messages) {
        // Increment version and update lastModified
        msg.version = (msg.version || 1) + 1;
        msg.lastModified = Math.floor(Date.now() / 1000);
        
        const serialized = msg.toJSON();
        await store.put(serialized);
      }
    });
  }

  /**
   * Create a backup of conversation data before sync operations
   * Returns the backup data that can be restored if sync fails
   */
  async backupConversationData(conversationId: string): Promise<{
    conversation: Conversation | undefined;
    messages: Message[];
  }> {
    return this.executeTransaction(['conversations', 'chatMessages'], 'readonly', async (tx) => {
      // Get conversation
      const conversationData = await tx.objectStore('conversations').get(conversationId);
      const conversation = conversationData ? Conversation.fromPlainObject(conversationData) : undefined;
      
      // Get all messages
      const messageStore = tx.objectStore('chatMessages');
      const index = messageStore.index('by-conversationId');
      const rawMessages = await index.getAll(conversationId);
      const messages = rawMessages.map((data: any) => Message.fromJSON(data));
      
      return { conversation, messages };
    });
  }

  /**
   * Restore conversation data from backup
   * Used when sync operations fail
   */
  async restoreConversationData(
    conversationId: string,
    backup: { conversation: Conversation | undefined; messages: Message[] }
  ): Promise<void> {
    return this.executeTransaction(['conversations', 'chatMessages'], 'readwrite', async (tx) => {
      // Restore conversation if it existed
      if (backup.conversation) {
        await tx.objectStore('conversations').put(backup.conversation);
      }
      
      // Clear current messages and restore from backup
      const messageStore = tx.objectStore('chatMessages');
      const index = messageStore.index('by-conversationId');
      const currentMessages = await index.getAll(conversationId);
      
      // Delete current messages
      for (const msg of currentMessages) {
        await messageStore.delete(msg.id);
      }
      
      // Restore backup messages
      for (const msg of backup.messages) {
        const serialized = msg.toJSON();
        await messageStore.add(serialized);
      }
    });
  }

  /**
   * Get sync metadata for a conversation
   */
  async getSyncMetadata(conversationId: string): Promise<ConversationSyncMetadata | undefined> {
    await this.status;
    return this.db.get('syncMetadata', conversationId);
  }

  /**
   * Save sync metadata for a conversation
   */
  async saveSyncMetadata(metadata: ConversationSyncMetadata): Promise<void> {
    await this.status;
    await this.db.put('syncMetadata', metadata);
  }

  /**
   * Delete sync metadata for a conversation
   */
  async deleteSyncMetadata(conversationId: string): Promise<void> {
    await this.status;
    await this.db.delete('syncMetadata', conversationId);
  }

  /**
   * Get all sync metadata
   */
  async getAllSyncMetadata(): Promise<ConversationSyncMetadata[]> {
    await this.status;
    return this.db.getAll('syncMetadata');
  }

}
