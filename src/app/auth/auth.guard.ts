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
        if (user) {
          console.log('User authenticated, allowing access');
          return true;
        }
        console.log('User not authenticated, redirecting to login');
        return this.router.createUrlTree(['/login']);
      })
    );
  }
}
