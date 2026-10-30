import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';
import { ReasoningMode } from '../../data/models/catalog.model';

/** Small icons for what a model can do: tools, image input, thinking. */
@Component({
  selector: 'app-model-capabilities',
  standalone: true,
  imports: [MatIconModule, MatTooltipModule, TranslateModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (supportsTools) {
      <mat-icon [matTooltip]="'catalog.capability.tools' | translate"
                [attr.aria-label]="'catalog.capability.tools' | translate" role="img">build</mat-icon>
    }
    @if (supportsVision) {
      <mat-icon [matTooltip]="'catalog.capability.vision' | translate"
                [attr.aria-label]="'catalog.capability.vision' | translate" role="img">image</mat-icon>
    }
    @if (reasoning && reasoning !== 'none') {
      <mat-icon [matTooltip]="(reasoning === 'always' ? 'catalog.capability.thinking' : 'catalog.capability.thinkingOptional') | translate"
                [attr.aria-label]="'catalog.capability.thinking' | translate" role="img">psychology</mat-icon>
    }
  `,
  styles: [`
    :host {
      display: inline-flex;
      align-items: center;
      gap: 2px;
      color: var(--theme-text-secondary);
      vertical-align: middle;
    }

    mat-icon {
      font-size: 15px;
      width: 15px;
      height: 15px;
    }
  `]
})
export class ModelCapabilitiesComponent {
  @Input() supportsTools = false;
  @Input() supportsVision = false;
  @Input() reasoning: ReasoningMode | null | undefined = 'none';
}
