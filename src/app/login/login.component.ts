import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { AuthService } from '../auth/auth.service';

@Component({
  selector: 'app-login',
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.scss'],
  standalone: false
})
export class LoginComponent implements OnInit {
  email: string = '';
  error: string = '';
  loading: boolean = false;

  // This allows you to easily switch between mock and IDP login
  useMockLogin: boolean = true; // Set to false when you implement IDP

  constructor(
    private authService: AuthService,
    private route: ActivatedRoute
  ) {}

  ngOnInit() {
    // Check for error from failed auth callback
    const error = this.route.snapshot.queryParams['error'];
    if (error === 'auth_failed') {
      this.error = 'Authentication failed. Please try again.';
    }
  }

  async login() {
    if (this.useMockLogin) {
      if (!this.email) {
        this.error = 'Please enter an email';
        return;
      }

      this.loading = true;
      this.error = '';

      try {
        await this.authService.login({ email: this.email });
      } catch (error) {
        this.error = 'Login failed. Please try again.';
      } finally {
        this.loading = false;
      }
    } else {
      // For IDP login, just call login without credentials
      // The auth service will handle the redirect
      try {
        await this.authService.login();
      } catch (error) {
        this.error = 'Login provider not available';
      }
    }
  }

  // Alternative method for IDP login button
  loginWithProvider() {
    this.loading = true;
    this.authService.login();
  }
}
