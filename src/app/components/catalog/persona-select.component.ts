import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  Output,
  ViewEncapsulation
} from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { TranslateModule } from '@ngx-translate/core';
import { IPublicPersona } from '../../data/models/catalog.model';

/**
 * An agent dropdown for forms (settings), styled like the model dropdown's field: a full-width
 * trigger and a menu that starts with "No agent", then the agents with their descriptions.
 */
@Component({
  selector: 'app-persona-select',
  standalone: true,
  imports: [MatIconModule, MatMenuModule, TranslateModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  // The menu panel lives in the overlay container; the styles are the model dropdown's
  encapsulation: ViewEncapsulation.None,
  template: `
    <button type="button"
            class="model-select-trigger model-select-trigger--field"
            [matMenuTriggerFor]="personaMenu"
            [attr.aria-label]="('catalog.picker.choosePersona' | translate) + ': ' + (selected?.name ?? ('catalog.picker.noPersona' | translate))">
      <mat-icon class="model-select-icon" aria-hidden="true">theater_comedy</mat-icon>
      <span class="model-select-name">{{ selected?.name ?? ('catalog.picker.noPersona' | translate) }}</span>
      <mat-icon class="model-select-arrow" aria-hidden="true">arrow_drop_down</mat-icon>
    </button>

    <mat-menu #personaMenu="matMenu" class="model-select-panel" xPosition="after" yPosition="below">
      <button mat-menu-item type="button" role="menuitemradio"
              [attr.aria-checked]="!selected"
              [class.is-selected]="!selected"
              (click)="select(null)">
        <span class="model-option">
          <span class="model-option-main">
            <span class="model-option-name">{{ 'catalog.picker.noPersona' | translate }}</span>
            <mat-icon class="model-option-check" [class.model-option-check--off]="!!selected"
                      aria-hidden="true">check</mat-icon>
          </span>
          @if (noneHint) {
            <span class="model-option-description">{{ noneHint }}</span>
          }
        </span>
      </button>
      @for (persona of personas; track persona.id) {
        <button mat-menu-item type="button" role="menuitemradio"
                [attr.aria-checked]="persona.id === selected?.id"
                [class.is-selected]="persona.id === selected?.id"
                (click)="select(persona.id)">
          <span class="model-option">
            <span class="model-option-main">
              <span class="model-option-name">{{ persona.name }}</span>
              <mat-icon class="model-option-check" [class.model-option-check--off]="persona.id !== selected?.id"
                        aria-hidden="true">check</mat-icon>
            </span>
            @if (persona.description) {
              <span class="model-option-description">{{ persona.description }}</span>
            }
          </span>
        </button>
      }
    </mat-menu>
  `,
  styleUrls: ['./model-select.component.scss']
})
export class PersonaSelectComponent {
  @Input() personas: IPublicPersona[] = [];
  /** The picked agent's id; null = no agent. An id that isn't in personas counts as none. */
  @Input() selectedId: number | null = null;
  /** The description under "No agent". */
  @Input() noneHint: string | null = null;
  @Output() selectedChange = new EventEmitter<number | null>();

  get selected(): IPublicPersona | null {
    return this.personas.find(p => p.id === this.selectedId) ?? null;
  }

  select(id: number | null): void {
    if (id !== (this.selected?.id ?? null)) {
      this.selectedChange.emit(id);
    }
  }
}
