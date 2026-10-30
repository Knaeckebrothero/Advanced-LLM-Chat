import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';
import { PrivacyTier } from '../../data/models/catalog.model';

const TIER_ICONS: Record<PrivacyTier, string> = {
  local: 'home',
  eu: 'flag',
  trusted: 'verified_user',
  untrusted: 'report',
};

/**
 * The privacy tier of a model or provider as a small badge (icon and label, so it doesn't
 * rely on color alone). `compact` shows the icon only, with the label as tooltip.
 */
@Component({
  selector: 'app-privacy-badge',
  standalone: true,
  imports: [MatIconModule, MatTooltipModule, TranslateModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="privacy-badge"
          [attr.data-tier]="tier"
          [class.compact]="compact"
          [matTooltip]="('catalog.tierHint.' + tier) | translate"
          [matTooltipDisabled]="!tooltip"
          [attr.aria-label]="('catalog.tierLabel' | translate) + ': ' + (('catalog.tier.' + tier) | translate)"
          role="img">
      <mat-icon aria-hidden="true">{{ icon }}</mat-icon>
      @if (!compact) {
        <span class="label" aria-hidden="true">{{ ('catalog.tier.' + tier) | translate }}</span>
      }
    </span>
  `,
  styles: [`
    :host { display: inline-flex; vertical-align: middle; }

    .privacy-badge {
      display: inline-flex;
      align-items: center;
      gap: 3px;
      padding: 1px 7px 1px 5px;
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 600;
      line-height: 1.5;
      letter-spacing: 0.02em;
      white-space: nowrap;
      border: 1px solid transparent;

      mat-icon {
        font-size: 13px;
        width: 13px;
        height: 13px;
      }

      &.compact {
        padding: 2px;
      }
    }

    [data-tier='local'] { color: var(--theme-tier-local); background: var(--theme-tier-local-bg); }
    [data-tier='eu'] { color: var(--theme-tier-eu); background: var(--theme-tier-eu-bg); }
    [data-tier='trusted'] { color: var(--theme-tier-trusted); background: var(--theme-tier-trusted-bg); }
    [data-tier='untrusted'] {
      color: var(--theme-tier-untrusted);
      background: var(--theme-tier-untrusted-bg);
      border-color: var(--theme-tier-untrusted);
    }
  `]
})
export class PrivacyBadgeComponent {
  @Input({ required: true }) tier!: PrivacyTier;
  @Input() compact = false;
  /** Off inside elements that have their own tooltip. */
  @Input() tooltip = true;

  get icon(): string {
    return TIER_ICONS[this.tier] ?? 'help';
  }
}
