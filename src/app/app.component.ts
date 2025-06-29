import {Component, OnDestroy, OnInit, HostListener} from '@angular/core';
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
  private readonly visibilityChangeHandler: () => void; // Store the handler reference

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
    // Set the CSS variable for viewport height (existing functionality)
    this.setViewportHeight();

    // Initialize sidebar state CSS variable
    this.initializeSidebarState();

    // Router subscription
    this.routerSubscription = this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe((event: NavigationEnd) => {
      this.showMenuIcon = !(event.url === '/login' || event.urlAfterRedirects === '/login');
    });

    // TODO: Make this a env variable instead of a hardcoded value!
    // Periodic sync every 60 seconds
    this.syncSubscription = interval(60000).subscribe(() => {
      this.chatService.syncCurrentConversation();
    });

    // Sync when app regains focus
    document.addEventListener('visibilitychange', this.visibilityChangeHandler);

    // Subscribe to sidebar state changes and update CSS variable
    this.displayService.isSidebarOpen$.subscribe(isOpen => {
      this.updateSidebarState(isOpen);
    });
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
    const currentState = this.displayService.getCurrentSidebarState();
    document.documentElement.style.setProperty('--sidebar-state', currentState ? '1' : '0');
  }

  /**
   * Update sidebar state CSS variable for smooth animations
   */
  private updateSidebarState(isOpen: boolean) {
    document.documentElement.style.setProperty('--sidebar-state', isOpen ? '1' : '0');
  }
}
