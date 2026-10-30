import { Component, Inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { TranslateModule } from '@ngx-translate/core';

export interface ConfirmDialogData {
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
}

/** A yes/no question; closes with true when confirmed. */
@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  imports: [MatDialogModule, MatButtonModule, TranslateModule],
  template: `
    <h2 mat-dialog-title>{{ data.title }}</h2>
    <mat-dialog-content>
      <p class="confirm-message">{{ data.message }}</p>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" [mat-dialog-close]="false">{{ 'catalog.common.cancel' | translate }}</button>
      <button mat-flat-button type="button" cdkFocusInitial
              [class.danger-button]="data.danger"
              [mat-dialog-close]="true">{{ data.confirmLabel }}</button>
    </mat-dialog-actions>
  `,
  styles: [`
    .confirm-message {
      margin: 0;
      color: var(--theme-text);
      line-height: 1.5;
    }

    .danger-button.mat-mdc-unelevated-button:not(:disabled) {
      background-color: var(--theme-tier-untrusted);
      color: var(--theme-surface);
    }
  `]
})
export class ConfirmDialogComponent {
  constructor(@Inject(MAT_DIALOG_DATA) public data: ConfirmDialogData) {}
}
