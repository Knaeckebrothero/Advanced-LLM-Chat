import { Injectable, Injector } from '@angular/core';
import { ComponentType } from '@angular/cdk/portal';
import { MatDialog } from '@angular/material/dialog';
import { MatSnackBar } from '@angular/material/snack-bar';
import { TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';
import { ConfirmDialogComponent, ConfirmDialogData } from './confirm-dialog.component';
import { describeHttpError } from './catalog-admin.utils';

/**
 * Dialogs and messages of the catalog page. Dialogs get the page's injector, so they can use
 * its CatalogAdminStore.
 */
@Injectable()
export class CatalogAdminDialogs {
  constructor(
    private dialog: MatDialog,
    private snackBar: MatSnackBar,
    private translate: TranslateService,
    private injector: Injector
  ) {}

  open<C, D, R>(component: ComponentType<C>, data: D): Promise<R | undefined> {
    const ref = this.dialog.open<C, D, R>(component, {
      data,
      injector: this.injector,
      panelClass: 'catalog-dialog-panel',
      backdropClass: 'custom-backdrop',
      maxWidth: '95vw',
      autoFocus: 'first-tabbable'
    });
    return firstValueFrom(ref.afterClosed());
  }

  async confirm(data: ConfirmDialogData): Promise<boolean> {
    const result = await this.open<ConfirmDialogComponent, ConfirmDialogData, boolean>(ConfirmDialogComponent, data);
    return result === true;
  }

  /** A short confirmation at the bottom of the screen (translation key and params). */
  notify(key: string, params?: Record<string, unknown>): void {
    this.snackBar.open(this.translate.instant(key, params), undefined, { duration: 3000 });
  }

  notifyError(error: unknown): void {
    this.snackBar.open(describeHttpError(error, this.translate), this.translate.instant('catalog.common.close'), {
      duration: 8000
    });
  }

  t(key: string, params?: Record<string, unknown>): string {
    return this.translate.instant(key, params);
  }
}
