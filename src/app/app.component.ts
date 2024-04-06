import { Component } from '@angular/core';
import { StatusBarService } from './status-bar/status-bar.service';


@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})
export class AppComponent {
  title = 'Advanced LLM Chat';

  constructor(private statusService: StatusBarService) { }

  toggleNavbar() {
    this.statusService.toggleSidenav();
  }
}
