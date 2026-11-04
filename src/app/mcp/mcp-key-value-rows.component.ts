import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormArray, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';
import { KeyValueRow, secretVarNames } from './mcp-utils';

/**
 * Rows of names and values in the MCP server dialog: the headers, and the environment of a stdio
 * server. With `secret`, values are masked and a stored header shows that its value is kept.
 */
@Component({
  selector: 'app-mcp-key-value-rows',
  standalone: true,
  imports: [ReactiveFormsModule, MatButtonModule, MatFormFieldModule, MatIconModule, MatInputModule, MatTooltipModule, TranslateModule],
  template: `
    @for (row of rows.controls; track row; let i = $index) {
      <div class="kv-row" [formGroup]="row">
        <mat-form-field appearance="outline">
          <mat-label>{{ keyLabel }}</mat-label>
          <input matInput formControlName="key" class="code-input" required autocomplete="off"
                 [placeholder]="keyPlaceholder">
          @if (row.controls.key.hasError('required')) {
            <mat-error>{{ 'catalog.admin.validation.required' | translate }}</mat-error>
          } @else if (row.controls.key.hasError('pattern')) {
            <mat-error>{{ keyPatternError }}</mat-error>
          }
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>{{ valueLabel }}</mat-label>
          <input matInput formControlName="value" class="code-input"
                 [type]="secret ? 'password' : 'text'"
                 [attr.autocomplete]="secret ? 'new-password' : 'off'"
                 [placeholder]="isStored(row) ? '••••••••' : valuePlaceholder">
          @if (isStored(row)) {
            <mat-hint>{{ 'mcp.dialog.headerStored' | translate }}</mat-hint>
          }
          @if (row.controls.value.hasError('required')) {
            <mat-error>{{ 'catalog.admin.validation.required' | translate }}</mat-error>
          } @else if (secretVarNames(row.controls.value)) {
            <mat-error>{{ 'mcp.dialog.secretVar' | translate: { names: secretVarNames(row.controls.value) } }}</mat-error>
          }
        </mat-form-field>
        <button mat-icon-button type="button" (click)="remove(i)"
                [matTooltip]="'mcp.dialog.removeRow' | translate"
                [attr.aria-label]="('mcp.dialog.removeRow' | translate) + ': ' + (row.controls.key.value || keyLabel)">
          <mat-icon>remove_circle_outline</mat-icon>
        </button>
      </div>
    }
    <button mat-stroked-button type="button" class="kv-add" (click)="add.emit()">
      <mat-icon>add</mat-icon>
      {{ addLabel }}
    </button>
  `,
  styles: [`
    :host {
      display: block;
      margin-bottom: 12px;
    }

    .kv-row {
      display: grid;
      grid-template-columns: minmax(120px, 2fr) minmax(140px, 3fr) auto;
      gap: 8px;
      align-items: start;

      .mat-mdc-form-field {
        margin-bottom: 12px;
      }

      button {
        margin-top: 8px;
      }

      // Phones: the value under the name, a line between rows
      @media (max-width: 600px) {
        grid-template-columns: 1fr auto;

        .mat-mdc-form-field:nth-child(2) {
          grid-column: 1;
          grid-row: 2;
        }

        & + .kv-row {
          padding-top: 12px;
          border-top: 1px dashed var(--theme-border);
        }
      }
    }

    .code-input {
      font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
      font-size: 0.85rem;
      letter-spacing: normal;
    }
  `]
})
export class McpKeyValueRowsComponent {
  @Input({ required: true }) rows!: FormArray<KeyValueRow>;
  @Input() keyLabel = '';
  @Input() valueLabel = '';
  @Input() keyPlaceholder = '';
  @Input() valuePlaceholder = '';
  @Input() keyPatternError = '';
  @Input() addLabel = '';
  /** Values are secrets (users' headers): masked, and stored ones may stay empty. */
  @Input() secret = false;
  @Output() add = new EventEmitter<void>();
  readonly secretVarNames = secretVarNames;

  isStored(row: KeyValueRow): boolean {
    const stored = row.controls.stored.value;
    return stored !== null && row.controls.key.value.trim() === stored;
  }

  remove(index: number): void {
    this.rows.removeAt(index);
    this.rows.markAsDirty();
  }
}
