import { Injectable } from '@angular/core';
import { HttpInterceptor, HttpRequest, HttpHandler, HttpEvent, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { Router } from '@angular/router';
import { ApiService } from '../services/api.service';


@Injectable()
export class AuthInterceptor implements HttpInterceptor {
  constructor(
    private router: Router,
    private apiService: ApiService
  ) {}

  intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    // Clone the request and add withCredentials to include cookies
    let authReq = req.clone({
      withCredentials: true
    });

    // Add CSRF token if available and not already present
    const csrfToken = this.apiService.csrfToken;
    if (csrfToken && !req.headers.has('X-CSRF-Token')) {
      authReq = authReq.clone({
        headers: authReq.headers.set('X-CSRF-Token', csrfToken)
      });
      console.log('AuthInterceptor: Added CSRF token to request:', req.url);
    } else if (!csrfToken) {
      console.warn('AuthInterceptor: No CSRF token available for request:', req.url);
    }

    return next.handle(authReq).pipe(
      catchError((error: HttpErrorResponse) => {
        if (error.status === 401) {
          // User is not authenticated, redirect to login
          this.router.navigate(['/login']);
        } else if (error.status === 403 && error.error?.error === 'CSRF validation failed') {
          console.error('CSRF validation failed for request:', req.url);
          // Could implement CSRF token refresh here
        }
        return throwError(() => error);
      })
    );
  }
}
