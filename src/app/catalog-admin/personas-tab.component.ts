import { Component } from '@angular/core';
import { AsyncPipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';
import { IPersonaOut } from '../data/models/catalog.model';
import { CatalogAdminStore } from './catalog-admin.store';
import { CatalogAdminDialogs } from './catalog-admin-dialogs';
import { PersonaDialogComponent, PersonaDialogData } from './persona-dialog.component';

/** Personas: named system prompts with fill-in variables. */
@Component({
  selector: 'app-personas-tab',
  standalone: true,
  imports: [AsyncPipe, MatButtonModule, MatIconModule, MatTooltipModule, TranslateModule],
  template: `
    <div class="tab-toolbar">
      <p class="tab-intro">{{ 'catalog.admin.personas.intro' | translate }}</p>
      <div class="tab-toolbar-actions">
        <button mat-flat-button color="primary" type="button" (click)="add()">
          <mat-icon>add</mat-icon>
          {{ 'catalog.admin.personas.add' | translate }}
        </button>
      </div>
    </div>

    @if (store.personas$ | async; as personas) {
      <div class="item-list">
        @for (persona of sorted(personas); track persona.id) {
          <div class="item-card" [class.is-disabled]="!persona.enabled">
            <div class="item-main">
              <div class="item-title-row">
                <span class="item-title">{{ persona.name }}</span>
                @if (!persona.enabled) {
                  <span class="state-tag">{{ 'catalog.admin.disabled' | translate }}</span>
                }
                @if (persona.availableToGuests) {
                  <span class="state-tag state-tag--accent">{{ 'catalog.admin.fields.guests' | translate }}</span>
                }
              </div>
              @if (persona.description) {
                <p class="item-description">{{ persona.description }}</p>
              }
              <div class="item-meta">
                @if (persona.variables.length > 0) {
                  <span class="chip-list">
                    @for (variable of persona.variables; track variable.name) {
                      <span class="state-tag mono">{{ variable.name }}</span>
                    }
                  </span>
                }
                <span>
                  <mat-icon aria-hidden="true">smart_toy</mat-icon>
                  {{ modelName(persona.defaultModelId) ?? ('catalog.admin.personas.noDefaultModel' | translate) }}
                </span>
                <span>#{{ persona.sortOrder }}</span>
              </div>
            </div>
            <div class="item-controls">
              <div class="item-actions">
                <button mat-icon-button type="button" (click)="edit(persona)"
                        [matTooltip]="'catalog.common.edit' | translate"
                        [attr.aria-label]="('catalog.common.edit' | translate) + ': ' + persona.name">
                  <mat-icon>edit</mat-icon>
                </button>
                <button mat-icon-button type="button" class="danger-action" (click)="remove(persona)"
                        [matTooltip]="'catalog.common.delete' | translate"
                        [attr.aria-label]="('catalog.common.delete' | translate) + ': ' + persona.name">
                  <mat-icon>delete_outline</mat-icon>
                </button>
              </div>
            </div>
          </div>
        } @empty {
          <div class="empty-state">
            <mat-icon aria-hidden="true">theater_comedy</mat-icon>
            <p>{{ 'catalog.admin.personas.empty' | translate }}</p>
          </div>
        }
      </div>
    }
  `,
  styleUrls: ['./catalog-admin-list.scss']
})
export class PersonasTabComponent {
  constructor(
    public store: CatalogAdminStore,
    private dialogs: CatalogAdminDialogs
  ) {}

  sorted(personas: IPersonaOut[]): IPersonaOut[] {
    return [...personas].sort((a, b) => a.sortOrder - b.sortOrder || a.name.localeCompare(b.name));
  }

  modelName(id: number | null | undefined): string | null {
    if (id == null) return null;
    const model = this.store.models.find(m => m.id === id);
    return model ? `${model.displayName} · ${model.providerName}` : `#${id}`;
  }

  async add(): Promise<void> {
    const saved = await this.dialogs.open<PersonaDialogComponent, PersonaDialogData, IPersonaOut>(
      PersonaDialogComponent, { persona: null, models: this.store.models }
    );
    if (saved) this.dialogs.notify('catalog.admin.personas.saved', { name: saved.name });
  }

  async edit(persona: IPersonaOut): Promise<void> {
    const saved = await this.dialogs.open<PersonaDialogComponent, PersonaDialogData, IPersonaOut>(
      PersonaDialogComponent, { persona, models: this.store.models }
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
