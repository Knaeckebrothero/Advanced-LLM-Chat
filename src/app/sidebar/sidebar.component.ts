import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon'; // Note: Also added MatIconModule here for completeness
import { Subscription } from 'rxjs';
import { MatTooltipModule } from '@angular/material/tooltip'; // Added for the info icons in the new settings HTML

import { Conversation } from '../data/objects/conversation';
import { ChatService } from '../chat/chat.service';
import { DisplayService } from "./service/display.service";
import { ThemeService } from 'src/styles/themes/theme.service';

import { ConversationComponent } from './conversation/conversation.component';
// FIXED: Added the missing import for SettingsComponent
import { SettingsComponent } from '../settings/settings.component';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.scss'],
  imports: [
    CommonModule,
    ConversationComponent,
    MatIconModule, // Use the module here
    MatDialogModule,
    MatTooltipModule, // Added for the info icons
  ]
})
export class SidebarComponent implements OnInit, OnDestroy {

  groupedConversations: { [key: string]: Conversation[] } = {};
  isDarkMode: boolean = false;
  private themeSubscription!: Subscription;

  constructor(
    public chatService: ChatService,
    public router: Router,
    public displayService: DisplayService,
    private dialog: MatDialog,
    private themeService: ThemeService
  ) {}

  ngOnInit(): void {
    // Subscribe to theme changes to toggle logo
    this.themeSubscription = this.themeService.getEffectiveTheme$().subscribe(theme => {
      this.isDarkMode = theme === 'dark';
    });

    // Subscribe to conversations for display
    this.chatService.getConversations().subscribe(conversations => {
      this.groupedConversations = this.groupConversationsByDate(conversations);
    });

    // Initial load of all conversations
    this.chatService.loadAllConversations();
  }

  ngOnDestroy(): void {
    // Clean up the theme subscription
    if (this.themeSubscription) {
      this.themeSubscription.unsubscribe();
    }
  }

  /**
   * Opens the settings component in a modal dialog.
   */
  openSettings(): void {
    this.dialog.open(SettingsComponent, {
      // ...and update the width property here
      width: '540px', // Increased from 500px
      autoFocus: false,
      panelClass: 'settings-dialog-panel'
    });
  }


  /**
   * Groups conversations into time-based categories for display.
   */
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
        updated.getFullYear() === now.getFullYear()
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

  /**
   * Loads a selected conversation into the main view.
   */
  onSelectConversation(conversation: Conversation): void {
    this.chatService.loadConversation(conversation);
    this.displayService.setActiveConversation(conversation.id);
    this.router.navigate(['/']);
    this.displayService.closeSidebarOnMobile();
  }

  /**
   * Creates a new temporary conversation state.
   */
  createNewConversation(): void {
    const tempConversation = new Conversation(
      0, // Temporary ID for a new, unsaved chat
      1, // Placeholder user ID
      'New Chat',
      ['user', 'Assistant']
    );

    this.chatService.loadConversation(tempConversation);
    this.displayService.setActiveConversation(0);
    this.displayService.closeSidebarOnMobile();
  }

  /**
   * Navigates to a specific route.
   */
  navigateTo(route: string): void {
    this.router.navigate([route]);
    this.displayService.closeSidebarOnMobile();
  }
}
