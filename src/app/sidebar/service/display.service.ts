import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class DisplayService implements OnDestroy {
  private isSidebarOpenSubject = new BehaviorSubject<boolean>(true);
  public isSidebarOpen$: Observable<boolean> = this.isSidebarOpenSubject.asObservable();

  public activeConversationId$ = new BehaviorSubject<number | null>(null);
  private resizeListener: () => void;

  constructor() {
    this.handleResize(); // Set initial state
    this.resizeListener = () => this.handleResize();
    window.addEventListener('resize', this.resizeListener);
  }

  // Cleanup on destruction to prevent memory leaks
  ngOnDestroy() {
    if (this.resizeListener) {
      window.removeEventListener('resize', this.resizeListener);
    }
  }

  public setActiveConversation(conversationId: number | null) {
    this.activeConversationId$.next(conversationId);
  }

  private handleResize(): void {
    const mobile = this.isMobile();
    const currentState = this.isSidebarOpenSubject.value;

    if (mobile) {
      // If screen becomes mobile and sidebar is open, close it.
      if (currentState) {
        this.isSidebarOpenSubject.next(false);
      }
    } else {
      // If screen becomes desktop and sidebar is closed, open it.
      if (!currentState) {
        this.isSidebarOpenSubject.next(true);
      }
    }
  }

  public toggleSidebar(): void {
    this.isSidebarOpenSubject.next(!this.isSidebarOpenSubject.value);
  }

  public openSidebar(): void {
    if (!this.isSidebarOpenSubject.value) {
      this.isSidebarOpenSubject.next(true);
    }
  }

  public closeSidebar(): void {
    if (this.isSidebarOpenSubject.value) {
      this.isSidebarOpenSubject.next(false);
    }
  }

  public closeSidebarOnMobile(): void {
    if (this.isMobile()) {
      this.closeSidebar();
    }
  }

  public isMobile(): boolean {
    return window.innerWidth <= 768; // Matches SCSS breakpoint
  }

  public getCurrentSidebarState(): boolean {
    return this.isSidebarOpenSubject.value;
  }
}
