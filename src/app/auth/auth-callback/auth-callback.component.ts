import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { AuthService } from '../auth.service';


@Component({
  selector: 'app-auth-callback',
  template: `
    <div class="callback-container">
      <mat-spinner></mat-spinner>
      <p>Completing login...</p>
    </div>
  `,
  styles: [`
    .callback-container {
      height: 100vh;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      gap: 20px;
    }
  `],
  standalone: false
})
export class AuthCallbackComponent implements OnInit {
  constructor(
    private route: ActivatedRoute,
    private authService: AuthService
  ) {}

  ngOnInit() {
    // Get all query params (code, state, etc. for OAuth)
    const params = this.route.snapshot.queryParams;

    // Handle the callback
    this.authService.handleAuthCallback(params);
  }
}
