import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { StatusBarService } from './status-bar.service';

@Component({
  selector: 'app-status-bar',
  templateUrl: './status-bar.component.html',
  styleUrls: ['./status-bar.component.scss']
})
export class StatusBarComponent {

  constructor(
    public statusService: StatusBarService,
    private router: Router
  ) {}

  navigate(route: string) {
    this.router.navigate([route]);
    this.statusService.toggleSidenav();
  }
}
