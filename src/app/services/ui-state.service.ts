import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Observable, fromEvent, merge } from 'rxjs';
import { map, shareReplay, distinctUntilChanged, debounceTime, takeUntil } from 'rxjs/operators';
import { Subject } from 'rxjs';

export interface UIState {
  isSidebarOpen: boolean;
  isMobile: boolean;
  isTablet: boolean;
  isDesktop: boolean;
  viewportWidth: number;
  viewportHeight: number;
  activeConversationId: string | null;
}

export interface Breakpoints {
  mobile: number;
  tablet: number;
  desktop: number;
}

@Injectable({
  providedIn: 'root'
})
export class UIStateService implements OnDestroy {
  private destroy$ = new Subject<void>();
  
  // Default breakpoints (matching SCSS)
  private breakpoints: Breakpoints = {
    mobile: 768,
    tablet: 1024,
    desktop: 1280
  };
  
  // State subjects
  private isSidebarOpen$ = new BehaviorSubject<boolean>(true);
  public activeConversationId$ = new BehaviorSubject<string | null>(null);
  private viewportSize$ = new BehaviorSubject<{ width: number; height: number }>({
    width: window.innerWidth,
    height: window.innerHeight
  });
  
  // Responsive breakpoint observables
  public isMobile$: Observable<boolean> = this.viewportSize$.pipe(
    map(size => size.width <= this.breakpoints.mobile),
    distinctUntilChanged(),
    shareReplay(1)
  );
  
  public isTablet$: Observable<boolean> = this.viewportSize$.pipe(
    map(size => size.width > this.breakpoints.mobile && size.width <= this.breakpoints.tablet),
    distinctUntilChanged(),
    shareReplay(1)
  );
  
  public isDesktop$: Observable<boolean> = this.viewportSize$.pipe(
    map(size => size.width > this.breakpoints.tablet),
    distinctUntilChanged(),
    shareReplay(1)
  );
  
  // Combined UI state
  public state$: Observable<UIState> = this.viewportSize$.pipe(
    map(size => ({
      isSidebarOpen: this.isSidebarOpen$.getValue(),
      isMobile: size.width <= this.breakpoints.mobile,
      isTablet: size.width > this.breakpoints.mobile && size.width <= this.breakpoints.tablet,
      isDesktop: size.width > this.breakpoints.tablet,
      viewportWidth: size.width,
      viewportHeight: size.height,
      activeConversationId: this.activeConversationId$.getValue()
    })),
    shareReplay(1)
  );
  
  // Individual observables
  public sidebarOpen$ = this.isSidebarOpen$.asObservable();
  public activeConversationId = this.activeConversationId$.asObservable();
  public viewportSize = this.viewportSize$.asObservable();
  
  constructor() {
    this.initializeResponsiveHandling();
    this.initializeSidebarBehavior();
  }
  
  /**
   * Initialize responsive viewport handling
   */
  private initializeResponsiveHandling(): void {
    // Listen to window resize events
    fromEvent(window, 'resize')
      .pipe(
        debounceTime(100), // Debounce resize events
        takeUntil(this.destroy$)
      )
      .subscribe(() => {
        this.viewportSize$.next({
          width: window.innerWidth,
          height: window.innerHeight
        });
      });
    
    // Also listen for orientation changes on mobile
    fromEvent(window, 'orientationchange')
      .pipe(
        debounceTime(100),
        takeUntil(this.destroy$)
      )
      .subscribe(() => {
        // Small delay to ensure dimensions are updated
        setTimeout(() => {
          this.viewportSize$.next({
            width: window.innerWidth,
            height: window.innerHeight
          });
        }, 100);
      });
  }
  
  /**
   * Initialize sidebar responsive behavior
   */
  private initializeSidebarBehavior(): void {
    // Auto-close sidebar on mobile, auto-open on desktop
    this.isMobile$
      .pipe(takeUntil(this.destroy$))
      .subscribe(isMobile => {
        if (isMobile && this.isSidebarOpen$.getValue()) {
          this.closeSidebar();
        } else if (!isMobile && !this.isSidebarOpen$.getValue()) {
          this.openSidebar();
        }
      });
  }
  
  /**
   * Toggle sidebar open/closed
   */
  toggleSidebar(): void {
    this.isSidebarOpen$.next(!this.isSidebarOpen$.getValue());
  }
  
  /**
   * Open sidebar
   */
  openSidebar(): void {
    if (!this.isSidebarOpen$.getValue()) {
      this.isSidebarOpen$.next(true);
    }
  }
  
  /**
   * Close sidebar
   */
  closeSidebar(): void {
    if (this.isSidebarOpen$.getValue()) {
      this.isSidebarOpen$.next(false);
    }
  }
  
  /**
   * Close sidebar only on mobile
   */
  closeSidebarOnMobile(): void {
    const viewportSize = this.viewportSize$.getValue();
    if (viewportSize.width <= this.breakpoints.mobile) {
      this.closeSidebar();
    }
  }
  
  /**
   * Set active conversation ID
   */
  setActiveConversation(conversationId: string | null): void {
    this.activeConversationId$.next(conversationId);
  }
  
  /**
   * Get current state synchronously
   */
  getCurrentState(): UIState {
    const size = this.viewportSize$.getValue();
    return {
      isSidebarOpen: this.isSidebarOpen$.getValue(),
      isMobile: size.width <= this.breakpoints.mobile,
      isTablet: size.width > this.breakpoints.mobile && size.width <= this.breakpoints.tablet,
      isDesktop: size.width > this.breakpoints.tablet,
      viewportWidth: size.width,
      viewportHeight: size.height,
      activeConversationId: this.activeConversationId$.getValue()
    };
  }
  
  /**
   * Get current sidebar state (synchronous)
   */
  get isSidebarOpen(): boolean {
    return this.isSidebarOpen$.getValue();
  }
  
  /**
   * Get current mobile state (synchronous)
   */
  get isMobile(): boolean {
    return window.innerWidth <= this.breakpoints.mobile;
  }
  
  /**
   * Check if current viewport is tablet
   */
  isTablet(): boolean {
    const width = window.innerWidth;
    return width > this.breakpoints.mobile && width <= this.breakpoints.tablet;
  }
  
  /**
   * Check if current viewport is desktop
   */
  isDesktop(): boolean {
    return window.innerWidth > this.breakpoints.tablet;
  }
  
  /**
   * Update custom breakpoints
   */
  setBreakpoints(breakpoints: Partial<Breakpoints>): void {
    this.breakpoints = { ...this.breakpoints, ...breakpoints };
    // Trigger re-evaluation
    this.viewportSize$.next({
      width: window.innerWidth,
      height: window.innerHeight
    });
  }
  
  /**
   * Get current sidebar state
   */
  getCurrentSidebarState(): boolean {
    return this.isSidebarOpen$.getValue();
  }
  
  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}