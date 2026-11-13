import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { NavigationEnd, Router } from '@angular/router';
import { Conversation } from '../data/objects/conversation';
import { ConversationComponent } from './conversation/conversation.component';
import { MatIcon } from "@angular/material/icon";
import { SettingsDialogService } from "../settings/settings-dialog";
import { MatDialogModule } from '@angular/material/dialog';
import { AuthService } from '../auth/auth.service';
import { ChatStateService } from '../services/chat-state.service';
import { FamilyModeService } from '../services/family-mode.service';
import { UIStateService } from '../services/ui-state.service';
import { Observable, Subject, combineLatest } from 'rxjs';
import { filter, map, shareReplay, startWith, takeUntil } from 'rxjs/operators';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

/** Taps on the logo, within this time, that turn family mode off and on (onLogoTap()). */
const LOGO_TAPS = 5;
const LOGO_TAP_WINDOW_MS = 3000;

@Component({
  selector: 'app-sidebar',
  standalone: true,
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.scss'],
  imports: [
    CommonModule,
    ConversationComponent,
    MatIcon,
    MatDialogModule,
    TranslateModule
  ]
})
export class SidebarComponent implements OnInit, OnDestroy {

  groupedConversations: { [key: string]: Conversation[] } = {};

  // Without the hidden ones while this device is in family mode
  conversations$: Observable<Conversation[]> = this.chatState.visibleConversations$;
  activeConversationId$: Observable<string | null> = this.uiState.activeConversationId$;
  isSidebarOpen$: Observable<boolean> = this.uiState.sidebarOpen$;
  isAdmin$: Observable<boolean> = this.authService.isAdmin$;  // The Agents page is for admins
  // The knowledge base is for signed-in users (AuthService sets isGuest before it publishes the user)
  isMember$: Observable<boolean> = this.authService.currentUser$.pipe(map(user => !!user && !this.authService.isGuest));

  /** The current page's path, without query and fragment (the nav marks its page with it). */
  currentPath$: Observable<string> = this.router.events.pipe(
    filter((event): event is NavigationEnd => event instanceof NavigationEnd),
    map(event => event.urlAfterRedirects),
    startWith(this.router.url),
    map(url => url.split(/[?#]/)[0] || '/'),
    shareReplay({ bufferSize: 1, refCount: true })
  );

  /**
   * The conversation shown as selected ('0' marks New Chat): only while the chat is open, so on the
   * other pages nothing in the list looks selected.
   */
  selectedConversationId$: Observable<string | null> = combineLatest([this.activeConversationId$, this.currentPath$]).pipe(
    map(([id, path]) => path === '/' ? id : null)
  );

  private destroy$ = new Subject<void>();

  constructor(
    private chatState: ChatStateService,
    private uiState: UIStateService,
    public router: Router,
    private settingsDialog: SettingsDialogService,
    private authService: AuthService,
    private translate: TranslateService,
    private familyMode: FamilyModeService
  ) { }

  /** Family mode is off on this device: the logo wears sunglasses. */
  showingHidden$: Observable<boolean> = combineLatest([this.familyMode.available$, this.familyMode.active$]).pipe(
    map(([available, active]) => available && !active)
  );

  /** Taps on the logo within the last LOGO_TAP_WINDOW_MS. */
  private logoTaps: number[] = [];
  /** The logo pulses once when the switch flips. */
  logoPulse = false;

  /** Five quick taps on the logo turn family mode off and on, where the server puts its switch there. */
  onLogoTap(): void {
    if (!this.familyMode.available || this.familyMode.switchKind !== 'logo') return;
    const now = Date.now();
    this.logoTaps = [...this.logoTaps.filter(time => now - time < LOGO_TAP_WINDOW_MS), now];
    if (this.logoTaps.length < LOGO_TAPS) return;
    this.logoTaps = [];
    this.familyMode.toggle();
    // A short vibration on phones that have it
    try {
      navigator.vibrate?.(30);
    } catch {
      // Not allowed here: the pulse is enough
    }
    this.logoPulse = true;
    setTimeout(() => this.logoPulse = false, 400);
  }

  /** Whether the nav item of the route is the current page ('/' only exactly, the others with their subpages). */
  isNavActive(path: string | null, route: string): boolean {
    if (path === null) return false;
    return route === '/' ? path === '/' : path === route || path.startsWith(route + '/');
  }

  isGuest(): boolean {
    return this.authService.isGuest;
  }

  getUserName(): string {
    const user = this.authService.getCurrentUser();
    if (user) {
      return user.name || user.email;
    }
    return 'Guest';
  }

  getUserInitials(): string {
    const user = this.authService.getCurrentUser();
    if (user) {
      if (user.name) {
        const names = user.name.split(' ');
        if (names.length >= 2) {
          return names[0][0].toUpperCase() + names[names.length - 1][0].toUpperCase();
        }
        return user.name.substring(0, 2).toUpperCase();
      } else if (user.email) {
        return user.email.substring(0, 2).toUpperCase();
      }
    }
    return 'G';
  }

  handleUserClick(): void {
    if (this.authService.isGuest) {
      this.router.navigate(['/login']);
      this.uiState.closeSidebarOnMobile();
    } else {
      if (confirm(this.translate.instant('sidebar.logoutConfirm'))) {
        this.authService.logout();
      }
    }
  }

  openSettings(): void {
    this.settingsDialog.open();
  }


  ngOnInit(): void {
    this.conversations$
      .pipe(takeUntil(this.destroy$))
      .subscribe(conversations => {
        this.groupedConversations = this.groupConversationsByDate(conversations);
      });
  }

  groupConversationsByDate(conversations: Conversation[]): { [key: string]: Conversation[] } {
    const groups: { [key: string]: Conversation[] } = {
      'Today': [],
      'Last 7 Days': [],
      'This Month': [],
      'Older': [],
    };

    const now = new Date();
    now.setHours(0, 0, 0, 0);

    for (const conv of conversations) {
      const updated = new Date(conv.lastActivity);
      updated.setHours(0, 0, 0, 0);

      const diffTime = now.getTime() - updated.getTime();
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

      if (updated.getTime() === now.getTime()) {
        groups['Today'].push(conv);
      } else if (diffDays > 0 && diffDays < 7) {
        groups['Last 7 Days'].push(conv);
      } else if (
        updated.getMonth() === now.getMonth() &&
        updated.getFullYear() === now.getFullYear() &&
        updated.getTime() < now.getTime()
      ) {
        groups['This Month'].push(conv);
      } else {
        groups['Older'].push(conv);
      }
    }

    for (const key in groups) {
      groups[key].sort(Conversation.compareByActivity);
    }

    return groups;
  }

  onSelectConversation(conversation: Conversation): void {
    this.chatState.loadConversation(conversation.id);
    this.router.navigate(['/']);
    this.uiState.closeSidebarOnMobile();
  }

  createNewConversation(): void {
    this.chatState.createNewConversation();
    this.router.navigate(['/']);  // Also from other pages, e.g. Agents
    this.uiState.closeSidebarOnMobile();
  }

  closeSidebar(): void {
    this.uiState.closeSidebar();
  }

  navigateTo(route: string): void {
    this.router.navigate([route]);
    this.uiState.closeSidebarOnMobile();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}
