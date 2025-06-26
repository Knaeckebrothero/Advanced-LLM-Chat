import { Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { Conversation } from '../../data/objects/conversation';
import { Message } from '../../data/objects/message';
import { DBService } from '../../data/db.service';
import { CommonModule } from '@angular/common';
import { ChatService } from "../../chat/chat.service";
import { FormsModule } from "@angular/forms";

@Component({
  selector: 'app-conversation',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './conversation.component.html',
  styleUrls: ['./conversation.component.scss']
})
export class ConversationComponent implements OnInit {
  // --- PROPERTIES ---
  // Using isSelected from the current branch to match the merged CSS.
  @Input() isSelected = false;
  @Input() conversation!: Conversation;
  @Output() selected = new EventEmitter<Conversation>();

  messages: Message[] = [];
  editing = false;
  newName = '';

  constructor(private chatService: ChatService, private db: DBService) {}

  // --- LIFECYCLE HOOKS ---
  async ngOnInit() {
    if (this.conversation?.id) {
      this.messages = await this.db.getMessagesByConversationId(this.conversation.id);
      this.messages.sort((a, b) => a.time!.getTime() - b.time!.getTime());
    }
  }

  // --- EVENT HANDLERS ---

  /**
   * Emits the conversation to the parent component.
   * This is the primary click action, taken from the 'develop' branch logic.
   */
  onSelect(): void {
    this.selected.emit(this.conversation);
  }

  /**
   * Handles the right-click event.
   * This version from 'develop' prevents the default menu AND starts the editing mode.
   * @param {Event} event - The right-click event object.
   */
  onRightClick(event: Event): void {
    event.preventDefault();
    this.startEditing();
  }

  // --- EDITING AND DELETION METHODS ---

  /**
   * Initiates the editing mode for the conversation name.
   */
  startEditing(): void {
    this.editing = true;
    this.newName = this.conversation.name;
  }

  /**
   * Finalizes the editing process and updates the conversation name.
   */
  async finishEditing(): Promise<void> {
    if (this.newName && this.newName.trim() !== '' && this.newName !== this.conversation.name) {
      this.conversation.name = this.newName;
      await this.chatService.updateConversation(this.conversation);
    }
    this.editing = false;
  }

  /**
   * Cancels the editing process.
   */
  cancelEditing(): void {
    this.editing = false;
    this.newName = '';
  }

  /**
   * Deletes the current conversation after user confirmation.
   * The self-contained logic from the current branch is preserved.
   */
  async deleteConversation(): Promise<void> {
    // Note: confirm() can be disruptive. For a better user experience,
    // consider replacing this with a custom modal dialog in the future.
    if (confirm('Are you sure you want to delete this conversation?')) {
      await this.chatService.deleteConversation(this.conversation.id);
    }
  }
}
