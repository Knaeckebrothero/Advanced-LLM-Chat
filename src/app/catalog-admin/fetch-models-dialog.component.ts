import { Component, Inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { IFetchedModel, IProviderOut } from '../data/models/catalog.model';
import { CatalogAdminStore } from './catalog-admin.store';
import { describeHttpError } from './catalog-admin.utils';

export interface FetchModelsDialogData {
  provider: IProviderOut;
}

export interface FetchModelsDialogResult {
  added: number;
  errors: string[];
}

/**
 * The provider's own model list (its GET /models), to add models without typing their ids.
 * Models already in the catalog are marked and can't be picked again.
 */
@Component({
  selector: 'app-fetch-models-dialog',
  standalone: true,
  imports: [
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    TranslateModule
  ],
  template: `
    <h2 mat-dialog-title>{{ 'catalog.admin.fetch.title' | translate: { provider: data.provider.name } }}</h2>
    <mat-dialog-content class="catalog-dialog-content fetch-content">
      @if (loading) {
        <div class="fetch-state"><mat-spinner diameter="32"></mat-spinner></div>
      } @else if (loadError) {
        <p class="dialog-error" role="alert"><mat-icon aria-hidden="true">error_outline</mat-icon>{{ loadError }}</p>
      } @else {
        <mat-form-field appearance="outline" class="full-width" subscriptSizing="dynamic">
          <mat-label>{{ 'catalog.admin.fetch.filter' | translate }}</mat-label>
          <mat-icon matPrefix>search</mat-icon>
          <input matInput [(ngModel)]="filter" name="filter" autocomplete="off">
        </mat-form-field>
        <p class="fetch-summary">
          {{ 'catalog.admin.fetch.summary' | translate: { total: models.length, added: alreadyAddedCount } }}
        </p>
        <div class="fetch-list" role="list">
          @for (model of filteredModels; track model.id) {
            <div class="fetch-item" role="listitem" [class.is-added]="model.alreadyAdded">
              <mat-checkbox [checked]="model.alreadyAdded || selected.has(model.id)"
                            [disabled]="model.alreadyAdded"
                            (change)="toggle(model, $event.checked)">
                <span class="fetch-id">{{ model.id }}</span>
              </mat-checkbox>
              <span class="fetch-meta">
                @if (model.contextWindow) {
                  <span>{{ 'catalog.admin.fetch.context' | translate: { tokens: formatCount(model.contextWindow) } }}</span>
                }
                @if (model.ownedBy) {
                  <span>{{ model.ownedBy }}</span>
                }
                @if (model.alreadyAdded) {
                  <span class="added-tag">{{ 'catalog.admin.fetch.added' | translate }}</span>
                }
              </span>
            </div>
          } @empty {
            <p class="empty-hint">{{ 'catalog.admin.fetch.none' | translate }}</p>
          }
        </div>
      }
      @if (saveError) {
        <p class="dialog-error" role="alert"><mat-icon aria-hidden="true">error_outline</mat-icon>{{ saveError }}</p>
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" mat-dialog-close>{{ 'catalog.common.cancel' | translate }}</button>
      <button mat-flat-button color="primary" type="button"
              [disabled]="selected.size === 0 || saving"
              (click)="addSelected()">
        @if (saving) {
          <mat-spinner diameter="18"></mat-spinner>
        }
        {{ 'catalog.admin.fetch.addSelected' | translate: { count: selected.size } }}
      </button>
    </mat-dialog-actions>
  `,
  styleUrls: ['./catalog-dialog.scss'],
  styles: [`
    .fetch-content { min-height: 200px; }

    .fetch-state {
      display: flex;
      justify-content: center;
      padding: 48px 0;
    }

    .fetch-summary {
      margin: 8px 0;
      font-size: 0.8rem;
      color: var(--theme-text-secondary);
    }

    .fetch-list {
      display: flex;
      flex-direction: column;
      border: 1px solid var(--theme-border);
      border-radius: 10px;
      overflow: hidden;
    }

    .fetch-item {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 4px 12px;
      padding: 2px 12px 2px 4px;
      border-bottom: 1px solid var(--theme-border);

      &:last-child { border-bottom: none; }
      &.is-added { opacity: 0.7; }
    }

    .fetch-id {
      font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
      font-size: 0.85rem;
      overflow-wrap: anywhere;
    }

    .fetch-meta {
      display: flex;
      gap: 10px;
      font-size: 0.75rem;
      color: var(--theme-text-secondary);
    }

    .added-tag {
      padding: 0 8px;
      border-radius: 999px;
      background: var(--theme-active);
      color: var(--theme-text-accent);
      font-weight: 600;
    }
  `]
})
export class FetchModelsDialogComponent implements OnInit {
  models: IFetchedModel[] = [];
  selected = new Set<string>();
  filter = '';
  loading = true;
  saving = false;
  loadError: string | null = null;
  saveError: string | null = null;

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: FetchModelsDialogData,
    private dialogRef: MatDialogRef<FetchModelsDialogComponent, FetchModelsDialogResult>,
    private store: CatalogAdminStore,
    private translate: TranslateService
  ) {}

  async ngOnInit(): Promise<void> {
    try {
      const response = await this.store.fetchProviderModels(this.data.provider.id);
      this.models = [...(response?.models ?? [])].sort((a, b) => a.id.localeCompare(b.id));
    } catch (error) {
      this.loadError = describeHttpError(error, this.translate);
    } finally {
      this.loading = false;
    }
  }

  get filteredModels(): IFetchedModel[] {
    const term = this.filter.trim().toLowerCase();
    return term ? this.models.filter(m => m.id.toLowerCase().includes(term)) : this.models;
  }

  get alreadyAddedCount(): number {
    return this.models.filter(m => m.alreadyAdded).length;
  }

  toggle(model: IFetchedModel, checked: boolean): void {
    if (checked) this.selected.add(model.id);
    else this.selected.delete(model.id);
  }

  formatCount(value: number): string {
    return new Intl.NumberFormat(this.translate.currentLang || 'en').format(value);
  }

  async addSelected(): Promise<void> {
    const picked = this.models.filter(m => this.selected.has(m.id));
    if (picked.length === 0) return;
    this.saving = true;
    this.saveError = null;
    try {
      const result = await this.store.addFetchedModels(this.data.provider, picked);
      if (result.errors.length > 0 && result.added === 0) {
        this.saveError = result.errors.join('\n');
        return;
      }
      this.dialogRef.close(result);
    } catch (error) {
      this.saveError = describeHttpError(error, this.translate);
    } finally {
      this.saving = false;
    }
  }
}
