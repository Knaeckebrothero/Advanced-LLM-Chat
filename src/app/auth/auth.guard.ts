import { Injectable } from '@angular/core';
import { CanActivate, Router, UrlTree } from '@angular/router';
import { from, Observable } from 'rxjs';
import { map, switchMap, take } from 'rxjs/operators';
import { AuthService } from './auth.service';


@Injectable({
  providedIn: 'root'
})
export class AuthGuard implements CanActivate {
  constructor(
    private authService: AuthService,
    private router: Router
  ) {}

  canActivate(): Observable<boolean | UrlTree> {
    console.log('AuthGuard checking authentication...');
    // Wait for auth initialization before checking user state
    // This fixes the race condition where take(1) grabbed null before guest login completed
    return from(this.authService.initializeAuth()).pipe(
      switchMap(() => this.authService.currentUser$.pipe(take(1))),
      map(user => {
        console.log('Current user in guard:', user);

        // Check if user exists (either authenticated or guest)
        if (user) {
          // User is authenticated (could be guest or regular user)
          return true;
        } else {
          // No user found, redirect to login
          console.log('No user found, redirecting to login');
          return this.router.createUrlTree(['/login']);
        }
      })
    );
  }
}
