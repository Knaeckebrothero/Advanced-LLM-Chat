import { Component, OnInit, OnDestroy } from '@angular/core';
import { Router, NavigationEnd } from '@angular/router'; // Import Router and NavigationEnd
import { StatusBarService } from './status-bar/status-bar.service';
import { Subscription } from 'rxjs'; // Import Subscription
import { filter } from 'rxjs/operators'; // Import filter operator

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  standalone: false
})
export class AppComponent implements OnInit, OnDestroy {
  title = 'Advanced LLM Chat';
  showMenuIcon: boolean = true; // Property to control menu icon visibility
  private routerSubscription: Subscription | undefined; // To store the subscription

  constructor(
    private statusService: StatusBarService,
    private router: Router // Inject Router
  ) {}

  ngOnInit() {
    this.routerSubscription = this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe((event: NavigationEnd) => {
      // Check if the current route is the login page
      this.showMenuIcon = !(event.url === '/login' || event.urlAfterRedirects === '/login');
    });
  }

  toggleNavbar() {
    this.statusService.toggleSidenav();
  }

  ngOnDestroy() {
    // Unsubscribe to prevent memory leaks
    if (this.routerSubscription) {
      this.routerSubscription.unsubscribe();
    }
  }
}
