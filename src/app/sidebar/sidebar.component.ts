import { Component, OnInit } from '@angular/core'; // Removed Output, EventEmitter
import { CommonModule, NgOptimizedImage } from '@angular/common';
import { Router } from '@angular/router';
import { Conversation } from '../data/objects/conversation';
import { ChatService } from '../chat/chat.service';
import { ConversationComponent } from './conversation/conversation.component';
import {DisplayService} from "./service/display.service";


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
  // Removed @Output() closeRequest

  groupedConversations: { [key: string]: Conversation[] } = {};

  constructor(
    private chatService: ChatService,
    public router: Router,
    private displayService: DisplayService // Injected DisplayService
  ) {}

  ngOnInit(): void {
    const allConversations = this.chatService.getDummyConversations();
    this.groupedConversations = this.groupConversationsByDate(allConversations);
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
    this.displayService.closeSidebarOnMobile(); // Use DisplayService
  }

  navigateTo(route: string): void {
    this.router.navigate([route]);
    this.displayService.closeSidebarOnMobile(); // Use DisplayService
  }
}
