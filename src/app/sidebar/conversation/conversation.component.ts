import { Component, EventEmitter, Input, OnInit, Output, ViewChild, OnDestroy, ElementRef } from '@angular/core';
import { Conversation } from '../../data/objects/conversation';
import { Message } from '../../data/objects/message';
import { CommonModule } from '@angular/common';
import { ChatStateService } from "../../services/chat-state.service";
import { FormsModule } from "@angular/forms";
import { firstValueFrom } from 'rxjs';
import { MatMenuModule, MatMenuTrigger } from '@angular/material/menu';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';


@Component({
  selector: 'app-conversation',
  standalone: true,
  imports: [CommonModule, FormsModule, MatMenuModule, MatIconModule, MatButtonModule],
  templateUrl: './conversation.component.html',
  styleUrls: ['./conversation.component.scss']
})
export class ConversationComponent implements OnInit, OnDestroy {
  @Input() conversation!: Conversation;
  @Input() highlighted: boolean = false; // Added Input
  @Output() selected = new EventEmitter<Conversation>();
  @Output() delete = new EventEmitter<string>();
  @ViewChild(MatMenuTrigger) menuTrigger!: MatMenuTrigger;
  @ViewChild('editInput') editInput?: ElementRef<HTMLInputElement>;

  messages: Message[] = [];
  editing = false;
  newName = '';
  private longPressTimer: any;
  private longPressTriggered = false;

  constructor(private chatState: ChatStateService) {}

  onSelect(): void {
    // Don't select if long press was triggered
    if (!this.longPressTriggered) {
      this.selected.emit(this.conversation);
    }
    this.longPressTriggered = false;
  }

  onDelete(event: MouseEvent): void {
    event.stopPropagation();
    this.delete.emit(this.conversation.id);
  }

  // Lifecycle hook: called once after the component is initialized.
  // Loads messages related to this conversation for preview purposes.
  async ngOnInit() {
    // Messages are now managed by repositories and state services
    // No need to load directly from DB
  }

  // Emits the selected conversation to the parent component when the user clicks on this conversation.
  onClick(): void {
    this.selected.emit(this.conversation);
  }


  startEditing(): void {
    this.editing = true;
    this.newName = this.conversation.name;
    
    // Auto-focus the input field after DOM updates
    setTimeout(() => {
      if (this.editInput) {
        this.editInput.nativeElement.focus();
        this.editInput.nativeElement.select(); // Select all text for easy replacement
      }
    }, 50);
  }

  onMenuClick(event: MouseEvent): void {
    event.stopPropagation();
  }

  onRename(): void {
    this.startEditing();
  }

  onLongPress(): void {
    // Open the dropdown menu programmatically on long press (mobile)
    if (this.menuTrigger) {
      this.longPressTriggered = true;
      this.menuTrigger.openMenu();
    }
  }

  onPressStart(event: MouseEvent | TouchEvent): void {
    // Only handle long press on mobile (screen width < 768px)
    if (window.innerWidth < 768) {
      this.longPressTimer = setTimeout(() => {
        this.onLongPress();
      }, 500); // 500ms for long press
    }
  }

  onPressEnd(): void {
    if (this.longPressTimer) {
      clearTimeout(this.longPressTimer);
      this.longPressTimer = null;
    }
  }

  async finishEditing(): Promise<void> {
    if (this.newName && this.newName !== this.conversation.name) {
      this.conversation.name = this.newName;
      await this.chatState.updateConversation(this.conversation);
    }
    this.editing = false;
  }

  cancelEditing(): void {
    this.editing = false;
    this.newName = '';
  }

  /**
   * Deletes the current conversation after user confirmation.
   * Prompts the user with a confirmation dialog before proceeding with the deletion.
   * If the user confirms, the conversation is deleted using the chat state service.
   *
   * @return {Promise<void>} A promise that resolves when the conversation is successfully deleted or is rejected if an error occurs.
   */
  async deleteConversation(): Promise<void> {
    if (confirm('Delete this conversation?')) {
      await this.chatState.deleteConversation(this.conversation.id);
    }
  }

  ngOnDestroy(): void {
    // Clean up any pending timers
    if (this.longPressTimer) {
      clearTimeout(this.longPressTimer);
    }
  }
}
