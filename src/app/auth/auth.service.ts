import { Injectable } from '@angular/core';
import { HttpClient, HttpResponse } from '@angular/common/http';
import { Router } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { lastValueFrom } from 'rxjs';
import { environment } from '../environments/environment';
import {take} from "rxjs/operators";
import { SyncEngineService } from '../repositories/sync-engine.service';
import { DBService } from '../data/db.service';
import { ConversationRepository } from '../repositories/conversation.repository';
import { MessageRepository } from '../repositories/message.repository';
import { ApiService } from '../services/api.service';


interface User {
  id: number;
  email: string;
  name: string;
  is_guest?: boolean;
  // Add fields you might get from IDP later
  picture?: string;
  roles?: string[];
  permissions?: string[];
  // Catalog admin (GET /api/auth/me); is_admin is accepted as well, like the snake_case user fields
  isAdmin?: boolean;
  is_admin?: boolean;
}
// TODO: Change this to use the user interface!

/** GET /api/auth/me: the user, and the admin flag (top level and/or in the user object). */
interface MeResponse {
  user: User;
  isAdmin?: boolean;
}

function withAdminFlag(response: MeResponse): User {
  return { ...response.user, isAdmin: response.user.isAdmin ?? response.isAdmin };
}

/** GET /api/auth/config: how users log in on this server (AUTH_MODE); guests can always chat. */
export interface AuthConfig {
  mode: 'oidc' | 'mock' | 'none';
  // The OIDC provider's name for the login button
  providerName?: string | null;
}

// The user whose conversations are stored in this browser (IndexedDB)
const LOCAL_DATA_OWNER_KEY = 'localDataOwner';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private baseUrl: string = environment.apiUrl;
  private currentUserSubject = new BehaviorSubject<User | null>(null);
  public currentUser$ = this.currentUserSubject.asObservable();
  public isGuest = false;

  // Admins manage the model catalog (users in the backend's ADMIN_EMAILS; never guests)
  private isAdminSubject = new BehaviorSubject<boolean>(false);
  public isAdmin$ = this.isAdminSubject.asObservable();

  private guestLimitReachedSubject = new BehaviorSubject<boolean>(false);
  public guestLimitReached$ = this.guestLimitReachedSubject.asObservable();
  private guestLimitResetTimeSubject = new BehaviorSubject<string | null>(null);
  public guestLimitResetTime$ = this.guestLimitResetTimeSubject.asObservable();

  private authConfigSubject = new BehaviorSubject<AuthConfig>({ mode: 'none' });
  public authConfig$ = this.authConfigSubject.asObservable();

  // Promise to track initialization
  private authInitialized: Promise<void>;

  constructor(
    private http: HttpClient,
    private router: Router,
    private syncEngine: SyncEngineService,
    private dbService: DBService,
    private conversationRepository: ConversationRepository,
    private messageRepository: MessageRepository,
    private apiService: ApiService
  ) {
    // Store the promise but don't await it in constructor
    this.authInitialized = this.initializeAuthFlow();
  }

  // Make this return a Promise so APP_INITIALIZER can wait for it
  initializeAuth(): Promise<void> {
    return this.authInitialized;
  }

  private async initializeAuthFlow(): Promise<void> {
    console.log('AuthService: Initializing auth flow...');
    const configLoaded = this.loadAuthConfig();

    try {
      // First try to check if user has existing session
      const hasSession = await this.checkAuthStatus();

      if (!hasSession) {
        // If no existing session, automatically create a guest session
        console.log('AuthService: No existing session, creating guest session...');
        await this.autoGuestLogin();
      }
    } catch (error) {
      console.error('AuthService: Error during initialization, attempting guest login:', error);
      // Even if check fails (e.g., backend down), try guest login
      await this.autoGuestLogin();
    }
    await configLoaded;

    // The first sync, now that the session exists
    void this.syncEngine.syncNow();
  }

  private async loadAuthConfig(): Promise<void> {
    try {
      const config = await lastValueFrom(this.http.get<AuthConfig>(`${this.baseUrl}/api/auth/config`));
      this.authConfigSubject.next(config);
    } catch (error) {
      console.warn('AuthService: Could not load the login options:', error);
    }
  }

  private async autoGuestLogin(): Promise<void> {
    try {
      // The backend rate-limits guests by the IP address of the connection
      const response = await lastValueFrom(
        this.http.post<{ user: User, message: string, token: string }>(
          `${this.baseUrl}/api/auth/guest-login`,
          {},
          { withCredentials: true, observe: 'response' }
        )
      );

      // Extract CSRF token
      this.apiService.extractCsrfToken(response);

      // Every guest session is a new user that only reaches its own conversations, so chats
      // stored in this browser by an earlier (expired) session can't be continued
      await this.clearLocalUserData();
      this.writeLocalDataOwner(response.body!.user);

      this.isGuest = true;
      this.setCurrentUser(response.body!.user);
      console.log('AuthService: Guest session created successfully');
    } catch (error) {
      console.error('AuthService: Guest login failed, creating offline guest:', error);
      // If backend is not available, create a local guest user
      const offlineGuest: User = {
        id: 0,
        email: 'guest@offline',
        name: 'Guest (Offline)'
      };
      this.isGuest = true;
      this.setCurrentUser(offlineGuest);
    }
  }

  setGuestLimitReached(isReached: boolean, resetTime: string | null = null) {
    this.guestLimitReachedSubject.next(isReached);
    this.guestLimitResetTimeSubject.next(resetTime);
  }

  async checkAuthStatus(): Promise<boolean> {
    console.log('AuthService: checkAuthStatus() called.');
    try {
      const response = await lastValueFrom(
        this.http.get<MeResponse>(
          `${this.baseUrl}/api/auth/me`,
          { withCredentials: true, observe: 'response' }
        )
      );
      console.log('AuthService: /api/auth/me response received:', response);

      // Extract CSRF token
      this.apiService.extractCsrfToken(response);

      if (response && response.body && response.body.user) {
        this.isGuest = response.body.user.is_guest === true;
        await this.claimLocalData(response.body.user);
        this.setCurrentUser(withAdminFlag(response.body));
        console.log('AuthService: currentUserSubject updated with user:', response.body.user);
        return true;
      } else {
        console.log('AuthService: /api/auth/me response did not contain a valid user object.');
        this.setCurrentUser(null);
        return false;
      }
    } catch (error) {
      console.error('AuthService: Error during checkAuthStatus:', error);
      this.setCurrentUser(null);
      return false;
    }
  }

  /** Log in the way the server allows (GET /api/auth/config): through its OIDC provider, or with the mock login. */
  async login(credentials?: { email: string }): Promise<void> {
    const mode = this.authConfigSubject.value.mode;
    if (mode === 'oidc') {
      // The backend runs the login with the provider and redirects back to /auth/callback
      window.location.href = `${this.baseUrl}/api/auth/oidc/login`;
    } else if (mode === 'mock' && credentials) {
      await this.mockLogin(credentials.email);
    } else {
      throw new Error('Login is turned off on this server');
    }
  }

  // Keep your existing mock login as a private method
  private async mockLogin(email: string): Promise<void> {
    try {
      const response = await lastValueFrom(
        this.http.post<{ user: User, message: string }>(
          `${this.baseUrl}/api/auth/mock-login`,
          { email },
          { withCredentials: true, observe: 'response' }
        )
      );

      // Extract CSRF token
      this.apiService.extractCsrfToken(response);

      this.isGuest = false;
      await this.claimLocalData(response.body!.user);
      this.setCurrentUser(response.body!.user);
      this.router.navigate(['/']);

      // The login response may not carry the admin flag; /me does
      this.refreshAdminStatus();

      // Trigger sync after successful login
      console.log('Triggering sync after login...');
      await this.syncEngine.syncNow();
    } catch (error) {
      console.error('Login failed:', error);
      throw new Error('Login failed');
    }
  }

  /**
   * Finish a login through the OIDC provider. The backend has set the session cookie and
   * redirected the browser to /auth/callback, so the app has just started with the new session.
   */
  async completeLogin(): Promise<void> {
    await this.initializeAuth();
    if (this.isAuthenticated() && !this.isGuest) {
      this.router.navigate(['/']);
      await this.syncEngine.syncNow();
    } else {
      this.router.navigate(['/login'], { queryParams: { error: 'auth_failed' } });
    }
  }

  async logout(): Promise<void> {
    // After an OIDC login, the provider's session ends too (logoutUrl)
    let logoutUrl: string | null = null;
    try {
      const response = await lastValueFrom(
        this.http.post<{ logoutUrl?: string | null }>(`${this.baseUrl}/api/auth/logout`, {}, { withCredentials: true })
      );
      logoutUrl = response?.logoutUrl ?? null;
    } catch (error) {
      console.error('Logout error:', error);
    }

    // Clear all user data before switching to guest
    console.log('Clearing user data on logout...');
    await this.clearLocalUserData();

    if (logoutUrl) {
      // The provider redirects back to the app, which then starts a guest session
      window.location.href = logoutUrl;
      return;
    }

    // After logout, automatically create a new guest session
    await this.autoGuestLogin();
    this.router.navigate(['/login']); // Ensure redirection to login page
  }

  /** Remove the conversations, messages and settings stored in this browser, and the repository caches. */
  private async clearLocalUserData(): Promise<void> {
    await this.dbService.clearAllUserData();
    this.conversationRepository.clearCache();
    this.messageRepository.clearAllCaches();
  }

  /**
   * The conversations stored in this browser belong to one user: clear them when another
   * user's session starts (e.g. a guest logs in). Data without a known owner is kept.
   */
  private async claimLocalData(user: User): Promise<void> {
    let owner: string | null = null;
    try {
      owner = localStorage.getItem(LOCAL_DATA_OWNER_KEY);
    } catch {
      // Storage unavailable: nothing to compare with
    }
    if (owner !== null && owner !== String(user.id)) {
      console.log('AuthService: Another user logged in, clearing the data stored in this browser');
      await this.clearLocalUserData();
    }
    this.writeLocalDataOwner(user);
  }

  private writeLocalDataOwner(user: User): void {
    try {
      localStorage.setItem(LOCAL_DATA_OWNER_KEY, String(user.id));
    } catch {
      // Storage unavailable
    }
  }

  // Add method to check specific permissions (useful with IDP)
  hasPermission(permission: string): boolean {
    const user = this.currentUserSubject.value;
    return user?.permissions?.includes(permission) || false;
  }

  // Add method to check roles (useful with IDP)
  hasRole(role: string): boolean {
    const user = this.currentUserSubject.value;
    return user?.roles?.includes(role) || false;
  }

  getCurrentUser(): User | null {
    return this.currentUserSubject.value;
  }

  /** Whether the current user may manage the model catalog. */
  get isAdmin(): boolean {
    return this.isAdminSubject.value;
  }

  private setCurrentUser(user: User | null): void {
    // Update the admin flag first, so subscribers of currentUser$ see a consistent state
    this.isAdminSubject.next(this.readIsAdmin(user));
    this.currentUserSubject.next(user);
  }

  private readIsAdmin(user: User | null): boolean {
    if (!user || this.isGuest) return false;
    return user.isAdmin === true || user.is_admin === true;
  }

  /** Re-read the admin flag from /api/auth/me (login responses may leave it out). */
  private async refreshAdminStatus(): Promise<void> {
    try {
      const response = await lastValueFrom(
        this.http.get<MeResponse>(`${this.baseUrl}/api/auth/me`, { withCredentials: true })
      );
      if (response?.user) {
        this.isAdminSubject.next(this.readIsAdmin(withAdminFlag(response)));
      }
    } catch (error) {
      console.warn('AuthService: Could not refresh the admin flag:', error);
    }
  }

  isAuthenticated(): boolean {
    return this.currentUserSubject.value !== null;
  }
}
