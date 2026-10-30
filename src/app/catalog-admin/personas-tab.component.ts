import { Component } from '@angular/core';
import { AsyncPipe } from '@angular/common';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { IPersonaOut, IPublicPersona, ToolGroup } from '../data/models/catalog.model';
import { CatalogService } from '../services/catalog.service';
import { ChatStateService } from '../services/chat-state.service';
import { askPersonaValues, personaInputVariables } from '../chat-ui/model-picker/persona-values-dialog.component';
import { CatalogAdminStore } from './catalog-admin.store';
import { CatalogAdminDialogs } from './catalog-admin-dialogs';
import { PersonaDialogComponent, PersonaDialogData } from './persona-dialog.component';
import { toolIcon } from './catalog-admin.utils';

/** Agents (personas in the API): a named system prompt with fill-in variables and a set of tools. */
@Component({
  selector: 'app-personas-tab',
  standalone: true,
  imports: [AsyncPipe, MatButtonModule, MatIconModule, MatTooltipModule, TranslateModule],
  template: `
    <div class="section-header">
      <div class="section-heading">
        <h2 class="section-title">{{ 'catalog.admin.personas.title' | translate }}</h2>
        <p class="section-intro">{{ 'catalog.admin.personas.intro' | translate }}</p>
      </div>
      <div class="section-actions">
        <button mat-flat-button color="primary" type="button" (click)="add()">
          <mat-icon>add</mat-icon>
          {{ 'catalog.admin.personas.add' | translate }}
        </button>
      </div>
    </div>

    @if (store.personas$ | async; as personas) {
      <div class="agent-grid">
        @for (persona of sorted(personas); track persona.id) {
          <article class="agent-card" [class.is-disabled]="!persona.enabled">
            <div class="agent-head">
              <span class="agent-avatar" aria-hidden="true"><mat-icon>smart_toy</mat-icon></span>
              <div class="agent-title">
                <h3 class="item-title">{{ persona.name }}</h3>
                <div class="agent-tags">
                  @if (!persona.enabled) {
                    <span class="state-tag">{{ 'catalog.admin.disabled' | translate }}</span>
                  }
                  @if (persona.availableToGuests) {
                    <span class="state-tag state-tag--accent">{{ 'catalog.admin.fields.guests' | translate }}</span>
                  }
                </div>
              </div>
            </div>

            @if (persona.description) {
              <p class="item-description agent-description">{{ persona.description }}</p>
            }

            <div class="tool-chips" role="list" [attr.aria-label]="'catalog.admin.personas.toolsSection' | translate">
              @if (persona.tools == null) {
                <span class="tool-chip tool-chip--all" role="listitem"
                      [matTooltip]="allToolsHint()">
                  <mat-icon aria-hidden="true">construction</mat-icon>
                  {{ 'catalog.admin.personas.allTools' | translate }}
                </span>
              } @else {
                @for (tool of persona.tools; track tool) {
                  <span class="tool-chip" role="listitem"
                        [class.is-unavailable]="!isAvailable(tool)"
                        [matTooltip]="unavailableHint(tool)"
                        [matTooltipDisabled]="isAvailable(tool)">
                    <mat-icon aria-hidden="true">{{ toolIcon(tool) }}</mat-icon>
                    {{ ('catalog.tools.' + tool) | translate }}
                  </span>
                } @empty {
                  <span class="tool-chip tool-chip--none" role="listitem">
                    <mat-icon aria-hidden="true">block</mat-icon>
                    {{ 'catalog.admin.personas.noTools' | translate }}
                  </span>
                }
              }
            </div>

            @if (inputLabels(persona); as labels) {
              <p class="agent-inputs">
                <mat-icon aria-hidden="true">tune</mat-icon>
                {{ 'catalog.admin.personas.asksFor' | translate: { names: labels } }}
              </p>
            }

            <div class="agent-actions">
              <button mat-stroked-button color="primary" type="button"
                      [disabled]="!persona.enabled || starting === persona.id"
                      (click)="startChat(persona)">
                <mat-icon>chat_bubble_outline</mat-icon>
                {{ 'catalog.admin.personas.startChat' | translate }}
              </button>
              <div class="item-actions">
                <button mat-icon-button type="button" (click)="edit(persona)"
                        [matTooltip]="'catalog.common.edit' | translate"
                        [attr.aria-label]="('catalog.common.edit' | translate) + ': ' + persona.name">
                  <mat-icon>edit</mat-icon>
                </button>
                <button mat-icon-button type="button" (click)="duplicate(persona)"
                        [matTooltip]="'catalog.admin.personas.duplicate' | translate"
                        [attr.aria-label]="('catalog.admin.personas.duplicate' | translate) + ': ' + persona.name">
                  <mat-icon>content_copy</mat-icon>
                </button>
                <button mat-icon-button type="button" class="danger-action" (click)="remove(persona)"
                        [matTooltip]="'catalog.common.delete' | translate"
                        [attr.aria-label]="('catalog.common.delete' | translate) + ': ' + persona.name">
                  <mat-icon>delete_outline</mat-icon>
                </button>
              </div>
            </div>
          </article>
        } @empty {
          <div class="empty-state">
            <mat-icon aria-hidden="true">smart_toy</mat-icon>
            <p>{{ 'catalog.admin.personas.empty' | translate }}</p>
          </div>
        }
      </div>
    }
  `,
  styleUrls: ['./catalog-admin-list.scss']
})
export class PersonasTabComponent {
  readonly toolIcon = toolIcon;
  starting: number | null = null;  // The agent whose chat is being started

  constructor(
    public store: CatalogAdminStore,
    private dialogs: CatalogAdminDialogs,
    private dialog: MatDialog,
    private catalog: CatalogService,
    private chatState: ChatStateService,
    private router: Router,
    private translate: TranslateService
  ) {}

  sorted(personas: IPersonaOut[]): IPersonaOut[] {
    return [...personas].sort((a, b) => a.sortOrder - b.sortOrder || a.name.localeCompare(b.name));
  }

  isAvailable(tool: ToolGroup): boolean {
    return this.store.tools.find(t => t.id === tool)?.available ?? true;
  }

  unavailableHint(tool: ToolGroup): string {
    const reason = this.store.tools.find(t => t.id === tool)?.reason;
    return this.translate.instant('catalog.admin.personas.toolUnavailable', {
      reason: reason || this.translate.instant('catalog.admin.personas.toolUnavailableUnknown')
    });
  }

  /** What "All tools" currently means on this server. */
  allToolsHint(): string {
    const available = this.store.tools.filter(t => t.available).map(t => this.translate.instant('catalog.tools.' + t.id));
    return available.length > 0
      ? this.translate.instant('catalog.admin.personas.allToolsHint', { tools: available.join(', ') })
      : this.translate.instant('catalog.admin.personas.allToolsNone');
  }

  /** Labels of the variables the user fills in when starting a chat, or null when there are none. */
  inputLabels(persona: IPersonaOut): string | null {
    const variables = personaInputVariables(persona);
    return variables.length > 0 ? variables.map(v => v.label || v.name).join(', ') : null;
  }

  /**
   * Open a new chat with this agent, the way the composer's agent menu picks one: ask for its
   * variables (if any), then select it for a new conversation draft. The model stays as it is.
   */
  async startChat(persona: IPersonaOut): Promise<void> {
    if (!persona.enabled) return;
    // The public view of the agent; right after a save the pickers' list may not be reloaded yet
    const agent: IPublicPersona = this.catalog.getPersona(persona.id) ?? {
      id: persona.id,
      name: persona.name,
      description: persona.description,
      systemPrompt: persona.systemPrompt,
      variables: persona.variables,
      tools: persona.tools
    };

    const values = await askPersonaValues(this.dialog, agent);
    if (values === undefined) return;  // Cancelled

    this.starting = persona.id;
    try {
      await this.chatState.createNewConversation();
      await this.chatState.selectPersona(agent, values);
      await this.router.navigate(['/']);
    } catch (error) {
      this.dialogs.notifyError(error);
    } finally {
      this.starting = null;
    }
  }

  async add(): Promise<void> {
    const saved = await this.dialogs.open<PersonaDialogComponent, PersonaDialogData, IPersonaOut>(
      PersonaDialogComponent, { persona: null }
    );
    if (saved) this.dialogs.notify('catalog.admin.personas.saved', { name: saved.name });
  }

  async edit(persona: IPersonaOut): Promise<void> {
    const saved = await this.dialogs.open<PersonaDialogComponent, PersonaDialogData, IPersonaOut>(
      PersonaDialogComponent, { persona }
    );
    if (saved) this.dialogs.notify('catalog.admin.personas.saved', { name: saved.name });
  }

  /** Opens the dialog for a new agent, filled in from this one. */
  async duplicate(persona: IPersonaOut): Promise<void> {
    const saved = await this.dialogs.open<PersonaDialogComponent, PersonaDialogData, IPersonaOut>(
      PersonaDialogComponent, { persona: null, copyOf: persona }
    );
    if (saved) this.dialogs.notify('catalog.admin.personas.saved', { name: saved.name });
  }

  async remove(persona: IPersonaOut): Promise<void> {
    const confirmed = await this.dialogs.confirm({
      title: this.dialogs.t('catalog.admin.personas.deleteTitle', { name: persona.name }),
      message: this.dialogs.t('catalog.admin.personas.deleteMessage'),
      confirmLabel: this.dialogs.t('catalog.common.delete'),
      danger: true
    });
    if (!confirmed) return;
    try {
      await this.store.deletePersona(persona.id);
      this.dialogs.notify('catalog.admin.deleted', { name: persona.name });
    } catch (error) {
      this.dialogs.notifyError(error);
    }
  }
}
