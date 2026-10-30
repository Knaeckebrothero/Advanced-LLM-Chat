import { Component, OnInit } from '@angular/core';
import { AuthService } from '../auth.service';


@Component({
  selector: 'app-auth-callback',
  template: `
    <div class="callback-container">
      <mat-spinner></mat-spinner>
      <p>{{ 'Completing login...' | translate }}</p>
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
/** Where the backend sends the browser after a login through the OIDC provider. */
export class AuthCallbackComponent implements OnInit {
  constructor(private authService: AuthService) {}

  ngOnInit() {
    this.authService.completeLogin();
  }
}
