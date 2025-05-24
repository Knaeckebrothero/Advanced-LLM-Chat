import { Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { Conversation } from '../../data/objects/conversation';
import { Message } from '../../data/objects/message';
import { DBService } from '../../data/db.service';
import { DatePipe, CommonModule } from '@angular/common';

@Component({
  selector: 'app-conversation',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './conversation.component.html',
  styleUrls: ['./conversation.component.scss']
})
export class ConversationComponent implements OnInit {
  @Input() conversation!: Conversation;
  @Output() selected = new EventEmitter<Conversation>();

  messages: Message[] = [];

  constructor(private db: DBService) {}



  // Lifecycle hook: called once after component is initialized.
  // Loads messages related to this conversation from the local database.
  // (This could be used later for message previews or synchronization.)
  async ngOnInit() {
    this.messages = await this.conversation.getLatestMessages(this.db);
  }

  // Emits the selected conversation to the parent component when the user clicks on this conversation.
  onClick(): void {
    this.selected.emit(this.conversation);
  }
}
