import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule, NgOptimizedImage } from '@angular/common';
import { Router } from '@angular/router';
import { Conversation } from '../data/objects/conversation';
import { ConversationComponent } from './conversation/conversation.component';
import { MatIcon } from "@angular/material/icon";
import { SettingsComponent } from "../settings/settings.component";
import { MatDialog } from "@angular/material/dialog";
import { MatDialogModule } from '@angular/material/dialog';
import { AuthService } from '../auth/auth.service';
import { ChatStateService } from '../services/chat-state.service';
import { UIStateService } from '../services/ui-state.service';
import { Observable, Subject } from 'rxjs';
import { takeUntil } from 'rxjs/operators';


@Component({
  selector: 'app-sidebar',
  standalone: true,
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.scss'],
  imports: [
    CommonModule,
    NgOptimizedImage,
    ConversationComponent,
    MatIcon,
    MatDialogModule,
  ]
})
export class SidebarComponent implements OnInit, OnDestroy {

  groupedConversations: { [key: string]: Conversation[] } = {};
  
  // Observable streams from state services
  conversations$: Observable<Conversation[]> = this.chatState.conversations$;
  activeConversationId$: Observable<number | null> = this.uiState.activeConversationId$;
  isSidebarOpen$: Observable<boolean> = this.uiState.sidebarOpen$;
  
  private destroy$ = new Subject<void>();

  constructor(
    private chatState: ChatStateService,
    private uiState: UIStateService,
    public router: Router,
    private dialog: MatDialog,
    private authService: AuthService
  ) {}

  /**
   * Gets the current user's name to display
   */
  getUserName(): string {
    const user = this.authService.getCurrentUser();
    if (user) {
      return user.name || user.email;
    }
    return 'Guest';
  }

  /**
   * Gets the initials for the avatar
   */
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
    return 'G'; // Default for Guest
  }

  /**
   * Handles click on user profile - navigates to login if guest, shows logout option if logged in
   */
  handleUserClick(): void {
    if (this.authService.isGuest) {
      // Navigate to login page
      this.router.navigate(['/login']);
      this.uiState.closeSidebarOnMobile();
    } else {
      // Show logout confirmation
      if (confirm('Are you sure you want to logout?')) {
        this.authService.logout();
      }
    }
  }

  /**
   * Öffnet die Einstellungen als modales Dialogfenster.
   * Nutzt die neue SettingsNewComponent und zeigt sie über MatDialog an.
   */
  openSettings(): void {
    const dialogRef = this.dialog.open(SettingsComponent, {
      width: '400px'
    });

    // The new settings component handles saving internally
    dialogRef.afterClosed().subscribe(() => {
      // Settings are already saved by the component itself
    });
  }

  /**
   * Angular lifecycle hook that initializes the component's state.
   * It subscribes to a list of conversations from the chat state service.
   * It groups existing conversations by date and stores them accordingly.
   */
  ngOnInit(): void {
    // Subscribe to conversations from ChatStateService
    this.conversations$
      .pipe(takeUntil(this.destroy$))
      .subscribe(conversations => {
        this.groupedConversations = this.groupConversationsByDate(conversations);
      });
  }

  /**
   * Groups conversations into time-based categories for display.
   * Each group is also sorted by newest first.
   */
  groupConversationsByDate(conversations: Conversation[]): { [key: string]: Conversation[] } {
    const groups: { [key: string]: Conversation[] } = {
      'Heute': [],
      'Letzte 7 Tage': [],
      'Diesen Monat': [],
      'Älter': [],
    };

    const now = new Date();
    now.setHours(0, 0, 0, 0); // Reset time for accurate date comparison

    for (const conv of conversations) {
      const updated = new Date(conv.updatedAt);
      updated.setHours(0, 0, 0, 0);

      const diffTime = now.getTime() - updated.getTime();
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

      if (updated.getTime() === now.getTime()) {
        groups['Heute'].push(conv);
      } else if (diffDays > 0 && diffDays < 7) {
        groups['Letzte 7 Tage'].push(conv);
      } else if (
        updated.getMonth() === now.getMonth() &&
        updated.getFullYear() === now.getFullYear() &&
        updated.getTime() < now.getTime()
      ) {
        groups['Diesen Monat'].push(conv);
      } else {
        groups['Älter'].push(conv);
      }
    }

    // Sort each group by newest first
    for (const key in groups) {
      groups[key].sort(
        (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
      );
    }

    return groups;
  }

  /**
   * Called when a conversation is selected (clicked).
   * Passes the selected conversation to the ChatStateService and updates highlighting.
   */
  onSelectConversation(conversation: Conversation): void {
    this.chatState.loadConversation(conversation.id);
    this.router.navigate(['/']); // Navigate to the main chat view
    this.uiState.closeSidebarOnMobile(); // Close sidebar on mobile if open
  }

  /**
   * Creates a new placeholder conversation.
   */
  createNewConversation(): void {
    this.chatState.createNewConversation();
    this.uiState.closeSidebarOnMobile();
  }

  /**
   * Navigates to a specific route and closes sidebar on mobile
   */
  navigateTo(route: string): void {
    this.router.navigate([route]);
    this.uiState.closeSidebarOnMobile();
  }
  
  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }
}
