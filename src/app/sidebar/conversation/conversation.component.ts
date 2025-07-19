import { Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { Conversation } from '../../data/objects/conversation';
import { Message } from '../../data/objects/message';
import { DBService } from '../../data/db.service';
import { CommonModule } from '@angular/common';
import {ChatService} from "../../chat.service";
import {FormsModule} from "@angular/forms";


@Component({
  selector: 'app-conversation',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './conversation.component.html',
  styleUrls: ['./conversation.component.scss']
})
export class ConversationComponent implements OnInit {
  @Input() conversation!: Conversation;
  @Input() highlighted: boolean = false; // Added Input
  @Output() selected = new EventEmitter<Conversation>();
  @Output() delete = new EventEmitter<number>();

  messages: Message[] = [];
  editing = false;
  newName = '';

  constructor(private chatService: ChatService, private db: DBService) {}

  onSelect(): void {
    this.selected.emit(this.conversation);
  }

  onDelete(event: MouseEvent): void {
    event.stopPropagation();
    this.delete.emit(this.conversation.id);
  }

  // Lifecycle hook: called once after the component is initialized.
  // Loads messages related to this conversation from the local database.
  // (This could be used later for message previews or synchronization.)
  async ngOnInit() {
    if (this.conversation?.id) {
      this.messages = await this.db.getMessagesByConversationId(this.conversation.id);
      this.messages.sort((a, b) => a.time!.getTime() - b.time!.getTime());
    }
  }

  // Emits the selected conversation to the parent component when the user clicks on this conversation.
  onClick(): void {
    this.selected.emit(this.conversation);
  }

  /**
   * Handles the right-click event by preventing the default context menu
   * and initiating the editing process.
   *
   * @param {Event} event - The event object associated with the right-click action.
   * @return {void} This method does not return a value.
   */
  onRightClick(event: Event): void {
    event.preventDefault();
    this.startEditing();
  }

  startEditing(): void {
    this.editing = true;
    this.newName = this.conversation.name;
  }

  async finishEditing(): Promise<void> {
    if (this.newName && this.newName !== this.conversation.name) {
      this.conversation.name = this.newName;
      await this.chatService.updateConversation(this.conversation);
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
   * If the user confirms, the conversation is deleted using the chat service.
   *
   * @return {Promise<void>} A promise that resolves when the conversation is successfully deleted or is rejected if an error occurs.
   */
  async deleteConversation(): Promise<void> {
    if (confirm('Delete this conversation?')) {
      await this.chatService.deleteConversation(this.conversation.id);
    }
  }
}
