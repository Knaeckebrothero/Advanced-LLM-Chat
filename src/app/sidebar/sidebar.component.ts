import { Component, OnInit } from '@angular/core';
import { CommonModule, NgOptimizedImage } from '@angular/common';
import { Router } from '@angular/router';
import { Conversation } from '../data/objects/conversation';
import { ChatService } from '../services/chat.service';
import { ConversationComponent } from './conversation/conversation.component';
import { DisplayService } from "./service/display.service";
import { MatIcon } from "@angular/material/icon";
import { SettingsComponent } from "../settings/settings.component";
import { SettingsService } from "../settings/settings.service";
import { MatDialog } from "@angular/material/dialog";
import { MatDialogModule } from '@angular/material/dialog';
import { Settings } from '../settings/settings.service';
import { AuthService } from '../auth/auth.service';


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
export class SidebarComponent implements OnInit {

  groupedConversations: { [key: string]: Conversation[] } = {};

  constructor(
    public chatService: ChatService,
    public router: Router,
    public displayService: DisplayService,
    private dialog: MatDialog,
    private settingsService: SettingsService,
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
      this.displayService.closeSidebarOnMobile();
    } else {
      // Show logout confirmation
      if (confirm('Are you sure you want to logout?')) {
        this.authService.logout();
      }
    }
  }

  /**
   * Öffnet die Einstellungen als modales Dialogfenster.
   * Nutzt die bestehende SettingsComponent und zeigt sie über MatDialog an.
   */
  openSettings(): void {
    const dialogRef = this.dialog.open(SettingsComponent, {
      width: '400px'
    });

    dialogRef.afterClosed().subscribe((result: Settings | undefined) => {
      if (result) {
        this.settingsService.saveSettings(result).subscribe();
        this.settingsService.saveLocal(result);
      }
    });
  }

  /**
   * Angular lifecycle hook that initializes the component's state.
   * It subscribes to a list of conversations from the chat service.
   * It groups existing conversations by date and stores them accordingly.
   */
  ngOnInit(): void {
    // Subscribe to conversations
    this.chatService.getConversations().subscribe(conversations => {
      this.groupedConversations = this.groupConversationsByDate(conversations);
    });

    // Initial load of all conversations
    this.chatService.loadAllConversations();
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
   * Passes the selected conversation to the ChatService and updates highlighting.
   */
  onSelectConversation(conversation: Conversation): void {
    this.chatService.loadConversation(conversation);
    this.displayService.setActiveConversation(conversation.id);
    this.router.navigate(['/']); // Navigate to the main chat view
    this.displayService.closeSidebarOnMobile(); // Close sidebar on mobile if open
  }

  /**
   * Creates a new placeholder conversation.
   */
  createNewConversation(): void {
    const tempConversation = new Conversation(
      0, // Temporary ID for a new, unsaved chat
      1, // Placeholder user ID
      'New Chat', // Default name
      ['user', 'Assistant'] // Default participants
    );

    this.chatService.loadConversation(tempConversation);
    this.displayService.setActiveConversation(0); // Highlight "New Chat" button
    this.displayService.closeSidebarOnMobile();
  }

  /**
   * Navigates to a specific route and closes sidebar on mobile
   */
  navigateTo(route: string): void {
    this.router.navigate([route]);
    this.displayService.closeSidebarOnMobile();
  }
}
