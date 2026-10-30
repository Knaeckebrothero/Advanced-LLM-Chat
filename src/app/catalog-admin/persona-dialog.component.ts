import { Component, Inject } from '@angular/core';
import { FormArray, FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import {
  BUILT_IN_PERSONA_VARIABLES,
  IModelOut,
  IPersonaCreate,
  IPersonaOut,
  IPersonaVariable
} from '../data/models/catalog.model';
import { CatalogAdminStore } from './catalog-admin.store';
import { describeHttpError, findPlaceholders, numberOrNull, textOrNull } from './catalog-admin.utils';

export interface PersonaDialogData {
  persona: IPersonaOut | null;  // null = add a new persona
  models: IModelOut[];
}

const VARIABLE_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** Add or edit a persona: a named system prompt with {{variables}}. */
@Component({
  selector: 'app-persona-dialog',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatTooltipModule,
    TranslateModule
  ],
  templateUrl: './persona-dialog.component.html',
  styleUrls: ['./catalog-dialog.scss']
})
export class PersonaDialogComponent {
  readonly builtIns = BUILT_IN_PERSONA_VARIABLES.map(name => `{{${name}}}`).join(', ');

  form: FormGroup;
  persona: IPersonaOut | null;
  models: IModelOut[];
  saving = false;
  error: string | null = null;

  constructor(
    @Inject(MAT_DIALOG_DATA) data: PersonaDialogData,
    private dialogRef: MatDialogRef<PersonaDialogComponent, IPersonaOut>,
    private store: CatalogAdminStore,
    private translate: TranslateService,
    private fb: FormBuilder
  ) {
    this.persona = data.persona;
    this.models = data.models;
    const p = data.persona;
    this.form = fb.group({
      name: [p?.name ?? '', Validators.required],
      description: [p?.description ?? ''],
      systemPrompt: [p?.systemPrompt ?? '', Validators.required],
      variables: fb.array((p?.variables ?? []).map(v => this.variableGroup(v))),
      defaultModelId: [p?.defaultModelId ?? null],
      availableToGuests: [p?.availableToGuests ?? false],
      enabled: [p?.enabled ?? true],
      sortOrder: [p?.sortOrder ?? 0]
    });
  }

  get isNew(): boolean {
    return this.persona === null;
  }

  get variables(): FormArray<FormGroup> {
    return this.form.controls['variables'] as FormArray<FormGroup>;
  }

  /** Placeholders in the prompt that have no variable yet (built-ins need none). */
  get undeclaredPlaceholders(): string[] {
    const declared = new Set(this.variables.controls.map(c => c.controls['name'].value));
    return findPlaceholders(this.form.controls['systemPrompt'].value || '')
      .filter(name => !declared.has(name) && !BUILT_IN_PERSONA_VARIABLES.includes(name));
  }

  private variableGroup(variable?: Partial<IPersonaVariable>): FormGroup {
    return this.fb.group({
      name: [variable?.name ?? '', [Validators.required, Validators.pattern(VARIABLE_NAME)]],
      label: [variable?.label ?? '', Validators.required],
      default: [variable?.default ?? '']
    });
  }

  addVariable(name = ''): void {
    const label = name ? name.charAt(0).toUpperCase() + name.slice(1).replace(/_/g, ' ') : '';
    this.variables.push(this.variableGroup({ name, label }));
  }

  addPlaceholdersFromPrompt(): void {
    for (const name of this.undeclaredPlaceholders) {
      this.addVariable(name);
    }
  }

  removeVariable(index: number): void {
    this.variables.removeAt(index);
  }

  async save(): Promise<void> {
    if (this.form.invalid || this.saving) {
      this.form.markAllAsTouched();
      return;
    }
    const v = this.form.getRawValue();
    const body: IPersonaCreate = {
      name: v.name.trim(),
      description: textOrNull(v.description),
      systemPrompt: v.systemPrompt,
      variables: (v.variables as IPersonaVariable[]).map(variable => ({
        name: variable.name.trim(),
        label: variable.label.trim(),
        default: textOrNull(variable.default)
      })),
      defaultModelId: v.defaultModelId ?? null,
      availableToGuests: !!v.availableToGuests,
      enabled: !!v.enabled,
      sortOrder: numberOrNull(v.sortOrder) ?? 0
    };

    this.saving = true;
    this.error = null;
    try {
      const saved = await this.store.savePersona(this.persona?.id ?? null, body);
      this.dialogRef.close(saved);
    } catch (error) {
      this.error = describeHttpError(error, this.translate);
    } finally {
      this.saving = false;
    }
  }
}
