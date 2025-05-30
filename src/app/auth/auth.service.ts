import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { BehaviorSubject, Observable, throwError } from 'rxjs';
import { map, catchError, tap } from 'rxjs/operators';
import { Router } from '@angular/router';
import { environment } from '../environments/environment';

interface LoginResponse {
  user: {
    id: number;
    name: string;
    email: string;
  };
  token: string;
}

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private baseUrl = environment.apiUrl;
  private currentUserSubject = new BehaviorSubject<any>(null);
  public currentUser$ = this.currentUserSubject.asObservable();

  private tokenCookieName = 'sessionToken';
  private userCookieName = 'currentUser';
  private sessionCheckInterval: any;

  constructor(
    private http: HttpClient,
    private router: Router
  ) {
    // Check if user is already logged in
    this.checkStoredSession();
    // Start session check interval
    this.startSessionCheck();
  }

  private getCookie(name: string): string | null {
    const nameEQ = name + "=";
    const ca = document.cookie.split(';');
    for (let i = 0; i < ca.length; i++) {
      let c = ca[i];
      while (c.charAt(0) === ' ') c = c.substring(1, c.length);
      if (c.indexOf(nameEQ) === 0) return decodeURIComponent(c.substring(nameEQ.length, c.length));
    }
    return null;
  }

  private setCookie(name: string, value: string, hours: number = 1) {
    const date = new Date();
    date.setTime(date.getTime() + (hours * 60 * 60 * 1000));
    const expires = "expires=" + date.toUTCString();
    // Only add Secure flag if using HTTPS
    const secure = window.location.protocol === 'https:' ? ';Secure' : '';
    document.cookie = `${name}=${encodeURIComponent(value)};${expires};path=/;SameSite=Lax${secure}`;
  }

  private deleteCookie(name: string) {
    const secure = window.location.protocol === 'https:' ? ';Secure' : '';
    document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 UTC;path=/;SameSite=Lax${secure}`;
  }

  private checkStoredSession() {
    const token = this.getCookie(this.tokenCookieName);
    const userStr = this.getCookie(this.userCookieName);

    if (token && userStr) {
      try {
        const userData = JSON.parse(userStr);
        this.currentUserSubject.next(userData);
      } catch (e) {
        this.clearSession();
      }
    }
  }

  private startSessionCheck() {
    // Check session validity every 5 minutes
    this.sessionCheckInterval = setInterval(() => {
      this.validateSession();
    }, 5 * 60 * 1000);
  }

  login(username: string, password: string): Observable<LoginResponse> {
    const endpoint = `${this.baseUrl}/api/auth/login`;

    return this.http.post<LoginResponse>(endpoint, { username, password })
      .pipe(
        tap(response => {
          // Store token and user info in cookies (1 hour expiry)
          this.setCookie(this.tokenCookieName, response.token, 1);
          this.setCookie(this.userCookieName, JSON.stringify(response.user), 1);
          this.currentUserSubject.next(response.user);
        }),
        catchError(error => {
          console.error('Login failed:', error);
          return throwError(() => error);
        })
      );
  }

  logout(): Observable<any> {
    const endpoint = `${this.baseUrl}/api/auth/logout`;
    const token = this.getToken();

    if (!token) {
      this.clearSession();
      return throwError(() => new Error('No session to logout'));
    }

    const headers = new HttpHeaders({
      'Authorization': `Bearer ${token}`
    });

    return this.http.post(endpoint, {}, { headers })
      .pipe(
        tap(() => this.clearSession()),
        catchError(error => {
          // Clear session even if logout fails
          this.clearSession();
          return throwError(() => error);
        })
      );
  }

  private clearSession() {
    this.deleteCookie(this.tokenCookieName);
    this.deleteCookie(this.userCookieName);
    this.currentUserSubject.next(null);

    if (this.sessionCheckInterval) {
      clearInterval(this.sessionCheckInterval);
    }

    this.router.navigate(['/login']);
  }

  getToken(): string | null {
    return this.getCookie(this.tokenCookieName);
  }

  getCurrentUser(): any {
    return this.currentUserSubject.value;
  }

  isAuthenticated(): boolean {
    return !!this.getToken() && !!this.getCurrentUser();
  }

  private validateSession() {
    const token = this.getToken();
    if (!token) {
      this.clearSession();
      return;
    }

    const endpoint = `${this.baseUrl}/api/auth/session-info`;
    const headers = new HttpHeaders({
      'Authorization': `Bearer ${token}`
    });

    this.http.get(endpoint, { headers })
      .pipe(
        catchError(error => {
          if (error.status === 401) {
            // Session expired or invalid
            this.clearSession();
          }
          return throwError(() => error);
        })
      )
      .subscribe();
  }

  ngOnDestroy() {
    if (this.sessionCheckInterval) {
      clearInterval(this.sessionCheckInterval);
    }
  }
}
