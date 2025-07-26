import { Injectable } from '@angular/core';
import { CanActivate, Router, UrlTree } from '@angular/router';
import { Observable } from 'rxjs';
import { map, take } from 'rxjs/operators';
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
    return this.authService.currentUser$.pipe(
      take(1),
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
