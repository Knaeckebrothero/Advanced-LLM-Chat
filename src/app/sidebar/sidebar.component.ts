import { Component, OnInit } from '@angular/core';
import { CommonModule, NgOptimizedImage } from '@angular/common';
import { Router } from '@angular/router';
import { Conversation } from '../data/objects/conversation';
import { ChatService } from '../chat/chat.service';
import { ConversationComponent } from './conversation/conversation.component';
import { DisplayService } from "./service/display.service";
import { MatIcon } from "@angular/material/icon";


@Component({
  selector: 'app-sidebar',
  standalone: true,
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.scss'],
  imports: [
    CommonModule,
    ConversationComponent,
    MatIcon
  ]
})
export class SidebarComponent implements OnInit {

  groupedConversations: Record<string, Conversation[]> = {};
  selectedConversation: Conversation | null = null;

  constructor(
    private chatService: ChatService,
    public router: Router,
    private displayService: DisplayService
  ) {}

  /**
   * Angular lifecycle hook that initializes the component's state.
   * It subscribes to a list of conversations from the chat service.
   * If no conversations are present, it creates a new one.
   * Otherwise, it groups existing conversations by date and stores them accordingly.
   */
  ngOnInit(): void {  // Fixed: Removed async and Promise<void>
    // Subscribe to conversations
    this.chatService.getConversations().subscribe(conversations => {
      if (conversations.length === 0) {
        // Auto-create first conversation
        this.createNewConversation();
      } else {
        this.groupedConversations = this.groupConversationsByDate(conversations);
      }
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
   * Passes the selected conversation to the ChatService.
   */
  onSelectConversation(conversation: Conversation): void {
    this.selectedConversation = conversation;
    this.chatService.loadConversation(conversation);
    this.router.navigate(['/']);
    this.displayService.closeSidebarOnMobile();
  }

  /**
   * Creates a new conversation with default values.
   */
  async createNewConversation(): Promise<void> {
    const newConversation = new Conversation(
      Date.now(), // Temporary ID
      1, // Current user ID
      'New Chat', // Default name
      ['user', 'Assistant'] // Default participants
    );

    await this.chatService.createConversation(newConversation);
    // Fixed: Changed to use the correct service method
    await this.chatService.loadAllConversations(); // Refresh the list
    this.onSelectConversation(newConversation);
  }

  /**
   * Navigates to a specific route and closes sidebar on mobile
   */
  navigateTo(route: string): void {
    this.router.navigate([route]);
    this.displayService.closeSidebarOnMobile();
  }
}
