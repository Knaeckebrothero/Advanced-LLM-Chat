import { Component } from '@angular/core';
import { AsyncPipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';
import { IProviderOut } from '../data/models/catalog.model';
import { PrivacyBadgeComponent } from '../components/catalog/privacy-badge.component';
import { CatalogAdminStore } from './catalog-admin.store';
import { CatalogAdminDialogs } from './catalog-admin-dialogs';
import { ProviderDialogComponent, ProviderDialogData } from './provider-dialog.component';
import {
  FetchModelsDialogComponent,
  FetchModelsDialogData,
  FetchModelsDialogResult
} from './fetch-models-dialog.component';

/** Providers (API accounts): list, add, edit, delete, fetch their models. */
@Component({
  selector: 'app-providers-tab',
  standalone: true,
  imports: [AsyncPipe, MatButtonModule, MatIconModule, MatTooltipModule, TranslateModule, PrivacyBadgeComponent],
  template: `
    <div class="tab-toolbar">
      <p class="tab-intro">{{ 'catalog.admin.providers.intro' | translate }}</p>
      <div class="tab-toolbar-actions">
        <button mat-flat-button color="primary" type="button" (click)="add()">
          <mat-icon>add</mat-icon>
          {{ 'catalog.admin.providers.add' | translate }}
        </button>
      </div>
    </div>

    @if (store.providers$ | async; as providers) {
      <div class="item-list">
        @for (provider of providers; track provider.id) {
          <div class="item-card" [class.is-disabled]="!provider.enabled">
            <div class="item-main">
              <div class="item-title-row">
                <span class="item-title">{{ provider.name }}</span>
                <app-privacy-badge [tier]="provider.privacyTier"></app-privacy-badge>
                @if (!provider.enabled) {
                  <span class="state-tag">{{ 'catalog.admin.disabled' | translate }}</span>
                }
              </div>
              <div class="item-meta">
                <span>{{ ('catalog.kind.' + provider.kind) | translate }}</span>
                <span class="mono">{{ provider.baseUrl || ('catalog.admin.providers.sdkDefault' | translate) }}</span>
              </div>
              <div class="item-meta">
                <span>
                  <mat-icon aria-hidden="true">key</mat-icon>
                  @switch (provider.apiKeySource) {
                    @case ('stored') {
                      <span>{{ 'catalog.admin.providers.keyStored' | translate: { key: provider.apiKeyMasked || '…' } }}</span>
                    }
                    @case ('env') {
                      <span>{{ 'catalog.admin.providers.keyEnv' | translate: { env: provider.apiKeyEnv || '' } }}</span>
                    }
                    @default {
                      <span>{{ 'catalog.admin.providers.keyNone' | translate }}</span>
                    }
                  }
                </span>
                <span>{{ 'catalog.admin.providers.modelCount' | translate: { count: provider.modelCount } }}</span>
                <span>{{ provider.currency }}</span>
              </div>
              @if (provider.notes) {
                <p class="item-notes">{{ provider.notes }}</p>
              }
            </div>
            <div class="item-controls">
              <button mat-stroked-button type="button" (click)="fetchModels(provider)">
                <mat-icon>cloud_download</mat-icon>
                {{ 'catalog.admin.providers.fetchModels' | translate }}
              </button>
              <div class="item-actions">
                <button mat-icon-button type="button" (click)="edit(provider)"
                        [matTooltip]="'catalog.common.edit' | translate"
                        [attr.aria-label]="('catalog.common.edit' | translate) + ': ' + provider.name">
                  <mat-icon>edit</mat-icon>
                </button>
                <button mat-icon-button type="button" class="danger-action" (click)="remove(provider)"
                        [matTooltip]="'catalog.common.delete' | translate"
                        [attr.aria-label]="('catalog.common.delete' | translate) + ': ' + provider.name">
                  <mat-icon>delete_outline</mat-icon>
                </button>
              </div>
            </div>
          </div>
        } @empty {
          <div class="empty-state">
            <mat-icon aria-hidden="true">hub</mat-icon>
            <p>{{ 'catalog.admin.providers.empty' | translate }}</p>
          </div>
        }
      </div>
    }
  `,
  styleUrls: ['./catalog-admin-list.scss']
})
export class ProvidersTabComponent {
  constructor(
    public store: CatalogAdminStore,
    private dialogs: CatalogAdminDialogs
  ) {}

  async add(): Promise<void> {
    const saved = await this.dialogs.open<ProviderDialogComponent, ProviderDialogData, IProviderOut>(
      ProviderDialogComponent, { provider: null }
    );
    if (saved) {
      this.dialogs.notify('catalog.admin.providers.saved', { name: saved.name });
      // Offer the provider's models right away
      this.fetchModels(saved);
    }
  }

  async edit(provider: IProviderOut): Promise<void> {
    const saved = await this.dialogs.open<ProviderDialogComponent, ProviderDialogData, IProviderOut>(
      ProviderDialogComponent, { provider }
    );
    if (saved) this.dialogs.notify('catalog.admin.providers.saved', { name: saved.name });
  }

  async fetchModels(provider: IProviderOut): Promise<void> {
    const result = await this.dialogs.open<FetchModelsDialogComponent, FetchModelsDialogData, FetchModelsDialogResult>(
      FetchModelsDialogComponent, { provider }
    );
    if (result) {
      this.dialogs.notify('catalog.admin.fetch.addedCount', { count: result.added });
      if (result.errors.length > 0) this.dialogs.notifyError(new Error(result.errors.join('\n')));
    }
  }

  async remove(provider: IProviderOut): Promise<void> {
    const confirmed = await this.dialogs.confirm({
      title: this.dialogs.t('catalog.admin.providers.deleteTitle', { name: provider.name }),
      message: this.dialogs.t('catalog.admin.providers.deleteMessage', { count: provider.modelCount }),
      confirmLabel: this.dialogs.t('catalog.common.delete'),
      danger: true
    });
    if (!confirmed) return;
    try {
      await this.store.deleteProvider(provider.id);
      this.dialogs.notify('catalog.admin.deleted', { name: provider.name });
    } catch (error) {
      this.dialogs.notifyError(error);
    }
  }
}
