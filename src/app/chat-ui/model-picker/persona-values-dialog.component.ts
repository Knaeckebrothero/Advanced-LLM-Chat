import { Component, Inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { TranslateModule } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';
import {
  BUILT_IN_PERSONA_VARIABLES,
  IPersonaVariable,
  IPublicPersona,
  PersonaValues
} from '../../data/models/catalog.model';

export interface PersonaValuesDialogData {
  persona: IPublicPersona;
  values: PersonaValues | null;  // Values stored with the conversation, if it already uses this persona
}

/** The variables of a persona that the user fills in (the built-ins are filled in by the backend). */
export function personaInputVariables(persona: IPublicPersona): IPersonaVariable[] {
  return (persona.variables || []).filter(v => !BUILT_IN_PERSONA_VARIABLES.includes(v.name));
}

/**
 * Asks for the values of a persona's variables before it is used in a chat.
 * Resolves to the values, to null when the persona has nothing to fill in (no dialog),
 * or to undefined when the user cancelled.
 */
export async function askPersonaValues(
  dialog: MatDialog,
  persona: IPublicPersona,
  values: PersonaValues | null = null
): Promise<PersonaValues | null | undefined> {
  if (personaInputVariables(persona).length === 0) {
    return null;
  }
  const ref = dialog.open<PersonaValuesDialogComponent, PersonaValuesDialogData, PersonaValues>(
    PersonaValuesDialogComponent,
    {
      data: { persona, values },
      panelClass: 'catalog-dialog-panel',
      backdropClass: 'custom-backdrop',
      autoFocus: 'first-tabbable'
    }
  );
  return firstValueFrom(ref.afterClosed());
}

/**
 * Asks for the values of a persona's variables, prefilled with the stored values or the defaults.
 * Closes with the values, or undefined when cancelled.
 */
@Component({
  selector: 'app-persona-values-dialog',
  standalone: true,
  imports: [FormsModule, MatDialogModule, MatButtonModule, MatFormFieldModule, MatInputModule, TranslateModule],
  template: `
    <h2 mat-dialog-title>{{ data.persona.name }}</h2>
    <form (ngSubmit)="confirm()" #valuesForm="ngForm">
      <mat-dialog-content>
        @if (data.persona.description) {
          <p class="persona-description">{{ data.persona.description }}</p>
        }
        @for (variable of variables; track variable.name) {
          <mat-form-field appearance="outline" class="full-width">
            <mat-label>{{ variable.label || variable.name }}</mat-label>
            <input matInput [name]="variable.name" [(ngModel)]="values[variable.name]"
                   [placeholder]="variable.default || ''">
          </mat-form-field>
        }
      </mat-dialog-content>
      <mat-dialog-actions align="end">
        <button mat-button type="button" mat-dialog-close>{{ 'catalog.common.cancel' | translate }}</button>
        <button mat-flat-button color="primary" type="submit">{{ 'catalog.picker.usePersona' | translate }}</button>
      </mat-dialog-actions>
    </form>
  `,
  styles: [`
    .full-width { width: 100%; }

    .persona-description {
      margin: 0 0 16px;
      color: var(--theme-text-secondary);
      font-size: 0.9rem;
    }

    mat-dialog-content { min-width: min(360px, 80vw); }
  `]
})
export class PersonaValuesDialogComponent {
  variables: IPersonaVariable[];
  values: PersonaValues = {};

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: PersonaValuesDialogData,
    private dialogRef: MatDialogRef<PersonaValuesDialogComponent, PersonaValues>
  ) {
    this.variables = personaInputVariables(data.persona);
    for (const variable of this.variables) {
      this.values[variable.name] = data.values?.[variable.name] ?? variable.default ?? '';
    }
  }

  confirm(): void {
    this.dialogRef.close({ ...this.values });
  }
}
