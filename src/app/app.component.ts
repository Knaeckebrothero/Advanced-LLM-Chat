import { Component, OnDestroy, OnInit } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { Subscription, interval, of } from 'rxjs';
import { filter, catchError } from 'rxjs/operators';

// Services
import { DisplayService } from "./sidebar/service/display.service";
import { ChatService } from './chat/chat.service';
import { SettingsService } from './settings/settings.service';
import { ThemeService } from "../styles/themes/theme.service";

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
    public displayService: DisplayService,
    private router: Router,
    private chatService: ChatService,
    private settingsService: SettingsService,
    private themeService: ThemeService
  ) {
    this.visibilityChangeHandler = () => {
      if (!document.hidden) {
        this.chatService.syncCurrentConversation();
      }
    };
  }

  ngOnInit() {
    // Load the user's saved theme immediately on startup to prevent a "flash"
    this.loadUserTheme();

    // Subscribe to router events to determine if the login page is active
    this.routerSubscription = this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe((event: NavigationEnd) => {
      this.isLoginPage = event.url === '/login' || event.urlAfterRedirects === '/login';
      this.showMenuIcon = !this.isLoginPage;
    });

    // Periodically sync the current conversation every 30 seconds
    this.syncSubscription = interval(30000).subscribe(() => {
      this.chatService.syncCurrentConversation();
    });

    // Add an event listener to sync when the window regains focus
    document.addEventListener('visibilitychange', this.visibilityChangeHandler);
  }

  ngOnDestroy() {
    // Unsubscribe from all subscriptions to prevent memory leaks
    if (this.routerSubscription) {
      this.routerSubscription.unsubscribe();
    }
    if (this.syncSubscription) {
      this.syncSubscription.unsubscribe();
    }
    document.removeEventListener('visibilitychange', this.visibilityChangeHandler);
  }

  /**
   * Fetches user settings on app load to apply the correct theme.
   * This prevents a flash of the default theme before the user's preference is loaded.
   */
  private loadUserTheme(): void {
    this.settingsService.getSettings().pipe(
      // If the call fails (e.g., user not logged in), catch the error
      // and continue gracefully by returning a null observable.
      catchError(() => of(null))
    ).subscribe(settings => {
      if (settings && settings.theme) {
        // If settings were loaded, apply the saved theme.
        this.themeService.setTheme(settings.theme);
      } else {
        // If no settings were found, apply the OS default theme as a fallback.
        this.themeService.setTheme('os');
      }
    });
  }
}
