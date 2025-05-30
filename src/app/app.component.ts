import { Component, OnInit, OnDestroy } from '@angular/core';
import { StatusBarService } from './status-bar/status-bar.service';
import { AuthService } from './auth/auth.service';
import { Subscription } from 'rxjs';
import { Router } from '@angular/router';


@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  standalone: false
})
export class AppComponent implements OnInit, OnDestroy {
  title = 'Advanced LLM Chat';
  isAuthenticated = false;
  private authSubscription: Subscription | undefined;

  constructor(
    private statusService: StatusBarService,
    private authService: AuthService,
    private router: Router
  ) { }

  ngOnInit() {
    // Subscribe to authentication status
    this.authSubscription = this.authService.currentUser$.subscribe(user => {
      this.isAuthenticated = !!user;
    });
  }

  ngOnDestroy() {
    if (this.authSubscription) {
      this.authSubscription.unsubscribe();
    }
  }

  toggleNavbar() {
    if (this.isAuthenticated) {
      this.statusService.toggleSidenav();
    }
  }

  logout() {
    this.authService.logout().subscribe({
      next: () => {
        console.log('Logged out successfully');
        this.router.navigate(['/login']);
      },
      error: (error) => {
        console.error('Logout error:', error);
        // Navigate to login anyway
        this.router.navigate(['/login']);
      }
    });
  }
}
