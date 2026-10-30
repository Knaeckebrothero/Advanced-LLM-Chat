import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  OnChanges,
  Output,
  ViewEncapsulation
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { IPublicModel } from '../../data/models/catalog.model';
import { CatalogService, ModelGroup } from '../../services/catalog.service';
import { PrivacyBadgeComponent } from './privacy-badge.component';
import { ModelCapabilitiesComponent } from './model-capabilities.component';

/**
 * A model dropdown: a trigger button and a menu of models grouped by provider, each with its
 * privacy badge and capability icons.
 *
 * - `variant="chip"`: compact trigger for the chat composer
 * - `variant="field"`: full-width trigger for forms (settings)
 * - `variant="icon"`: an icon button (`icon`, labelled by `label`), e.g. to regenerate with another model
 *
 * With `automaticLabel` set, the menu starts with an option for `null` (e.g. "Automatic").
 */
@Component({
  selector: 'app-model-select',
  standalone: true,
  imports: [
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatTooltipModule,
    TranslateModule,
    PrivacyBadgeComponent,
    ModelCapabilitiesComponent
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  // The menu panel lives in the overlay container, outside this component's view
  encapsulation: ViewEncapsulation.None,
  template: `
    @if (variant === 'icon') {
      <button mat-icon-button type="button"
              class="model-select-icon-trigger"
              [matMenuTriggerFor]="modelMenu"
              [disabled]="disabled"
              [matTooltip]="label ?? ''"
              [attr.aria-label]="label">
        <mat-icon>{{ icon }}</mat-icon>
      </button>
    } @else {
      <button type="button"
              class="model-select-trigger"
              [class.model-select-trigger--chip]="variant === 'chip'"
              [class.model-select-trigger--field]="variant === 'field'"
              [matMenuTriggerFor]="modelMenu"
              [disabled]="disabled"
              [matTooltip]="variant === 'chip' ? triggerTooltip : ''"
              matTooltipClass="multiline-tooltip"
              [attr.aria-label]="('catalog.picker.chooseModel' | translate) + ': ' + (selectedModel?.displayName ?? automaticLabel ?? '')">
        @if (selectedModel) {
          <app-privacy-badge [tier]="selectedModel.privacyTier" [compact]="variant === 'chip'"
                             [tooltip]="false"></app-privacy-badge>
          <span class="model-select-name">{{ selectedModel.displayName }}</span>
          @if (variant === 'field') {
            <app-model-capabilities [supportsTools]="selectedModel.supportsTools"
                                    [supportsVision]="selectedModel.supportsVision"
                                    [reasoning]="selectedModel.reasoning"></app-model-capabilities>
          }
        } @else {
          <mat-icon class="model-select-icon" aria-hidden="true">auto_awesome</mat-icon>
          <span class="model-select-name">{{ automaticLabel ?? ('catalog.picker.model' | translate) }}</span>
        }
        <mat-icon class="model-select-arrow" aria-hidden="true">arrow_drop_down</mat-icon>
      </button>
    }

    <mat-menu #modelMenu="matMenu" class="model-select-panel" xPosition="after"
              [yPosition]="variant === 'chip' ? 'above' : 'below'">
      @if (label && variant === 'icon') {
        <div class="model-select-group model-select-heading" role="presentation">{{ label }}</div>
      }
      @if (automaticLabel) {
        <button mat-menu-item type="button" role="menuitemradio"
                [attr.aria-checked]="selectedId === null"
                [class.is-selected]="selectedId === null"
                (click)="select(null)">
          <span class="model-option">
            <span class="model-option-main">
              <span class="model-option-name">{{ automaticLabel }}</span>
              @if (selectedId === null) {
                <mat-icon class="model-option-check" aria-hidden="true">check</mat-icon>
              }
            </span>
            @if (automaticHint) {
              <span class="model-option-description">{{ automaticHint }}</span>
            }
          </span>
        </button>
      }
      @for (group of groups; track group.providerName) {
        <div class="model-select-group" role="presentation">{{ group.providerName }}</div>
        @for (model of group.models; track model.id) {
          <button mat-menu-item type="button" role="menuitemradio"
                  [attr.aria-checked]="model.id === selectedId"
                  [class.is-selected]="model.id === selectedId"
                  (click)="select(model.id)">
            <span class="model-option">
              <span class="model-option-main">
                <span class="model-option-name">{{ model.displayName }}</span>
                <app-privacy-badge [tier]="model.privacyTier"></app-privacy-badge>
                <app-model-capabilities [supportsTools]="model.supportsTools"
                                        [supportsVision]="model.supportsVision"
                                        [reasoning]="model.reasoning"></app-model-capabilities>
                @if (model.id === selectedId) {
                  <mat-icon class="model-option-check" aria-hidden="true">check</mat-icon>
                }
              </span>
              @if (model.description) {
                <span class="model-option-description">{{ model.description }}</span>
              }
            </span>
          </button>
        }
      }
    </mat-menu>
  `,
  styleUrls: ['./model-select.component.scss']
})
export class ModelSelectComponent implements OnChanges {
  @Input() models: IPublicModel[] = [];
  /** The picked model id; null = automatic (only meaningful with automaticLabel). */
  @Input() selectedId: number | null = null;
  /** The model shown on the trigger; defaults to the picked one. */
  @Input() displayedModel: IPublicModel | null = null;
  @Input() variant: 'chip' | 'field' | 'icon' = 'chip';
  @Input() icon = 'swap_horiz';
  @Input() label: string | null = null;
  @Input() automaticLabel: string | null = null;
  @Input() automaticHint: string | null = null;
  @Input() disabled = false;
  @Output() selectedChange = new EventEmitter<number | null>();

  groups: ModelGroup[] = [];

  constructor(private translate: TranslateService) {}

  ngOnChanges(): void {
    this.groups = CatalogService.groupByProvider(this.models);
  }

  get selectedModel(): IPublicModel | null {
    return this.displayedModel ?? this.models.find(m => m.id === this.selectedId) ?? null;
  }

  /** Model and privacy tier for the chip's tooltip. */
  get triggerTooltip(): string {
    const model = this.selectedModel;
    if (!model) return this.automaticLabel ?? '';
    return `${this.translate.instant('catalog.picker.model')}: ${model.displayName} · ${model.providerName}\n` +
      this.translate.instant('catalog.tierHint.' + model.privacyTier);
  }

  select(id: number | null): void {
    // The icon variant is an action ("regenerate with"), so picking the current model counts too
    if (id !== this.selectedId || this.variant === 'icon') {
      this.selectedChange.emit(id);
    }
  }
}
