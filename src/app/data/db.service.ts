import { Injectable, inject } from '@angular/core'; // Added inject
import { openDB, IDBPDatabase } from 'idb';
import { Message } from './objects/message';
import { MainAppDB } from './db-schema';
import { Conversation } from './objects/conversation';
import { User } from './objects/user';
import { ApiService } from '../api/api.service'; // Import ApiService


@Injectable({
  providedIn: 'root'
})
export class DBService {

  private db!: IDBPDatabase<MainAppDB>;
  private status: Promise<void>;
  private readonly USER_COOKIE_KEY = 'currentUserAppSession';

  // Use inject for ApiService if constructor is complex or for newer Angular patterns
  private apiService = inject(ApiService);

  constructor() {
    // ApiService will be injected.
    // Initialize DB first, then attempt to fetch session info.
    this.status = this.initDB().then(() => this.initializeSessionState());
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

  private saveUserToCookie(user: User): void {
    const cookieValue = JSON.stringify({
      id: user.id,
      name: user.name,
      accessToken: user.accessToken,
      email: user.email
    });
    const expires = new Date(Date.now() + 10 * 60 * 60 * 1000).toUTCString(); // 10 hours
    document.cookie = `${this.USER_COOKIE_KEY}=${encodeURIComponent(cookieValue)}; expires=${expires}; path=/; SameSite=Lax; Secure`;
    console.log("User saved to cookie (10 hour expiry):", user.name, user.id);
  }

  private getUserFromCookie(): User | null {
    const cookies = document.cookie.split(';').map(cookie => cookie.trim());
    const userCookie = cookies.find(cookie => cookie.startsWith(`${this.USER_COOKIE_KEY}=`));

    if (userCookie) {
      try {
        const cookieValue = decodeURIComponent(userCookie.substring(this.USER_COOKIE_KEY.length + 1));
        const userData = JSON.parse(cookieValue);
        if (userData && typeof userData.id !== 'undefined' && userData.name && userData.accessToken) { // email can be optional if not always set
          return userData as User;
        } else {
          console.warn("Malformed user data in cookie, clearing.");
          this.clearUserCookie();
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

  // Renamed from initializeDefaultState to reflect new logic
  private async initializeSessionState() {
    console.log("Initializing session state...");

    // 1. Try to fetch session info from backend
    try {
      const sessionInfo = await this.apiService.fetchSessionInfo();
      if (sessionInfo && sessionInfo.user && sessionInfo.token) {
        console.log("Session info fetched from backend:", sessionInfo.user.name);
        // The user object from backend already includes the token as accessToken
        await this.addUser(sessionInfo.user, true); // Save to DB and cookie
        return; // Session established from backend
      } else {
        console.warn("Could not fetch session info from backend, or response was invalid.");
      }
    } catch (error) {
      console.error("Error fetching session info from backend:", error);
      // Proceed to fallback if backend fetch fails
    }

    // 2. Fallback: Check cookie
    console.log("Falling back to cookie/DB check for user session.");
    let user = this.getUserFromCookie();

    if (user) {
      console.log("User found in cookie:", user.name, user.id);
      const dbUser = await this.getUser(user.id);
      if (!dbUser) {
        console.log("User from cookie not in DB, adding to DB...");
        await this.addUser(user, false); // Already in cookie, just add to DB
      }
      return; // Session established from cookie
    }

    // 3. Fallback: Check DB for any user (e.g., if cookie was cleared but DB persisted)
    console.log("No user found in cookie. Checking DB for any user...");
    const usersInDb = await this.getAllUsers();
    if (usersInDb && usersInDb.length > 0) {
      user = usersInDb[0]; // Use the first user found in DB
      console.log("User found in DB, saving to cookie:", user.name, user.id);
      this.saveUserToCookie(user);
      return; // Session established from DB
    }

    // 4. Fallback: Create a "truly default" user if nothing else worked (optional)
    // This ensures the app can run even if backend is down and no prior session existed.
    // You might want to remove this if a backend-provided session is strictly mandatory.
    console.log("No user in DB. Creating truly default user as a last resort...");
    const defaultUser: User = {
      id: 0, // Default local ID
      accessToken: "localDefaultUserToken", // Different token to signify it's local
      email: "local.default@example.com",
      name: "Local Default User"
    };
    await this.addUser(defaultUser, true); // Save to DB and cookie
    console.log("Truly default user created and saved:", defaultUser.name);
  }


  public getDatabaseReadyPromise() {
    console.log("Waiting for database to be ready...");
    return this.status;
  }

  async addUser(user: User, saveCookie: boolean = true) {
    // Check if user already exists to avoid constraint errors, or use put for upsert
    const existingUser = await this.getUser(user.id);
    if (existingUser) {
      console.log(`User ${user.id} already in DB, updating.`);
      await this.db.put('user', user);
    } else {
      console.log(`Adding new user ${user.id} to DB.`);
      await this.db.add('user', user);
    }

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
    await this.status; // Ensure DB and session initialization is complete
    let user = this.getUserFromCookie(); // Primary source of truth for current session
    if (user) {
      return user;
    }
    // This part is mostly a fallback if cookie is somehow lost but was expected by initializeSessionState
    // initializeSessionState should handle setting the cookie if a user is found/created
    console.warn("getCurrentUser: No user in cookie after initialization. This might indicate an issue.");
    const users = await this.getAllUsers(); // Check DB as a last resort
    if (users && users.length > 0) {
      console.warn("getCurrentUser: Found user in DB but not in cookie. Using first DB user.");
      this.saveUserToCookie(users[0]); // Attempt to restore cookie
      return users[0];
    }
    console.error("getCurrentUser: Critical - No user could be determined.");
    return null;
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
