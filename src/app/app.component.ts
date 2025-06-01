import {Component, OnDestroy, OnInit} from '@angular/core';
import {DisplayService} from "./sidebar/service/display.service";


import {NavigationEnd, Router} from '@angular/router'; // Import Router and NavigationEnd
import {Subscription} from 'rxjs'; // Import Subscription
import {filter} from 'rxjs/operators'; // Import filter operator


@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  standalone: false // This makes AppComponent a non-standalone component
})
export class AppComponent implements OnInit, OnDestroy {
  title = 'Advanced LLM Chat';
  showMenuIcon: boolean = true; // Property to control menu icon visibility
  private routerSubscription: Subscription | undefined; // To store the subscription

  // Make displayService public to allow template to access its methods and observables
  constructor(public displayService: DisplayService,
              private router: Router // Inject Router


  ) {
  }


  ngOnInit() {
    this.routerSubscription = this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe((event: NavigationEnd) => {
      // Check if the current route is the login page
      this.showMenuIcon = !(event.url === '/login' || event.urlAfterRedirects === '/login');
    });
  }

  ngOnDestroy() {
    // Unsubscribe to prevent memory leaks
    if (this.routerSubscription) {
      this.routerSubscription.unsubscribe();
    }
  }
}
