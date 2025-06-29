import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { lastValueFrom } from 'rxjs';
import { environment } from '../environments/environment';
import {take} from "rxjs/operators";


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
    private router: Router
  ) {
    // Store the promise but don't await it in constructor
    this.authInitialized = this.checkAuthStatus();
  }

  // Make this return a Promise so APP_INITIALIZER can wait for it
  initializeAuth(): Promise<void> {
    return this.authInitialized;
  }

  setGuestLimitReached(isReached: boolean, resetTime: string | null = null) {
    this.guestLimitReachedSubject.next(isReached);
    this.guestLimitResetTimeSubject.next(resetTime);
  }

  async checkAuthStatus(): Promise<void> {
    console.log('AuthService: checkAuthStatus() called.');
    try {
      const response = await lastValueFrom(
        this.http.get<{ user: User }>(
          `${this.baseUrl}/api/auth/me`,
          { withCredentials: true }
        )
      );
      console.log('AuthService: /api/auth/me response received:', response);
      if (response && response.user) {
        this.currentUserSubject.next(response.user);
        console.log('AuthService: currentUserSubject updated with user:', response.user);
      } else {
        console.log('AuthService: /api/auth/me response did not contain a valid user object.');
        this.currentUserSubject.next(null);
      }
    } catch (error) {
      console.error('AuthService: Error during checkAuthStatus:', error);
      this.currentUserSubject.next(null);
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
          { withCredentials: true }
        )
      );

      this.currentUserSubject.next(response.user);
      this.isGuest = false;
      this.router.navigate(['/']);
    } catch (error) {
      console.error('Login failed:', error);
      throw new Error('Login failed');
    }
  }

  async skipLogin(): Promise<void> {
    try {
      const ipResponse = await lastValueFrom(this.http.get<{ ip: string }>('https://api.ipify.org?format=json'));
      const ip_address = ipResponse.ip;

      const response = await lastValueFrom(
        this.http.post<{ user: User, message: string, token: string }>(
          `${this.baseUrl}/api/auth/guest-login`,
          { ip_address },
          { withCredentials: true }
        )
      );

      this.isGuest = true;
      this.currentUserSubject.next(response.user);
      this.router.navigate(['/']);
    } catch (error) {
      console.error('Guest login failed:', error);
      // Optionally show an error to the user
      throw new Error('Guest login failed');
    }
  }


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
      this.currentUserSubject.next(null);
      this.isGuest = false;
      // For IDP logout, you might need to redirect to IDP logout URL
      if (this.loginProvider.type === 'oauth' && !this.isGuest) {
        // window.location.href = `${idpLogoutUrl}`;
      } else {
        this.router.navigate(['/login']);
      }
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
