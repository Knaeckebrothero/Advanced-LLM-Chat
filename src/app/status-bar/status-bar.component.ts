import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { StatusBarService } from './status-bar.service';
import { AuthService } from '../auth/auth.service';

@Component({
    selector: 'app-status-bar',
    templateUrl: './status-bar.component.html',
    styleUrls: ['./status-bar.component.scss'],
    standalone: false
})
export class StatusBarComponent {

  constructor(
    public statusService: StatusBarService,
    private router: Router,
    private authService: AuthService
  ) {}

  navigate(route: string) {
    this.router.navigate([route]);
    this.statusService.toggleSidenav();
  }

  async logout() {
    await this.authService.logout();
    this.statusService.toggleSidenav();
  }
}
