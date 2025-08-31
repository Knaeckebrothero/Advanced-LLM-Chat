import { Component, OnDestroy, OnInit, HostListener } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { Subscription, interval, combineLatest } from 'rxjs';
import { filter, map } from 'rxjs/operators';
import { ChatService } from './services/chat.service';
import { ThemeService } from './services/theme.service';
import { UIStateService } from './services/ui-state.service';
import { AuthService } from './auth/auth.service';
import { TranslateService } from '@ngx-translate/core';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  standalone: false
})
export class AppComponent implements OnInit, OnDestroy {
  title = 'Fessi';
  showMenuIcon: boolean = false; // Initialize to false to prevent showing on load
  private subscriptions = new Subscription();
  private readonly visibilityChangeHandler: () => void;

  constructor(
    public uiState: UIStateService,
    private router: Router,
    private chatService: ChatService,
    private themeService: ThemeService, // Injected the service
    private authService: AuthService,
    private translate: TranslateService
  ) {
    // Bind the handler so we can remove it later
    this.visibilityChangeHandler = () => {
      if (!document.hidden) {
        this.chatService.syncCurrentConversation();
      }
    };
  }

  ngOnInit() {
    // Theme is automatically initialized in the ThemeService constructor
    this.themeService.initializeTheme();

    this.setViewportHeight();

    // Initialize sidebar state CSS variable
    this.initializeSidebarState();

    const routerEvents$ = this.router.events.pipe(
      filter((event): event is NavigationEnd => event instanceof NavigationEnd)
    );

    // A user is considered authenticated for UI purposes if a user object exists (includes guests)
    const isAuthenticated$ = this.authService.currentUser$.pipe(
      map(user => !!user)
    );

    // Combine router and auth state to determine sidebar visibility
    this.subscriptions.add(
      combineLatest([routerEvents$, isAuthenticated$]).subscribe(([navigationEnd, isAuthenticated]) => {
        const url = navigationEnd.urlAfterRedirects;
        // Show the menu icon if the user is authenticated and not on the login page
        this.showMenuIcon = isAuthenticated && url !== '/login';
      })
    );

    // TODO: Make this a env variable instead of a hardcoded value!
    // Periodic sync every 60 seconds
    this.subscriptions.add(interval(60000).subscribe(() => {
      this.chatService.syncCurrentConversation();
    }));

    // Sync when app regains focus
    document.addEventListener('visibilitychange', this.visibilityChangeHandler);

    // Subscribe to sidebar state changes and update CSS variable
    this.subscriptions.add(this.uiState.sidebarOpen$.subscribe(isOpen => {
      this.updateSidebarState(isOpen);
    }));
  }

  ngOnDestroy() {
    // Unsubscribe to prevent memory leaks
    this.subscriptions.unsubscribe();

    // Remove event listener using the same handler reference
    document.removeEventListener('visibilitychange', this.visibilityChangeHandler);
  }

  @HostListener('window:resize')
  onResize() {
    this.setViewportHeight();
  }

  /**
   * Sets a CSS variable for the actual viewport height to handle mobile browser chrome
   */
  private setViewportHeight() {
    const vh = window.innerHeight * 0.01;
    document.documentElement.style.setProperty('--vh', `${vh}px`);
  }

  /**
   * Initialize sidebar state CSS variable
   */
  private initializeSidebarState() {
    const currentState = this.uiState.isSidebarOpen;
    document.documentElement.style.setProperty('--sidebar-state', currentState ? '1' : '0');
  }

  /**
   * Update sidebar state CSS variable for smooth animations
   */
  private updateSidebarState(isOpen: boolean) {
    document.documentElement.style.setProperty('--sidebar-state', isOpen ? '1' : '0');
  }
}
