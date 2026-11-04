import { inject, Injectable } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { AuthService } from '../auth/auth.service';
import { ChatStateService } from '../services/chat-state.service';
import { UIStateService } from '../services/ui-state.service';
import { SettingsComponent } from './settings.component';

const SETTINGS_DIALOG_ID = 'settings';

/** Opens the Settings dialog (from the sidebar's gear, or the /settings link). */
@Injectable({ providedIn: 'root' })
export class SettingsDialogService {
  private dialog = inject(MatDialog);
  private chatState = inject(ChatStateService);
  private uiState = inject(UIStateService);
  private router = inject(Router);

  open(): MatDialogRef<SettingsComponent> {
    const open = this.dialog.getDialogById(SETTINGS_DIALOG_ID) as MatDialogRef<SettingsComponent> | undefined;
    if (open) {
      return open;
    }
    // Its width is in the styles (two columns on wide screens); never larger than the screen:
    // the dialog scrolls instead (dvh leaves out the browser bars on phones)
    const dialogRef = this.dialog.open(SettingsComponent, {
      id: SETTINGS_DIALOG_ID,
      panelClass: 'settings-dialog-panel',
      backdropClass: 'custom-backdrop',
      maxWidth: 'calc(100vw - 24px)',
      maxHeight: 'calc(100dvh - 24px)',
      // The dialog itself takes the focus, not its first button: opened by a link, the browser would
      // show that button's focus ring, which looks like a selection; Tab still starts at the top
      autoFocus: 'dialog',
      ariaLabelledBy: 'settings-title',
    });

    // After an import, the imported conversation opens
    dialogRef.afterClosed().subscribe((result?: { openConversationId?: string }) => {
      if (result?.openConversationId) {
        this.chatState.loadConversation(result.openConversationId);
        this.router.navigate(['/']);
        this.uiState.closeSidebarOnMobile();
      }
    });
    return dialogRef;
  }
}

/**
 * /settings has no page of its own: it opens the Settings dialog over the current page,
 * or over the chat when the app starts with that link.
 */
export const settingsDialogGuard: CanActivateFn = async () => {
  const authService = inject(AuthService);
  const settingsDialog = inject(SettingsDialogService);
  const router = inject(Router);
  await authService.initializeAuth();
  if (authService.isAuthenticated()) {
    settingsDialog.open();
  }
  return router.navigated ? false : router.createUrlTree(['/']);
};
