import { inject, Injectable } from '@angular/core';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import {
  ConversationFilesDialogComponent,
  ConversationFilesDialogData,
  ConversationFilesDialogResult
} from './conversation-files-dialog.component';

type FilesDialogRef = MatDialogRef<ConversationFilesDialogComponent, ConversationFilesDialogResult>;

/**
 * Opens the list of files: "Files of this chat" (from a conversation's menu in the sidebar, or the
 * composer's attach menu), or "All files" of all conversations (from the settings).
 */
@Injectable({ providedIn: 'root' })
export class ConversationFilesDialogService {
  private dialog = inject(MatDialog);

  /** The files of one conversation. */
  open(conversationId: string, conversationName?: string): FilesDialogRef {
    return this.show({ conversationId, conversationName });
  }

  /**
   * The files of all conversations. It closes with the conversation the user picked in it
   * (`openConversationId`), which the caller opens.
   */
  openAll(): FilesDialogRef {
    return this.show({});
  }

  private show(data: ConversationFilesDialogData): FilesDialogRef {
    // Its width is in the styles; never larger than the screen (dvh leaves out the browser bars on phones)
    return this.dialog.open<ConversationFilesDialogComponent, ConversationFilesDialogData, ConversationFilesDialogResult>(
      ConversationFilesDialogComponent, {
        data,
        panelClass: 'conversation-files-dialog-panel',
        backdropClass: 'custom-backdrop',
        maxWidth: 'calc(100vw - 24px)',
        maxHeight: 'calc(100dvh - 24px)',
        // The dialog itself takes the focus, not its close button
        autoFocus: 'dialog',
        ariaLabelledBy: 'conversation-files-title',
      });
  }
}
