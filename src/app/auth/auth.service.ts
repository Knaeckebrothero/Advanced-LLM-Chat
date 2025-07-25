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
  // Add fields you might get from IDP later
  picture?: string;
  roles?: string[];
  permissions?: string[];
}
// TODO: Change this to use the user interface!

interface LoginProvider {
  type: 'mock' | 'oauth' | 'saml';  // Extensible for future
  config?: any;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private baseUrl: string = environment.apiUrl;
  private currentUserSubject = new BehaviorSubject<User | null>(null);
  public currentUser$ = this.currentUserSubject.asObservable();
  public isGuest = false;

  private guestLimitReachedSubject = new BehaviorSubject<boolean>(false);
  public guestLimitReached$ = this.guestLimitReachedSubject.asObservable();
  private guestLimitResetTimeSubject = new BehaviorSubject<string | null>(null);
  public guestLimitResetTime$ = this.guestLimitResetTimeSubject.asObservable();

  // Promise to track initialization
  private authInitialized: Promise<void>;

  // TODO: This makes it easy to switch providers later
  private loginProvider: LoginProvider = { type: 'mock' };

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
  }

  private async autoGuestLogin(): Promise<void> {
    try {
      // Try to get IP address and create guest session
      const ipResponse = await lastValueFrom(
        this.http.get<{ ip: string }>('https://api.ipify.org?format=json')
      ).catch(() => ({ ip: 'unknown' }));

      const ip_address = ipResponse.ip;

      const response = await lastValueFrom(
        this.http.post<{ user: User, message: string, token: string }>(
          `${this.baseUrl}/api/auth/guest-login`,
          { ip_address },
          { withCredentials: true, observe: 'response' }
        )
      );

      // Extract CSRF token
      this.apiService.extractCsrfToken(response);

      this.isGuest = true;
      this.currentUserSubject.next(response.body!.user);
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
      this.currentUserSubject.next(offlineGuest);
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
        this.http.get<{ user: User }>(
          `${this.baseUrl}/api/auth/me`,
          { withCredentials: true, observe: 'response' }
        )
      );
      console.log('AuthService: /api/auth/me response received:', response);
      
      // Extract CSRF token
      this.apiService.extractCsrfToken(response);
      
      if (response && response.body && response.body.user) {
        this.currentUserSubject.next(response.body.user);
        this.isGuest = response.body.user.email.includes('guest');
        console.log('AuthService: currentUserSubject updated with user:', response.body.user);
        return true;
      } else {
        console.log('AuthService: /api/auth/me response did not contain a valid user object.');
        this.currentUserSubject.next(null);
        return false;
      }
    } catch (error) {
      console.error('AuthService: Error during checkAuthStatus:', error);
      this.currentUserSubject.next(null);
      return false;
    }
  }

  // Generic login method that can handle different providers
  async login(credentials?: any): Promise<void> {
    switch (this.loginProvider.type) {
      case 'mock':
        await this.mockLogin(credentials.email);
        break;
      case 'oauth':
        // Future: Redirect to OAuth provider
        this.redirectToOAuthProvider();
        break;
      case 'saml':
        // Future: Handle SAML flow
        this.initiateSamlLogin();
        break;
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

      this.currentUserSubject.next(response.body!.user);
      this.isGuest = false;
      this.router.navigate(['/']);
      
      // Trigger sync after successful login
      console.log('Triggering sync after login...');
      await this.syncEngine.syncNow();
    } catch (error) {
      console.error('Login failed:', error);
      throw new Error('Login failed');
    }
  }

  // Removed skipLogin method as it's now handled automatically

  // Placeholder for OAuth redirect (implement when adding IDP)
  private redirectToOAuthProvider(): void {
    // Future implementation:
    // window.location.href = `${this.baseUrl}/api/auth/oauth/login`;
    throw new Error('OAuth not implemented yet');
  }

  // Placeholder for SAML (implement when adding IDP)
  private initiateSamlLogin(): void {
    // Future implementation
    throw new Error('SAML not implemented yet');
  }

  // Handle OAuth/SAML callback - call this from a callback component
  async handleAuthCallback(params: any): Promise<void> {
    try {
      const response = await lastValueFrom(
        this.http.post<{ user: User }>(`${this.baseUrl}/api/auth/callback`, params)
      );

      this.currentUserSubject.next(response.user);
      this.isGuest = false;
      this.router.navigate(['/']);
    } catch (error) {
      console.error('Auth callback failed:', error);
      this.router.navigate(['/login'], { queryParams: { error: 'auth_failed' } });
    }
  }

  async logout(): Promise<void> {
    try {
      await lastValueFrom(
        this.http.post(`${this.baseUrl}/api/auth/logout`, {}, { withCredentials: true })
      );
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      // Clear all user data from IndexedDB before switching to guest
      console.log('Clearing user data on logout...');
      await this.dbService.clearAllUserData();
      
      // Clear repository caches
      this.conversationRepository.clearCache();
      this.messageRepository.clearAllCaches();
      
      // After logout, automatically create a new guest session
      await this.autoGuestLogin();
      // Don't navigate away from current page after logout
      // this.router.navigate(['/']);
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

  isAuthenticated(): boolean {
    return this.currentUserSubject.value !== null;
  }
}
