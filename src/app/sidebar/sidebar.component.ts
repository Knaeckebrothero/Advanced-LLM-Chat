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
import {TranslateModule, TranslatePipe, TranslateService} from '@ngx-translate/core';


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
    TranslateModule
  ]
})
export class SidebarComponent implements OnInit, OnDestroy {

  groupedConversations: { [key: string]: Conversation[] } = {};

  conversations$: Observable<Conversation[]> = this.chatState.conversations$;
  activeConversationId$: Observable<string | null> = this.uiState.activeConversationId$;
  isSidebarOpen$: Observable<boolean> = this.uiState.sidebarOpen$;

  private destroy$ = new Subject<void>();

  constructor(
    private chatState: ChatStateService,
    private uiState: UIStateService,
    public router: Router,
    private dialog: MatDialog,
    private authService: AuthService,
    private translate: TranslateService
  ) {}

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
      if (confirm('Are you sure you want to logout?')) {
        this.authService.logout();
      }
    }
  }

  openSettings(): void {
    const dialogRef = this.dialog.open(SettingsComponent, {
      panelClass: 'settings-dialog-panel', // Apply custom class for responsive styling
      backdropClass: 'custom-backdrop' // Optional: for custom backdrop styles
    });

    dialogRef.afterClosed().subscribe(() => {
      // Logic after dialog closes
    });
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
      const updated = new Date(conv.updatedAt);
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
      groups[key].sort(
        (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
      );
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
    this.uiState.closeSidebarOnMobile();
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
