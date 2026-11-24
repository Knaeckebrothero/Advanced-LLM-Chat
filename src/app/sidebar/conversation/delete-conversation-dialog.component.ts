import { Component, Inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { TranslateModule } from '@ngx-translate/core';

export interface DeleteConversationDialogData {
  name: string;
  // How many side chats it has (docs/side_chats.md)
  sideChats: number;
}

/** What becomes of a deleted conversation's side chats; the dialog closes without a value on Cancel. */
export type DeleteConversationChoice = 'keep' | 'delete';

/**
 * Deleting a conversation that has side chats (docs/side_chats.md): keep them as conversations of
 * their own, or delete them with it.
 */
@Component({
  selector: 'app-delete-conversation-dialog',
  standalone: true,
  imports: [MatDialogModule, MatButtonModule, TranslateModule],
  template: `
    <h2 mat-dialog-title>{{ 'sideChat.deleteTitle' | translate: { name: data.name } }}</h2>
    <mat-dialog-content>
      <p class="delete-message">
        {{ (data.sideChats === 1 ? 'sideChat.deleteMessageOne' : 'sideChat.deleteMessage') | translate: { count: data.sideChats } }}
      </p>
    </mat-dialog-content>
    <mat-dialog-actions class="delete-actions">
      <button mat-stroked-button type="button" cdkFocusInitial [mat-dialog-close]="'keep'">
        {{ (data.sideChats === 1 ? 'sideChat.deleteKeepOne' : 'sideChat.deleteKeep') | translate }}
      </button>
      <button mat-flat-button type="button" class="danger-button" [mat-dialog-close]="'delete'">
        {{ (data.sideChats === 1 ? 'sideChat.deleteAllOne' : 'sideChat.deleteAll') | translate }}
      </button>
      <button mat-button type="button" [mat-dialog-close]="undefined">{{ 'catalog.common.cancel' | translate }}</button>
    </mat-dialog-actions>
  `,
  styles: [`
    .delete-message {
      max-width: 440px;
      margin: 0;
      color: var(--theme-text);
      line-height: 1.5;
    }

    // Three choices, one under the other: each says what happens
    .delete-actions.mat-mdc-dialog-actions {
      flex-direction: column;
      align-items: stretch;
      gap: 8px;
      padding: 8px 24px 20px;

      button {
        margin: 0;
        height: 44px;
      }
    }

    .danger-button.mat-mdc-unelevated-button:not(:disabled) {
      background-color: var(--theme-tier-untrusted);
      color: var(--theme-surface);
    }
  `]
})
export class DeleteConversationDialogComponent {
  constructor(@Inject(MAT_DIALOG_DATA) public data: DeleteConversationDialogData) {}
}
