import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule, NgOptimizedImage } from '@angular/common';
import { Router } from '@angular/router';
import { Conversation } from '../data/objects/conversation';
import { ChatService } from '../chat/chat.service';
import { ConversationComponent } from './conversation/conversation.component';
import { DisplayService } from "./service/display.service";
import { MatIcon } from "@angular/material/icon";
import { ThemeService } from 'src/styles/themes/theme.service';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.scss'],
  imports: [
    CommonModule,
    // From 'develop'
    ConversationComponent,
    MatIcon
  ]
})
export class SidebarComponent implements OnInit, OnDestroy {
  // --- PROPERTIES ---
  groupedConversations: { [key: string]: Conversation[] } = {};
  isDarkMode: boolean = false; // From 'current' for theme-aware logo
  private themeSubscription!: Subscription; // From 'current'

  constructor(
    // Services from both branches are injected
    public chatService: ChatService,
    public router: Router,
    public displayService: DisplayService,
    private themeService: ThemeService // From 'current'
  ) {}

  // --- LIFECYCLE HOOKS ---
  ngOnInit(): void {
    // Theme subscription from 'current' branch
    this.themeSubscription = this.themeService.getEffectiveTheme$().subscribe(theme => {
      this.isDarkMode = theme === 'dark';
    });

    // Conversation subscription from 'develop' branch
    this.chatService.getConversations().subscribe(conversations => {
      this.groupedConversations = this.groupConversationsByDate(conversations);
    });

    // Initial load from 'develop' branch
    this.chatService.loadAllConversations();
  }

  ngOnDestroy(): void {
    // Cleanup from 'current' branch
    if (this.themeSubscription) {
      this.themeSubscription.unsubscribe();
    }
  }

  // --- DATA HANDLING ---
  /**
   * Groups conversations by date. Logic is identical in both branches.
   */
  groupConversationsByDate(conversations: Conversation[]): { [key: string]: Conversation[] } {
    const groups: { [key: string]: Conversation[] } = {
      'Heute': [], 'Letzte 7 Tage': [], 'Diesen Monat': [], 'Älter': [],
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
      } else if (updated.getMonth() === now.getMonth() && updated.getFullYear() === now.getFullYear()) {
        groups['Diesen Monat'].push(conv);
      } else {
        groups['Älter'].push(conv);
      }
    }

    for (const key in groups) {
      groups[key].sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
    }
    return groups;
  }

  // --- EVENT HANDLERS & NAVIGATION ---
  /**
   * Handles selecting an existing conversation.
   * This complete logic is from the 'develop' branch.
   */
  onSelectConversation(conversation: Conversation): void {
    this.chatService.loadConversation(conversation);
    this.displayService.setActiveConversation(conversation.id);
    this.router.navigate(['/']);
    this.displayService.closeSidebarOnMobile();
  }

  /**
   * Creates a new temporary conversation state.
   * This functionality is taken directly from the 'develop' branch.
   */
  createNewConversation(): void {
    const tempConversation = new Conversation(
      0, // Using 0 as a temporary ID for an unsaved chat
      1,
      'New Chat',
      ['user', 'Assistant']
    );

    this.chatService.loadConversation(tempConversation);
    this.displayService.setActiveConversation(0); // Highlight "New Chat" button by setting active ID to 0
    this.displayService.closeSidebarOnMobile();
  }

  /**
   * Navigates to a specific route. Logic is identical in both branches.
   */
  navigateTo(route: string): void {
    this.router.navigate([route]);
    this.displayService.closeSidebarOnMobile();
  }
}
