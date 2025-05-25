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

  // The database instance
  private db!: IDBPDatabase<MainAppDB>;
  private status: Promise<void>;

  // User cookie key
  private readonly USER_COOKIE_KEY = 'currentUserAppSession'; // Unique key

  constructor() {
    this.status = this.initDB().then(() => this.initializeDefaultState());
  }

  async initDB() {
    console.log("Starting database...");
    this.db = await openDB<MainAppDB>('main', 1, {
      upgrade(db) {
        db.createObjectStore('user', { keyPath: 'id' });
        const conversationStore = db.createObjectStore('conversations', { keyPath: 'id' });
        conversationStore.createIndex('by-userId', 'userId');
        const messageStore = db.createObjectStore('chatMessages', { keyPath: 'id' });
        messageStore.createIndex('by-conversationId', 'conversationId');
        messageStore.createIndex('by-conversationId-time', ['conversationId', 'time']);
      }
    });
    console.log("Database started!");
  }

  // --- Cookie Methods ---
  private saveUserToCookie(user: User): void {
    const cookieValue = JSON.stringify({
      id: user.id,
      name: user.name,
      accessToken: user.accessToken,
      email: user.email
    });
    // Cookie expires in 10 hours from now
    const expires = new Date(Date.now() + 10 * 60 * 60 * 1000).toUTCString();
    document.cookie = `${this.USER_COOKIE_KEY}=${encodeURIComponent(cookieValue)}; expires=${expires}; path=/; SameSite=Lax; Secure`;
    console.log("User saved to cookie (10 hour expiry):", user.name, "");
  }

  private getUserFromCookie(): User | null {
    const cookies = document.cookie.split(';').map(cookie => cookie.trim());
    const userCookie = cookies.find(cookie => cookie.startsWith(`${this.USER_COOKIE_KEY}=`));

    if (userCookie) {
      try {
        const cookieValue = decodeURIComponent(userCookie.substring(this.USER_COOKIE_KEY.length + 1));
        const userData = JSON.parse(cookieValue);
        if (userData && typeof userData.id !== 'undefined' && userData.name && userData.accessToken && userData.email) {
          return userData as User;
        } else {
          console.warn("Malformed user data in cookie, clearing.");
          this.clearUserCookie(); // Clear malformed cookie
          return null;
        }
      } catch (error) {
        console.error("Error parsing user cookie:", error);
        this.clearUserCookie();
        return null;
      }
    }
    return null;
  }

  private clearUserCookie(): void {
    document.cookie = `${this.USER_COOKIE_KEY}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; SameSite=Lax; Secure`;
    console.log("User cookie cleared.");
  }
  // --- End Cookie Methods ---

  private async initializeDefaultState() {
    console.log("Checking cookie and db state...");
    let user = this.getUserFromCookie();

    if (user) {
      console.log("User found in cookie:", user.name, "");
      const dbUser = await this.getUser(user.id);
      if (!dbUser) {
        console.log("User from cookie not in DB, adding to DB...");
        await this.addUser(user, false);
      }
    } else {
      console.log("No user found in cookie. Checking DB for any user...");
      const usersInDb = await this.getAllUsers();
      if (usersInDb && usersInDb.length > 0) {
        user = usersInDb[0];
        console.log("User found in DB, saving to cookie:", user.name, "");
        this.saveUserToCookie(user);
      } else {
        console.log("No user in DB. Creating default user as per original logic...");
        const defaultUser: User = {
          id: 0,
          accessToken: "defaultUser",
          email: "defaultUser@example.com",
          name: "Default User"
        };
        await this.addUser(defaultUser, true);
        user = defaultUser;
        console.log("Default user created and saved to cookie:", user.name, "");
      }
    }
  }

  public getDatabaseReadyPromise() {
    console.log("Waiting for database to be ready...");
    return this.status;
  }

  /* CRUD operations for messages */
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
      // Use IDBKeyRange.only for a specific value lookup on an index
      return this.db.getAllFromIndex('chatMessages', 'by-conversationId', IDBKeyRange.only(conversationId));
    } else {
      return await this.db.getAll('chatMessages');
    }
  }

  /* CRUD operations for conversations */
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
      // Use IDBKeyRange.only for a specific value lookup on an index
      return this.db.getAllFromIndex('conversations', 'by-userId', IDBKeyRange.only(userId));
    } else {
      return await this.db.getAll('conversations');
    }
  }

  /* CRUD operations for the user */
  async addUser(user: User, saveCookie: boolean = true) {
    await this.db.add('user', user);
    if (saveCookie) {
      this.saveUserToCookie(user);
    }
    return user;
  }

  async getUser(id: number): Promise<User | undefined> {
    return await this.db.get('user', id);
  }

  async updateUser(user: User, saveCookie: boolean = true) {
    const key = await this.db.put('user', user);
    if (saveCookie) {
      this.saveUserToCookie(user);
    }
    return key;
  }

  async deleteUser(id: number) {
    const result = await this.db.delete('user', id);
    const cookieUser = this.getUserFromCookie();
    if (cookieUser && cookieUser.id === id) {
      this.clearUserCookie();
    }
    return result;
  }

  async getAllUsers(): Promise<User[]> {
    return await this.db.getAll('user');
  }

  async getCurrentUser(): Promise<User | null> {
    await this.status;
    let user = this.getUserFromCookie();
    if (user) {
      return user;
    }
    const users = await this.getAllUsers();
    if (users && users.length > 0) {
      this.saveUserToCookie(users[0]);
      return users[0];
    }
    return null;
  }
}
