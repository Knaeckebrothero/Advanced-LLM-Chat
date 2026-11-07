import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { CHARS_PER_TOKEN, IContextSize } from '../../../data/models/conversation.model';

const RADIUS = 8;

/**
 * The input token indicator of manual editing: about how many tokens the next answer
 * sends (the backend's count, plus the draft in the composer) against the model's
 * context window. The ring turns amber when messages are left out or the next answer
 * first summarizes the oldest ones; the tooltip breaks the count down.
 */
@Component({
  selector: 'app-context-meter',
  standalone: true,
  imports: [CommonModule, MatTooltipModule, TranslateModule],
  template: `
    <span class="context-meter"
          [class.warn]="warn"
          role="img"
          tabindex="0"
          [attr.aria-label]="details"
          [matTooltip]="details"
          matTooltipClass="multiline-tooltip context-meter-tooltip">
      <svg class="ring" viewBox="0 0 20 20" aria-hidden="true">
        <circle class="track" cx="10" cy="10" [attr.r]="radius"></circle>
        <circle class="fill" cx="10" cy="10" [attr.r]="radius"
                [attr.stroke-dasharray]="circumference"
                [attr.stroke-dashoffset]="dashOffset"></circle>
      </svg>
      <span class="count" aria-hidden="true">{{ short(total) }}<span class="window"> / {{ short(size.contextWindow) }}</span></span>
    </span>
  `,
  styles: [`
    .context-meter {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      height: 32px;
      padding: 0 8px;
      border-radius: 10px;
      font-size: 12px;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
      color: var(--theme-text-secondary);
      cursor: default;
      outline: none;

      &:focus-visible {
        box-shadow: 0 0 0 2px var(--theme-primary);
      }
    }

    .ring {
      width: 18px;
      height: 18px;
      flex-shrink: 0;
      transform: rotate(-90deg);

      circle {
        fill: none;
        stroke-width: 3;
      }

      .track {
        stroke: var(--theme-border);
      }

      .fill {
        stroke: var(--theme-primary);
        stroke-linecap: round;
        transition: stroke-dashoffset 0.3s ease;
      }
    }

    .warn .ring .fill {
      stroke: #f59e0b;
    }

    // Phones: the count alone, the window is in the tooltip
    @media (max-width: 480px) {
      .context-meter {
        padding: 0 4px;
      }

      .window {
        display: none;
      }
    }
  `]
})
export class ContextMeterComponent {
  /** The backend's count for the conversation as stored. */
  @Input({ required: true }) size!: IContextSize;

  /** The text in the composer, which the next answer sends too once it is sent. */
  @Input() draft = '';

  readonly radius = RADIUS;
  readonly circumference = 2 * Math.PI * RADIUS;

  constructor(private translate: TranslateService) {}

  get draftTokens(): number {
    const text = this.draft.trim();
    return text ? Math.ceil(text.length / CHARS_PER_TOKEN) : 0;
  }

  get total(): number {
    return this.size.inputTokens + this.draftTokens;
  }

  get dashOffset(): number {
    return this.circumference * (1 - Math.min(this.total / this.size.contextWindow, 1));
  }

  get warn(): boolean {
    return this.size.summarizes || this.size.leftOutCount > 0;
  }

  /** The tooltip and the label for screen readers: the count, its parts and what happens next. */
  get details(): string {
    const t = (key: string, params?: object) => this.translate.instant(`composer.context.${key}`, params);
    const share = this.total / this.size.contextWindow * 100;
    const percent = share > 0 && share < 1 ? '<1' : String(Math.round(share));
    const lines = [
      t('total', { count: this.full(this.total), window: this.full(this.size.contextWindow), percent }),
      t('parts', {
        system: this.full(this.size.systemTokens),
        tools: this.full(this.size.toolTokens),
        history: this.full(this.size.historyTokens),
        messages: this.size.messageCount
      })
    ];
    if (this.draftTokens) lines.push(t('draft', { count: this.full(this.draftTokens) }));
    if (this.size.leftOutCount) lines.push(t('leftOut', { count: this.size.leftOutCount }));
    if (this.size.summarizes) lines.push(t('summarizes'));
    lines.push(t('estimate'));
    return lines.join('\n');
  }

  /** 950, 1.2k, 128k (with the language's decimal sign). */
  short(value: number): string {
    if (value < 1000) return String(value);
    const thousands = value / 1000;
    return new Intl.NumberFormat(this.locale, { maximumFractionDigits: thousands < 10 ? 1 : 0 }).format(thousands) + 'k';
  }

  private full(value: number): string {
    return new Intl.NumberFormat(this.locale).format(value);
  }

  private get locale(): string {
    return this.translate.currentLang || 'en';
  }
}
