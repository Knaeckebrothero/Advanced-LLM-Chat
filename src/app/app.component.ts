import { Component, OnDestroy, OnInit } from '@angular/core';
import { DisplayService } from "./sidebar/service/display.service";
import { NavigationEnd, Router } from '@angular/router';
import { Subscription, interval } from 'rxjs';
import { filter } from 'rxjs/operators';
import { ChatService } from './chat/chat.service';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  standalone: false
})
export class AppComponent implements OnInit, OnDestroy {
  title = 'Advanced LLM Chat';
  isLoginPage: boolean = false;
  showMenuIcon: boolean = true;
  private routerSubscription: Subscription | undefined;
  private syncSubscription: Subscription | undefined;
  private visibilityChangeHandler: () => void;

  constructor(
    public displayService: DisplayService, // Kept public for template access from current branch
    private router: Router,
    private chatService: ChatService // Injected from develop branch
  ) {
    // This logic from develop ensures data syncs when the tab becomes active
    this.visibilityChangeHandler = () => {
      if (!document.hidden) {
        this.chatService.syncCurrentConversation();
      }
    };
  }

  ngOnInit() {
    // Combined router event subscription
    this.routerSubscription = this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe((event: NavigationEnd) => {
      const isLoginRoute = event.url === '/login' || event.urlAfterRedirects === '/login';
      // This handles the menu icon visibility from both branches
      this.showMenuIcon = !isLoginRoute;
      // This sets the login page flag from the current branch
      this.isLoginPage = isLoginRoute;
    });

    // This periodic sync logic is from the develop branch
    this.syncSubscription = interval(30000).subscribe(() => {
      this.chatService.syncCurrentConversation();
    });

    // This event listener from develop syncs when the app window regains focus
    document.addEventListener('visibilitychange', this.visibilityChangeHandler);
  }

  ngOnDestroy() {
    // Unsubscribe from all subscriptions and remove event listeners to prevent memory leaks
    if (this.routerSubscription) {
      this.routerSubscription.unsubscribe();
    }

    if (this.syncSubscription) {
      this.syncSubscription.unsubscribe();
    }

    document.removeEventListener('visibilitychange', this.visibilityChangeHandler);
  }
}
