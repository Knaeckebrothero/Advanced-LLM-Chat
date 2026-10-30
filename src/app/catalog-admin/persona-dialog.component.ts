import { Component, Inject } from '@angular/core';
import { FormArray, FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatRadioModule } from '@angular/material/radio';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import {
  BUILT_IN_PERSONA_VARIABLES,
  IPersonaCreate,
  IPersonaOut,
  IPersonaVariable,
  IToolStatus,
  ToolGroup
} from '../data/models/catalog.model';
import { CatalogAdminStore } from './catalog-admin.store';
import { describeHttpError, findPlaceholders, numberOrNull, textOrNull, toolIcon } from './catalog-admin.utils';

export interface PersonaDialogData {
  persona: IPersonaOut | null;  // null = add a new agent
  copyOf?: IPersonaOut;  // A new agent filled in from this one (Duplicate)
}

/** "all": every tool the server has (tools = null); "pick": only the checked ones. */
export type ToolMode = 'all' | 'pick';

const VARIABLE_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** Add, edit or duplicate an agent (a persona in the API): a system prompt with {{variables}} and its tools. */
@Component({
  selector: 'app-persona-dialog',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatRadioModule,
    MatSlideToggleModule,
    MatTooltipModule,
    TranslateModule
  ],
  templateUrl: './persona-dialog.component.html',
  styleUrls: ['./catalog-dialog.scss']
})
export class PersonaDialogComponent {
  readonly builtIns = BUILT_IN_PERSONA_VARIABLES.map(name => `{{${name}}}`).join(', ');
  readonly toolIcon = toolIcon;

  form: FormGroup;
  persona: IPersonaOut | null;
  isCopy: boolean;
  tools: IToolStatus[];
  pickedTools: Set<ToolGroup>;  // The explicit selection (tool mode "pick")
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
    this.isCopy = !data.persona && !!data.copyOf;
    const p = data.persona ?? data.copyOf ?? null;
    const name = this.isCopy ? store.copyName(data.copyOf!.name) : p?.name ?? '';
    this.pickedTools = new Set(p?.tools ?? []);
    // The server's tool groups, plus picked ones it doesn't list (shown as unavailable)
    const listed = new Set(store.tools.map(t => t.id));
    this.tools = [
      ...store.tools,
      ...[...this.pickedTools].filter(id => !listed.has(id)).map(id => ({ id, available: false, reason: null }))
    ];
    this.form = fb.group({
      name: [name, Validators.required],
      description: [p?.description ?? ''],
      systemPrompt: [p?.systemPrompt ?? '', Validators.required],
      variables: fb.array((p?.variables ?? []).map(v => this.variableGroup(v))),
      toolMode: [(Array.isArray(p?.tools) ? 'pick' : 'all') as ToolMode],
      availableToGuests: [p?.availableToGuests ?? false],
      enabled: [p?.enabled ?? true],
      sortOrder: [p?.sortOrder ?? 0]
    });
  }

  get isNew(): boolean {
    return this.persona === null;
  }

  get toolMode(): ToolMode {
    return this.form.controls['toolMode'].value;
  }

  /** Switching to "pick" starts from what "all" gives today, unless something is picked already. */
  onToolModeChange(mode: ToolMode): void {
    if (mode === 'pick' && this.pickedTools.size === 0) {
      this.pickedTools = new Set(this.tools.filter(t => t.available).map(t => t.id));
    }
  }

  isToolChecked(tool: IToolStatus): boolean {
    return this.toolMode === 'all' ? tool.available : this.pickedTools.has(tool.id);
  }

  /** An unavailable tool can't be picked, but one that is picked already can be removed. */
  isToolDisabled(tool: IToolStatus): boolean {
    return this.toolMode === 'all' || (!tool.available && !this.pickedTools.has(tool.id));
  }

  toggleTool(id: ToolGroup, checked: boolean): void {
    if (checked) this.pickedTools.add(id);
    else this.pickedTools.delete(id);
    this.form.markAsDirty();
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
      // Keep the server's order of the groups
      tools: v.toolMode === 'pick' ? this.tools.map(t => t.id).filter(id => this.pickedTools.has(id)) : null,
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
