import {Component, OnDestroy, OnInit} from '@angular/core';
import { CommonModule, NgOptimizedImage } from '@angular/common';
import { Router } from '@angular/router';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { Subscription } from 'rxjs';
import { MatTooltipModule } from '@angular/material/tooltip';

import { Conversation } from '../data/objects/conversation';
import { ChatService } from '../chat/chat.service';
import { DisplayService } from "./service/display.service";
import { SettingsComponent } from "../settings/settings.component";
import { AuthService } from '../auth/auth.service';
import { ThemeService } from 'src/styles/themes/theme.service';
import { ConversationComponent } from './conversation/conversation.component';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.scss'],
  imports: [
    CommonModule,
    ConversationComponent,
    MatIconModule,
    MatDialogModule,
    MatTooltipModule,
  ]
})
export class SidebarComponent implements OnInit, OnDestroy {

  groupedConversations: { [key: string]: Conversation[] } = {};
  isGuest = false;
  isDarkMode: boolean = false;
  private themeSubscription!: Subscription;

  constructor(
    public chatService: ChatService,
    public router: Router,
    public displayService: DisplayService,
    private dialog: MatDialog,
    private themeService: ThemeService,
    private authService: AuthService
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
      this.displayService.closeSidebarOnMobile();
    } else {
      if (confirm('Are you sure you want to logout?')) {
        this.authService.logout();
      }
    }
  }

  ngOnInit(): void {
    this.isGuest = this.authService.isGuest;
    this.themeSubscription = this.themeService.getEffectiveTheme$().subscribe(theme => {
      this.isDarkMode = theme === 'dark';
    });

    this.chatService.getConversations().subscribe(conversations => {
      this.groupedConversations = this.groupConversationsByDate(conversations);
    });

    this.chatService.loadAllConversations();
  }

  ngOnDestroy(): void {
    if (this.themeSubscription) {
      this.themeSubscription.unsubscribe();
    }
  }

  openSettings(): void {
    this.dialog.open(SettingsComponent, {
      width: '540px',
      autoFocus: false,
      panelClass: 'settings-dialog-panel'
    });
  }

  groupConversationsByDate(conversations: Conversation[]): { [key: string]: Conversation[] } {
    const groups: { [key: string]: Conversation[] } = {
      'Heute': [],
      'Letzte 7 Tage': [],
      'Diesen Monat': [],
      'Älter': [],
    };

    const now = new Date();
    now.setHours(0, 0, 0, 0);

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

    for (const key in groups) {
      groups[key].sort(
        (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
      );
    }

    return groups;
  }

  onSelectConversation(conversation: Conversation): void {
    this.chatService.loadConversation(conversation);
    this.displayService.setActiveConversation(conversation.id);
    this.router.navigate(['/']);
    this.displayService.closeSidebarOnMobile();
  }

  createNewConversation(): void {
    const tempConversation = new Conversation(
      0,
      1,
      'New Chat',
      ['user', 'Assistant']
    );

    this.chatService.loadConversation(tempConversation);
    this.displayService.setActiveConversation(0);
    this.displayService.closeSidebarOnMobile();
  }

  navigateTo(route: string): void {
    this.router.navigate([route]);
    this.displayService.closeSidebarOnMobile();
  }
}
