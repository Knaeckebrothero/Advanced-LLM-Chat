import { Component, OnInit } from '@angular/core';
import { CommonModule, NgOptimizedImage } from '@angular/common';

import { Conversation } from '../data/objects/conversation';
import { ChatService } from '../chat/chat.service';
import { ConversationComponent } from './conversation/conversation.component';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.scss'],
  imports: [
    CommonModule,
    NgOptimizedImage,
    ConversationComponent
  ]
})
export class SidebarComponent implements OnInit {

  groupedConversations: { [key: string]: Conversation[] } = {};

  constructor(private chatService: ChatService) {}

  /**
   * Lifecycle hook: called once after component initialization.
   * Loads and groups all conversations by relative date (Today, Last 7 Days, etc.).
   */
  ngOnInit(): void {
    const allConversations = this.chatService.getDummyConversations();
    this.groupedConversations = this.groupConversationsByDate(allConversations);
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

    for (const conv of conversations) {
      const updated = new Date(conv.updatedAt);
      const diffMs = now.getTime() - updated.getTime();
      const diffDays = diffMs / (1000 * 60 * 60 * 24);

      if (diffDays < 1) {
        groups['Heute'].push(conv);
      } else if (diffDays < 7) {
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
    this.chatService.loadConversation(conversation);
  }
}
