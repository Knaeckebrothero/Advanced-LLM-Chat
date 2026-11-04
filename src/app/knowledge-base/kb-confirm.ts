import { MatDialog } from '@angular/material/dialog';
import { firstValueFrom } from 'rxjs';
import { ConfirmDialogComponent, ConfirmDialogData } from '../catalog-admin/confirm-dialog.component';

/** Ask a yes/no question in the dialog style of the Agents page; true when confirmed. */
export async function confirmDialog(dialog: MatDialog, data: ConfirmDialogData): Promise<boolean> {
  const ref = dialog.open<ConfirmDialogComponent, ConfirmDialogData, boolean>(ConfirmDialogComponent, {
    data,
    panelClass: 'catalog-dialog-panel',
    backdropClass: 'custom-backdrop',
    maxWidth: '95vw',
    width: '440px',
    autoFocus: 'first-tabbable'
  });
  return (await firstValueFrom(ref.afterClosed())) === true;
}
