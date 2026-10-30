import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { Observable } from 'rxjs';
import { AuthConfig, AuthService } from '../auth/auth.service';

// Errors the backend redirects here with after a failed login through the OIDC provider
const LOGIN_ERRORS: Record<string, string> = {
  auth_failed: 'Login failed. Please try again.',
  provider_unavailable: 'The login service is not reachable. Please try again later.',
  forbidden: 'Your account may not use this app.',
  email_in_use: 'An account with this email already exists. An admin can link it by marking the email as verified.',
};


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

  // How users log in on this server: the OIDC provider, the mock login (email only) or not at all
  authConfig$: Observable<AuthConfig>;

  constructor(
    private authService: AuthService,
    private route: ActivatedRoute
  ) {
    this.authConfig$ = this.authService.authConfig$;
  }

  ngOnInit() {
    // Check for error from failed auth callback
    const error = this.route.snapshot.queryParams['error'];
    if (error) {
      this.error = LOGIN_ERRORS[error] ?? LOGIN_ERRORS['auth_failed'];
    }
  }

  /** The mock login with an email. */
  async login() {
    if (!this.email) {
      this.error = 'Please enter an email';
      return;
    }

    this.loading = true;
    this.error = '';

    try {
      await this.authService.login({ email: this.email });
    } catch (error) {
      this.error = LOGIN_ERRORS['auth_failed'];
    } finally {
      this.loading = false;
    }
  }

  /** The login through the OIDC provider; the browser leaves the app for the provider's login page. */
  async loginWithProvider() {
    this.loading = true;
    this.error = '';
    try {
      await this.authService.login();
    } catch (error) {
      this.loading = false;
      this.error = LOGIN_ERRORS['provider_unavailable'];
    }
  }
}
