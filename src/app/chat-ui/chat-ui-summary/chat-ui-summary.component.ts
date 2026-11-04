import { Component, Input } from '@angular/core';
import { IConversationSummary } from '../../data/models/conversation.model';

let nextId = 0;

/**
 * Divider after the newest message a conversation's summary covers: from there on the model
 * gets the summary instead of the messages above. Opens to show the summary.
 *
 * With pending, it marks a summary being written at the user's request (after the newest message).
 */
@Component({
  selector: 'app-chat-ui-summary',
  templateUrl: './chat-ui-summary.component.html',
  styleUrls: ['./chat-ui-summary.component.scss'],
  standalone: false
})
export class ChatUiSummaryComponent {
  @Input() summary: IConversationSummary | null = null;
  @Input() pending = false;

  expanded = false;
  readonly panelId = `conversation-summary-${++nextId}`;

  toggle(): void {
    this.expanded = !this.expanded;
  }
}
