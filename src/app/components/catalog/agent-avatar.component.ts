import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

/**
 * An agent's image, filling a circle or a rounded square of `size` pixels (cover: a picture that
 * isn't square shows its middle), or an icon where the agent has none.
 */
@Component({
  selector: 'app-agent-avatar',
  standalone: true,
  imports: [MatIconModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    'aria-hidden': 'true',
    '[class.is-round]': 'shape === "round"',
    '[class.has-image]': '!!src',
    '[style.width.px]': 'size',
    '[style.height.px]': 'size',
    '[style.--agent-avatar-icon.px]': 'iconSize',
  },
  template: `
    @if (src) {
      <img [src]="src" alt="" decoding="async">
    } @else {
      <mat-icon>{{ icon }}</mat-icon>
    }
  `,
  styles: [`
    :host {
      flex-shrink: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      border-radius: 25%;
      background: var(--theme-active);
      color: var(--theme-text-accent);
    }

    :host(.is-round) {
      border-radius: 50%;
    }

    :host(.has-image) {
      background: transparent;
    }

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }

    /* :host first, so this outweighs the menus' icon rules (a margin, their own size) */
    :host .mat-icon {
      margin: 0;
      font-size: var(--agent-avatar-icon);
      width: var(--agent-avatar-icon);
      height: var(--agent-avatar-icon);
      line-height: var(--agent-avatar-icon);
    }
  `]
})
export class AgentAvatarComponent {
  /** The image (a data URL), or null for the icon. */
  @Input() src: string | null | undefined = null;
  @Input() size = 40;
  @Input() shape: 'rounded' | 'round' = 'rounded';
  @Input() icon = 'smart_toy';

  get iconSize(): number {
    return Math.round(this.size * 0.55);
  }
}
