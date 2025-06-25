import {Component, OnDestroy, OnInit} from '@angular/core';
import {DisplayService} from "./sidebar/service/display.service";
import {NavigationEnd, Router} from '@angular/router';
import {Subscription, interval} from 'rxjs';
import {filter} from 'rxjs/operators';
import {ChatService} from './chat/chat.service';


@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  standalone: false
})
export class AppComponent implements OnInit, OnDestroy {
  title = 'Advanced LLM Chat';
  showMenuIcon: boolean = true;
  private routerSubscription: Subscription | undefined;
  private syncSubscription: Subscription | undefined;
  private visibilityChangeHandler: () => void; // Store the handler reference

  constructor(
    public displayService: DisplayService,
    private router: Router,
    private chatService: ChatService // Use proper type instead of 'any'
  ) {
    // Bind the handler so we can remove it later
    this.visibilityChangeHandler = () => {
      if (!document.hidden) {
        this.chatService.syncCurrentConversation();
      }
    };
  }

  ngOnInit() {
    // Router subscription
    this.routerSubscription = this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe((event: NavigationEnd) => {
      this.showMenuIcon = !(event.url === '/login' || event.urlAfterRedirects === '/login');
    });

    // Periodic sync every 30 seconds
    this.syncSubscription = interval(30000).subscribe(() => {
      this.chatService.syncCurrentConversation();
    });

    // Sync when app regains focus
    document.addEventListener('visibilitychange', this.visibilityChangeHandler);
  }

  ngOnDestroy() {
    // Unsubscribe to prevent memory leaks
    if (this.routerSubscription) {
      this.routerSubscription.unsubscribe();
    }

    if (this.syncSubscription) {
      this.syncSubscription.unsubscribe();
    }

    // Remove event listener using the same handler reference
    document.removeEventListener('visibilitychange', this.visibilityChangeHandler);
  }
}
