import { Component, Input } from '@angular/core';
import { IConversationSummary } from '../../data/models/conversation.model';

let nextId = 0;

/**
 * Divider after the newest message a conversation's summary covers: from there on the model
 * gets the summary instead of the messages above. Opens to show the summary.
 */
@Component({
  selector: 'app-chat-ui-summary',
  templateUrl: './chat-ui-summary.component.html',
  styleUrls: ['./chat-ui-summary.component.scss'],
  standalone: false
})
export class ChatUiSummaryComponent {
  @Input({ required: true }) summary!: IConversationSummary;

  expanded = false;
  readonly panelId = `conversation-summary-${++nextId}`;

  toggle(): void {
    this.expanded = !this.expanded;
  }
}
