import { Component } from '@angular/core';
import { AsyncPipe, DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSlideToggleChange, MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { ISkillImportResult, ISkillOut } from '../data/models/catalog.model';
import { CatalogAdminStore } from './catalog-admin.store';
import { CatalogAdminDialogs } from './catalog-admin-dialogs';
import { describeHttpError } from './catalog-admin.utils';
import { SkillDialogComponent, SkillDialogData } from './skill-dialog.component';

/** What importing one SKILL.md file did. */
interface ImportOutcome {
  file: string;
  ok: boolean;
  text: string;
}

/**
 * The agents' skills (docs/skills.md): instructions for one kind of work, which an agent loads
 * when a request needs them. Each agent picks its skills in its dialog. Skills are written here,
 * or imported and exported as SKILL.md files (the format of Claude Code and Anthropic's skills).
 */
@Component({
  selector: 'app-skills-tab',
  standalone: true,
  imports: [
    AsyncPipe,
    DecimalPipe,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSlideToggleModule,
    MatTooltipModule,
    TranslateModule
  ],
  template: `
    <div class="section-header">
      <div class="section-heading">
        <h2 class="section-title">{{ 'catalog.admin.skills.title' | translate }}</h2>
        <p class="section-intro">{{ 'catalog.admin.skills.intro' | translate }}</p>
      </div>
      <div class="section-actions">
        <input #fileInput type="file" accept=".md,.markdown,text/markdown,text/plain" multiple class="hidden-input"
               (change)="onFilesSelected($event)">
        <button mat-stroked-button type="button" (click)="fileInput.click()" [disabled]="importing">
          @if (importing) {
            <mat-spinner diameter="18"></mat-spinner>
          } @else {
            <mat-icon>upload_file</mat-icon>
          }
          {{ 'catalog.admin.skills.import' | translate }}
        </button>
        <button mat-flat-button color="primary" type="button" (click)="add()">
          <mat-icon>add</mat-icon>
          {{ 'catalog.admin.skills.add' | translate }}
        </button>
      </div>
    </div>

    @if (store.skillsError$ | async; as error) {
      <p class="config-notice" role="alert">
        <mat-icon aria-hidden="true">error_outline</mat-icon>
        <span>{{ 'catalog.admin.skills.loadFailed' | translate: { error: error } }}</span>
      </p>
    }

    @if (outcomes.length > 0) {
      <div class="import-outcomes" role="status">
        <ul>
          @for (outcome of outcomes; track $index) {
            <li [class.is-error]="!outcome.ok">
              <mat-icon aria-hidden="true">{{ outcome.ok ? 'check_circle' : 'error_outline' }}</mat-icon>
              <span><span class="mono">{{ outcome.file }}</span>: {{ outcome.text }}</span>
            </li>
          }
        </ul>
        <button mat-icon-button type="button" (click)="outcomes = []"
                [matTooltip]="'catalog.common.close' | translate" [attr.aria-label]="'catalog.common.close' | translate">
          <mat-icon>close</mat-icon>
        </button>
      </div>
    }

    @if (store.skills$ | async; as skills) {
      <div class="item-list">
        @for (skill of skills; track skill.id) {
          <div class="item-card" [class.is-disabled]="!skill.enabled">
            <div class="item-main">
              <div class="item-title-row">
                <span class="item-title mono">{{ skill.name }}</span>
                @if (!skill.enabled) {
                  <span class="state-tag">{{ 'catalog.admin.disabled' | translate }}</span>
                }
              </div>
              <div class="item-meta">
                <span>{{ 'catalog.admin.skills.length' | translate: { count: (skill.content.length | number) } }}</span>
              </div>
              <p class="item-description">{{ skill.description }}</p>
              <p class="item-usage">
                <mat-icon aria-hidden="true">smart_toy</mat-icon>
                @if (agentNames(skill); as names) {
                  {{ 'catalog.admin.skills.usedBy' | translate: { names: names } }}
                } @else {
                  {{ 'catalog.admin.skills.unused' | translate }}
                }
              </p>
            </div>

            <div class="item-controls">
              <div class="item-toggles">
                <mat-slide-toggle [checked]="skill.enabled"
                                  [aria-label]="('catalog.admin.fields.enabled' | translate) + ': ' + skill.name"
                                  (change)="setEnabled(skill, $event)">
                  {{ 'catalog.admin.fields.enabled' | translate }}
                </mat-slide-toggle>
              </div>
              <div class="item-actions">
                <button mat-icon-button type="button" (click)="export(skill)"
                        [matTooltip]="'catalog.admin.skills.export' | translate"
                        [attr.aria-label]="('catalog.admin.skills.export' | translate) + ': ' + skill.name">
                  <mat-icon>download</mat-icon>
                </button>
                <button mat-icon-button type="button" (click)="edit(skill)"
                        [matTooltip]="'catalog.common.edit' | translate"
                        [attr.aria-label]="('catalog.common.edit' | translate) + ': ' + skill.name">
                  <mat-icon>edit</mat-icon>
                </button>
                <button mat-icon-button type="button" class="danger-action" (click)="remove(skill)"
                        [matTooltip]="'catalog.common.delete' | translate"
                        [attr.aria-label]="('catalog.common.delete' | translate) + ': ' + skill.name">
                  <mat-icon>delete_outline</mat-icon>
                </button>
              </div>
            </div>
          </div>
        } @empty {
          @if (!(store.skillsError$ | async)) {
            <div class="empty-state">
              <mat-icon aria-hidden="true">school</mat-icon>
              <p>{{ 'catalog.admin.skills.empty' | translate }}</p>
            </div>
          }
        }
      </div>
    }
  `,
  styleUrls: ['./catalog-admin-list.scss', '../mcp/mcp-list.scss'],
  styles: [`
    .hidden-input { display: none; }

    .section-actions mat-spinner { display: inline-block; margin-right: 8px; }

    .import-outcomes {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      margin: 0 0 12px;
      padding: 8px 8px 8px 12px;
      border: 1px solid var(--theme-border);
      border-radius: 12px;

      ul { flex: 1; margin: 0; padding: 0; list-style: none; }

      li {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        padding: 4px 0;
        font-size: 0.875rem;
        overflow-wrap: anywhere;

        mat-icon { flex-shrink: 0; font-size: 18px; width: 18px; height: 18px; color: var(--theme-text-secondary); }

        &.is-error mat-icon { color: var(--theme-tier-untrusted); }
      }
    }
  `]
})
export class SkillsTabComponent {
  importing = false;
  outcomes: ImportOutcome[] = [];

  constructor(
    public store: CatalogAdminStore,
    private dialogs: CatalogAdminDialogs,
    private translate: TranslateService
  ) {}

  /** The agents that have the skill, or null when none has. */
  agentNames(skill: ISkillOut): string | null {
    return skill.agents.length > 0 ? skill.agents.map(agent => agent.name).join(', ') : null;
  }

  async add(): Promise<void> {
    const saved = await this.dialogs.open<SkillDialogComponent, SkillDialogData, ISkillOut>(
      SkillDialogComponent, { skill: null }
    );
    if (saved) this.dialogs.notify('catalog.admin.skills.saved', { name: saved.name });
  }

  async edit(skill: ISkillOut): Promise<void> {
    const saved = await this.dialogs.open<SkillDialogComponent, SkillDialogData, ISkillOut>(
      SkillDialogComponent, { skill }
    );
    if (saved) this.dialogs.notify('catalog.admin.skills.saved', { name: saved.name });
  }

  async setEnabled(skill: ISkillOut, change: MatSlideToggleChange): Promise<void> {
    try {
      await this.store.setSkillEnabled(skill, change.checked);
    } catch (error) {
      this.dialogs.notifyError(error);
      change.source.checked = !change.checked;  // Flip the switch back
    }
  }

  async export(skill: ISkillOut): Promise<void> {
    try {
      const text = await this.store.exportSkill(skill.id);
      const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `${skill.name}.md`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      this.dialogs.notifyError(error);
    }
  }

  async remove(skill: ISkillOut): Promise<void> {
    const names = this.agentNames(skill);
    const confirmed = await this.dialogs.confirm({
      title: this.dialogs.t('catalog.admin.skills.deleteTitle', { name: skill.name }),
      message: names
        ? this.dialogs.t('catalog.admin.skills.deleteMessage', { names })
        : this.dialogs.t('catalog.admin.skills.deleteMessageUnused'),
      confirmLabel: this.dialogs.t('catalog.common.delete'),
      danger: true
    });
    if (!confirmed) return;
    try {
      await this.store.deleteSkill(skill.id);
      this.dialogs.notify('catalog.admin.deleted', { name: skill.name });
    } catch (error) {
      this.dialogs.notifyError(error);
    }
  }

  /** Imports the picked SKILL.md files one by one; a name that is taken is replaced only when the admin agrees. */
  async onFilesSelected(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    input.value = '';  // Picking the same files again still triggers a change
    if (files.length === 0) return;

    this.importing = true;
    this.outcomes = [];
    try {
      for (const file of files) {
        this.outcomes = [...this.outcomes, await this.importFile(file)];
      }
      await this.store.reloadSkills();
    } finally {
      this.importing = false;
    }
  }

  private async importFile(file: File): Promise<ImportOutcome> {
    let text: string;
    try {
      text = await file.text();
    } catch (error) {
      return { file: file.name, ok: false, text: describeHttpError(error, this.translate) };
    }
    try {
      return this.outcome(file, await this.store.importSkill(text, false));
    } catch (error) {
      if (!(error instanceof HttpErrorResponse && error.status === 409)) {
        return { file: file.name, ok: false, text: describeHttpError(error, this.translate) };
      }
      const replace = await this.dialogs.confirm({
        title: this.dialogs.t('catalog.admin.skills.replaceTitle'),
        message: this.dialogs.t('catalog.admin.skills.replaceMessage', {
          error: describeHttpError(error, this.translate), file: file.name
        }),
        confirmLabel: this.dialogs.t('catalog.admin.skills.replace')
      });
      if (!replace) return { file: file.name, ok: false, text: this.dialogs.t('catalog.admin.skills.notReplaced') };
      try {
        return this.outcome(file, await this.store.importSkill(text, true));
      } catch (retryError) {
        return { file: file.name, ok: false, text: describeHttpError(retryError, this.translate) };
      }
    }
  }

  private outcome(file: File, result: ISkillImportResult): ImportOutcome {
    let text = this.dialogs.t(result.created ? 'catalog.admin.skills.imported' : 'catalog.admin.skills.replaced',
                              { name: result.skill.name });
    if (result.ignored.length > 0) {
      text += ' ' + this.dialogs.t('catalog.admin.skills.ignoredKeys', { keys: result.ignored.join(', ') });
    }
    return { file: file.name, ok: true, text };
  }
}
