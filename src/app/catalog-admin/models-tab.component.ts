import { Component } from '@angular/core';
import { AsyncPipe } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSlideToggleChange, MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { combineLatest, map, Observable } from 'rxjs';
import { IModelOut, IModelTestResult, IProviderOut } from '../data/models/catalog.model';
import { PrivacyBadgeComponent } from '../components/catalog/privacy-badge.component';
import { ModelCapabilitiesComponent } from '../components/catalog/model-capabilities.component';
import { CatalogAdminStore } from './catalog-admin.store';
import { CatalogAdminDialogs } from './catalog-admin-dialogs';
import { ModelDialogComponent, ModelDialogData } from './model-dialog.component';
import { describeHttpError } from './catalog-admin.utils';

interface ProviderModels {
  provider: IProviderOut | null;  // null: the provider is gone (shouldn't happen, models are deleted with it)
  name: string;
  models: IModelOut[];
}

interface TestState {
  running: boolean;
  result?: IModelTestResult;
}

/** Models grouped by provider, with quick switches, a smoke test and the edit dialog. */
@Component({
  selector: 'app-models-tab',
  standalone: true,
  imports: [
    AsyncPipe,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSlideToggleModule,
    MatTooltipModule,
    TranslateModule,
    PrivacyBadgeComponent,
    ModelCapabilitiesComponent
  ],
  template: `
    <div class="tab-toolbar">
      <p class="tab-intro">{{ 'catalog.admin.models.intro' | translate }}</p>
      <div class="tab-toolbar-actions">
        <button mat-flat-button color="primary" type="button" (click)="add()"
                [disabled]="store.providers.length === 0">
          <mat-icon>add</mat-icon>
          {{ 'catalog.admin.models.add' | translate }}
        </button>
      </div>
    </div>

    @if (groups$ | async; as groups) {
      @for (group of groups; track group.name) {
        <section class="group">
          <div class="group-header">
            <h3 class="group-title">{{ group.name }}</h3>
            @if (group.provider) {
              <app-privacy-badge [tier]="group.provider.privacyTier" [compact]="true"></app-privacy-badge>
              @if (!group.provider.enabled) {
                <span class="state-tag">{{ 'catalog.admin.providerDisabled' | translate }}</span>
              }
            }
            <span class="group-count">{{ group.models.length }}</span>
            <span class="group-spacer"></span>
            @if (group.provider) {
              <button mat-icon-button type="button" (click)="add(group.provider)"
                      [matTooltip]="'catalog.admin.models.addTo' | translate: { provider: group.name }"
                      [attr.aria-label]="'catalog.admin.models.addTo' | translate: { provider: group.name }">
                <mat-icon>add</mat-icon>
              </button>
            }
          </div>

          <div class="item-list">
            @for (model of group.models; track model.id) {
              <div class="item-card" [class.is-disabled]="!model.enabled">
                <div class="item-main">
                  <div class="item-title-row">
                    <span class="item-title">{{ model.displayName }}</span>
                    <app-privacy-badge [tier]="model.effectivePrivacyTier"></app-privacy-badge>
                    <app-model-capabilities [supportsTools]="model.supportsTools"
                                            [supportsVision]="model.supportsVision"
                                            [reasoning]="model.reasoning"></app-model-capabilities>
                    @if (model.isAuxiliary) {
                      <span class="state-tag state-tag--accent"
                            [matTooltip]="'catalog.admin.models.auxiliaryHint' | translate">
                        {{ 'catalog.admin.models.auxiliary' | translate }}
                      </span>
                    }
                  </div>
                  <div class="item-meta">
                    <span class="mono">{{ model.modelId }}</span>
                    @if (model.contextWindow) {
                      <span>{{ 'catalog.admin.models.context' | translate: { tokens: formatCount(model.contextWindow) } }}</span>
                    }
                    @if (priceText(model); as price) {
                      <span>{{ price }}</span>
                    }
                    <span>#{{ model.sortOrder }}</span>
                  </div>
                  @if (model.description) {
                    <p class="item-description">{{ model.description }}</p>
                  }
                </div>

                <div class="item-controls">
                  <div class="item-toggles">
                    <mat-slide-toggle [checked]="model.enabled"
                                      (change)="setFlag(model, 'enabled', $event)">
                      {{ 'catalog.admin.fields.enabled' | translate }}
                    </mat-slide-toggle>
                    <mat-slide-toggle [checked]="model.availableToGuests"
                                      (change)="setFlag(model, 'availableToGuests', $event)">
                      {{ 'catalog.admin.fields.guests' | translate }}
                    </mat-slide-toggle>
                  </div>
                  <div class="item-actions">
                    <button mat-icon-button type="button" (click)="test(model)"
                            [disabled]="tests[model.id]?.running"
                            [matTooltip]="'catalog.admin.models.test' | translate"
                            [attr.aria-label]="('catalog.admin.models.test' | translate) + ': ' + model.displayName">
                      @if (tests[model.id]?.running) {
                        <mat-spinner diameter="18"></mat-spinner>
                      } @else {
                        <mat-icon>play_circle</mat-icon>
                      }
                    </button>
                    <button mat-icon-button type="button" (click)="edit(model)"
                            [matTooltip]="'catalog.common.edit' | translate"
                            [attr.aria-label]="('catalog.common.edit' | translate) + ': ' + model.displayName">
                      <mat-icon>edit</mat-icon>
                    </button>
                    <button mat-icon-button type="button" class="danger-action" (click)="remove(model)"
                            [matTooltip]="'catalog.common.delete' | translate"
                            [attr.aria-label]="('catalog.common.delete' | translate) + ': ' + model.displayName">
                      <mat-icon>delete_outline</mat-icon>
                    </button>
                  </div>
                </div>

                @if (tests[model.id]?.result; as result) {
                  <div class="test-result" role="status"
                       [class.test-result--ok]="result.ok"
                       [class.test-result--failed]="!result.ok">
                    <mat-icon aria-hidden="true">{{ result.ok ? 'check_circle' : 'error_outline' }}</mat-icon>
                    <span>
                      {{ (result.ok ? 'catalog.admin.models.testOk' : 'catalog.admin.models.testFailed') | translate: { ms: formatCount(result.latencyMs) } }}
                      @if (result.reply) {
                        <span class="test-reply">“{{ result.reply }}”</span>
                      }
                      @if (result.error) {
                        <span>{{ result.error }}</span>
                      }
                    </span>
                  </div>
                }
              </div>
            }
          </div>
        </section>
      } @empty {
        <div class="empty-state">
          <mat-icon aria-hidden="true">smart_toy</mat-icon>
          <p>{{ (store.providers.length === 0 ? 'catalog.admin.models.emptyNoProviders' : 'catalog.admin.models.empty') | translate }}</p>
        </div>
      }
    }
  `,
  styleUrls: ['./catalog-admin-list.scss']
})
export class ModelsTabComponent {
  groups$: Observable<ProviderModels[]>;
  tests: Record<number, TestState | undefined> = {};

  constructor(
    public store: CatalogAdminStore,
    private dialogs: CatalogAdminDialogs,
    private translate: TranslateService
  ) {
    this.groups$ = combineLatest([this.store.providers$, this.store.models$]).pipe(
      map(([providers, models]) => {
        const sorted = [...models].sort((a, b) => a.sortOrder - b.sortOrder || a.displayName.localeCompare(b.displayName));
        const groups: ProviderModels[] = providers.map(provider => ({
          provider,
          name: provider.name,
          models: sorted.filter(m => m.providerId === provider.id)
        }));
        const known = new Set(providers.map(p => p.id));
        const orphans = sorted.filter(m => !known.has(m.providerId));
        if (orphans.length > 0) {
          groups.push({ provider: null, name: orphans[0].providerName, models: orphans });
        }
        return groups.filter(g => g.models.length > 0 || g.provider !== null);
      })
    );
  }

  formatCount(value: number): string {
    return new Intl.NumberFormat(this.translate.currentLang || 'en').format(value);
  }

  priceText(model: IModelOut): string | null {
    if (model.inputPricePerMtok == null && model.outputPricePerMtok == null) return null;
    const format = (value: number | null | undefined) => {
      if (value == null) return '–';
      try {
        return new Intl.NumberFormat(this.translate.currentLang || 'en', {
          style: 'currency', currency: model.currency, maximumFractionDigits: 3
        }).format(value);
      } catch {
        return `${value} ${model.currency}`;
      }
    };
    return this.translate.instant('catalog.admin.models.price', {
      input: format(model.inputPricePerMtok),
      output: format(model.outputPricePerMtok)
    });
  }

  async add(provider?: IProviderOut): Promise<void> {
    const saved = await this.dialogs.open<ModelDialogComponent, ModelDialogData, IModelOut>(
      ModelDialogComponent, { model: null, providers: this.store.providers, providerId: provider?.id }
    );
    if (saved) this.dialogs.notify('catalog.admin.models.saved', { name: saved.displayName });
  }

  async edit(model: IModelOut): Promise<void> {
    const saved = await this.dialogs.open<ModelDialogComponent, ModelDialogData, IModelOut>(
      ModelDialogComponent, { model, providers: this.store.providers }
    );
    if (saved) this.dialogs.notify('catalog.admin.models.saved', { name: saved.displayName });
  }

  async setFlag(model: IModelOut, flag: 'enabled' | 'availableToGuests', change: MatSlideToggleChange): Promise<void> {
    try {
      await this.store.updateModelFlags(model, { [flag]: change.checked });
    } catch (error) {
      this.dialogs.notifyError(error);
      change.source.checked = !change.checked;  // Flip the switch back
    }
  }

  async test(model: IModelOut): Promise<void> {
    this.tests[model.id] = { running: true };
    try {
      const result = await this.store.testModel(model.id);
      this.tests[model.id] = { running: false, result };
    } catch (error) {
      this.tests[model.id] = {
        running: false,
        result: { ok: false, latencyMs: 0, error: describeHttpError(error, this.translate) }
      };
    }
  }

  async remove(model: IModelOut): Promise<void> {
    const confirmed = await this.dialogs.confirm({
      title: this.dialogs.t('catalog.admin.models.deleteTitle', { name: model.displayName }),
      message: this.dialogs.t('catalog.admin.models.deleteMessage'),
      confirmLabel: this.dialogs.t('catalog.common.delete'),
      danger: true
    });
    if (!confirmed) return;
    try {
      await this.store.deleteModel(model.id);
      this.dialogs.notify('catalog.admin.deleted', { name: model.displayName });
    } catch (error) {
      this.dialogs.notifyError(error);
    }
  }
}
