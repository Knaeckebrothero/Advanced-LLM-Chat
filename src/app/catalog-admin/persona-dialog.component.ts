import { Component, ElementRef, Inject } from '@angular/core';
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
  ISkillOut,
  IToolStatus,
  ToolGroup
} from '../data/models/catalog.model';
import { IMcpServerOut } from '../data/models/mcp.model';
import { sortServers } from '../mcp/mcp-utils';
import { CatalogAdminStore } from './catalog-admin.store';
import { FamilyModeService } from '../services/family-mode.service';
import { describeHttpError, DIALOG_ERROR, findPlaceholders, INVALID_FIELD, numberOrNull, revealInDialog, textOrNull, toolIcon } from './catalog-admin.utils';

export interface PersonaDialogData {
  persona: IPersonaOut | null;  // null = add a new agent
  copyOf?: IPersonaOut;  // A new agent filled in from this one (Duplicate)
}

/** "all": every tool the server has (tools = null); "pick": only the checked ones. */
export type ToolMode = 'all' | 'pick';

/** An MCP server the agent can pick; `server` is null for a slug the agent has that no server has (any more). */
interface McpOption {
  slug: string;
  name: string;
  server: IMcpServerOut | null;
}

/** A skill the agent can pick; `skill` is null for a name the agent has that no skill has (any more). */
interface SkillOption {
  name: string;
  skill: ISkillOut | null;
}

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
  mcpOptions: McpOption[];
  pickedMcp: Set<string>;  // Slugs of the picked MCP servers (tool mode "pick")
  mcpLoadError: string | null;
  skillOptions: SkillOption[];
  pickedSkills: Set<string>;  // Names of the picked skills (docs/skills.md)
  skillsLoadError: string | null;
  saving = false;
  error: string | null = null;

  /** The server offers family mode. */
  readonly familyModeAvailable: boolean;

  constructor(
    @Inject(MAT_DIALOG_DATA) data: PersonaDialogData,
    private dialogRef: MatDialogRef<PersonaDialogComponent, IPersonaOut>,
    private host: ElementRef<HTMLElement>,
    private store: CatalogAdminStore,
    private translate: TranslateService,
    private fb: FormBuilder,
    familyMode: FamilyModeService
  ) {
    this.familyModeAvailable = familyMode.available;
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
    // The admin servers, plus picked slugs no server has (shown so they can be removed)
    this.pickedMcp = new Set(p?.mcpServers ?? []);
    const servers = sortServers(store.mcpServers);
    const knownSlugs = new Set(servers.map(server => server.slug));
    this.mcpOptions = [
      ...servers.map(server => ({ slug: server.slug, name: server.name, server })),
      ...[...this.pickedMcp].filter(slug => !knownSlugs.has(slug)).map(slug => ({ slug, name: slug, server: null }))
    ];
    this.mcpLoadError = store.mcpError$.value;
    // The skills, plus picked names no skill has (shown so they can be removed)
    this.pickedSkills = new Set(p?.skills ?? []);
    const knownSkills = new Set(store.skills.map(skill => skill.name));
    this.skillOptions = [
      ...store.skills.map(skill => ({ name: skill.name, skill })),
      ...[...this.pickedSkills].filter(name => !knownSkills.has(name)).map(name => ({ name, skill: null }))
    ];
    this.skillsLoadError = store.skillsError$.value;
    this.form = fb.group({
      name: [name, Validators.required],
      description: [p?.description ?? ''],
      systemPrompt: [p?.systemPrompt ?? '', Validators.required],
      variables: fb.array((p?.variables ?? []).map(v => this.variableGroup(v))),
      toolMode: [(Array.isArray(p?.tools) ? 'pick' : 'all') as ToolMode],
      availableToGuests: [p?.availableToGuests ?? false],
      enabled: [p?.enabled ?? true],
      sortOrder: [p?.sortOrder ?? 0],
      ownMemory: [p?.ownMemory ?? false],
      hidden: [p?.hidden ?? false]
    });
  }

  /** The agent has the knowledge base (picked), so it can have its own memory instead of the shared one. */
  get hasKnowledgeBase(): boolean {
    return this.toolMode === 'pick' && this.pickedTools.has('knowledge_base');
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
      this.pickedTools = new Set(this.tools.filter(t => this.inAllTools(t)).map(t => t.id));
    }
  }

  /** What "all tools" gives: the available groups except the opt-in ones (the knowledge base). */
  private inAllTools(tool: IToolStatus): boolean {
    return tool.available && !tool.optIn;
  }

  isToolChecked(tool: IToolStatus): boolean {
    return this.toolMode === 'all' ? this.inAllTools(tool) : this.pickedTools.has(tool.id);
  }

  /**
   * An unavailable tool can't be picked, nor one whose required group isn't picked (the past chats
   * need the knowledge base); one that is picked already can be removed.
   */
  isToolDisabled(tool: IToolStatus): boolean {
    if (this.toolMode === 'all') return true;
    if (this.pickedTools.has(tool.id)) return false;
    return !tool.available || (!!tool.requires && !this.pickedTools.has(tool.requires));
  }

  /** The hint under an opt-in group: what picking it gives. */
  optInHint(id: ToolGroup): string {
    if (id === 'user_mcp') return 'catalog.admin.personas.toolOptInUserMcp';
    if (id === 'past_chats') return 'catalog.admin.personas.toolOptInPastChats';
    return 'catalog.admin.personas.toolOptIn';
  }

  /** Removing a group also removes the groups that only work with it. */
  toggleTool(id: ToolGroup, checked: boolean): void {
    if (checked) {
      this.pickedTools.add(id);
    } else {
      this.pickedTools.delete(id);
      for (const tool of this.tools) {
        if (tool.requires === id) this.pickedTools.delete(tool.id);
      }
    }
    this.form.markAsDirty();
  }

  // MCP servers: picked one by one, with either tool mode ("all tools" never includes them)

  isMcpChecked(option: McpOption): boolean {
    return this.pickedMcp.has(option.slug);
  }

  /** A server that no longer exists can't be picked, but one that is picked already can be removed. */
  isMcpDisabled(option: McpOption): boolean {
    return option.server === null && !this.pickedMcp.has(option.slug);
  }

  isMcpUsable(option: McpOption): boolean {
    return !!option.server && option.server.enabled && !option.server.unavailableReason;
  }

  /** Why the server won't give the agent tools, or a note about guests; null when there is nothing to say. */
  mcpNote(option: McpOption): string | null {
    const server = option.server;
    if (!server) return this.translate.instant('catalog.admin.personas.mcpUnknown');
    if (!server.enabled) return this.translate.instant('catalog.admin.personas.mcpDisabled');
    if (server.unavailableReason) return this.translate.instant('mcp.unavailable', { reason: server.unavailableReason });
    if (this.form.controls['availableToGuests'].value && !server.availableToGuests) {
      return this.translate.instant('catalog.admin.personas.mcpNotForGuests');
    }
    return null;
  }

  toggleMcp(slug: string, checked: boolean): void {
    if (checked) this.pickedMcp.add(slug);
    else this.pickedMcp.delete(slug);
    this.form.markAsDirty();
  }

  // Skills: picked one by one (docs/skills.md); the agent loads them when a request needs one

  isSkillChecked(option: SkillOption): boolean {
    return this.pickedSkills.has(option.name);
  }

  /** A skill that no longer exists can't be picked, but one that is picked already can be removed. */
  isSkillDisabled(option: SkillOption): boolean {
    return option.skill === null && !this.pickedSkills.has(option.name);
  }

  /** Why the agent won't get the skill; null when it will. */
  skillNote(option: SkillOption): string | null {
    if (!option.skill) return this.translate.instant('catalog.admin.personas.skillUnknown');
    if (!option.skill.enabled) return this.translate.instant('catalog.admin.personas.skillDisabled');
    return null;
  }

  toggleSkill(name: string, checked: boolean): void {
    if (checked) this.pickedSkills.add(name);
    else this.pickedSkills.delete(name);
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
    if (this.saving) return;
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      revealInDialog(this.host.nativeElement, INVALID_FIELD);
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
      sortOrder: numberOrNull(v.sortOrder) ?? 0,
      ownMemory: !!v.ownMemory,
      hidden: !!v.hidden,
      // [] for none: unambiguous for create and update
      mcpServers: this.mcpOptions.map(o => o.slug).filter(slug => this.pickedMcp.has(slug)),
      skills: this.skillOptions.map(o => o.name).filter(name => this.pickedSkills.has(name))
    };

    this.saving = true;
    this.error = null;
    try {
      const saved = await this.store.savePersona(this.persona?.id ?? null, body);
      this.dialogRef.close(saved);
    } catch (error) {
      this.error = describeHttpError(error, this.translate);
      revealInDialog(this.host.nativeElement, DIALOG_ERROR);
    } finally {
      this.saving = false;
    }
  }
}
