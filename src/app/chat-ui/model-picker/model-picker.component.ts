import { ChangeDetectionStrategy, Component, ViewEncapsulation } from '@angular/core';
import { AsyncPipe } from '@angular/common';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';
import { combineLatest, Observable } from 'rxjs';
import { map } from 'rxjs/operators';
import { ChatStateService } from '../../services/chat-state.service';
import { CatalogService } from '../../services/catalog.service';
import { IConversationSelection, IPublicModel, IPublicPersona } from '../../data/models/catalog.model';
import { ModelSelectComponent } from '../../components/catalog/model-select.component';
import { askPersonaValues, personaInputVariables } from './persona-values-dialog.component';

interface PickerView {
  models: IPublicModel[];
  personas: IPublicPersona[];
  selection: IConversationSelection;
  effectiveModel: IPublicModel | null;
  persona: IPublicPersona | null;
}

/**
 * Model and persona dropdowns for the active conversation, shown in the chat composer.
 * Hidden when the catalog is empty (the backend then answers with its environment model).
 */
@Component({
  selector: 'app-model-picker',
  standalone: true,
  imports: [AsyncPipe, MatDialogModule, MatIconModule, MatMenuModule, MatTooltipModule, TranslateModule, ModelSelectComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
  template: `
    @if (view$ | async; as view) {
      <div class="model-picker">
        @if (view.models.length > 0) {
          <app-model-select variant="chip"
                            [models]="view.models"
                            [selectedId]="view.effectiveModel?.id ?? null"
                            [displayedModel]="view.effectiveModel"
                            (selectedChange)="selectModel($event)">
          </app-model-select>
        }

        @if (view.personas.length > 0) {
          <button type="button"
                  class="persona-trigger"
                  [class.persona-trigger--active]="!!view.persona"
                  [matMenuTriggerFor]="personaMenu"
                  [matTooltip]="('catalog.picker.persona' | translate) + ': ' + (view.persona?.name ?? ('catalog.picker.noPersona' | translate))"
                  [attr.aria-label]="('catalog.picker.choosePersona' | translate) + ': ' + (view.persona?.name ?? ('catalog.picker.noPersona' | translate))">
            <mat-icon aria-hidden="true">theater_comedy</mat-icon>
            @if (view.persona) {
              <span class="persona-trigger-name">{{ view.persona.name }}</span>
            }
            <mat-icon class="persona-trigger-arrow" aria-hidden="true">arrow_drop_down</mat-icon>
          </button>

          <mat-menu #personaMenu="matMenu" class="model-select-panel" xPosition="after" yPosition="above">
            <button mat-menu-item type="button" role="menuitemradio"
                    [attr.aria-checked]="!view.persona"
                    [class.is-selected]="!view.persona"
                    (click)="selectPersona(null, view)">
              <span class="model-option">
                <span class="model-option-main">
                  <span class="model-option-name">{{ 'catalog.picker.noPersona' | translate }}</span>
                  @if (!view.persona) {
                    <mat-icon class="model-option-check" aria-hidden="true">check</mat-icon>
                  }
                </span>
              </span>
            </button>
            @for (persona of view.personas; track persona.id) {
              <button mat-menu-item type="button" role="menuitemradio"
                      [attr.aria-checked]="persona.id === view.persona?.id"
                      [class.is-selected]="persona.id === view.persona?.id"
                      (click)="selectPersona(persona, view)">
                <span class="model-option">
                  <span class="model-option-main">
                    <span class="model-option-name">{{ persona.name }}</span>
                    @if (hasInputs(persona)) {
                      <mat-icon class="persona-option-edit" aria-hidden="true">tune</mat-icon>
                    }
                    @if (persona.id === view.persona?.id) {
                      <mat-icon class="model-option-check" aria-hidden="true">check</mat-icon>
                    }
                  </span>
                  @if (persona.description) {
                    <span class="model-option-description">{{ persona.description }}</span>
                  }
                </span>
              </button>
            }
          </mat-menu>
        }
      </div>
    }
  `,
  styleUrls: ['./model-picker.component.scss']
})
export class ModelPickerComponent {
  view$: Observable<PickerView>;

  constructor(
    private chatState: ChatStateService,
    private catalog: CatalogService,
    private dialog: MatDialog
  ) {
    this.view$ = combineLatest([
      this.catalog.models$,
      this.catalog.personas$,
      this.chatState.selection$,
      this.chatState.effectiveModel$,
      this.chatState.activePersona$
    ]).pipe(
      map(([models, personas, selection, effectiveModel, persona]) =>
        ({ models, personas, selection, effectiveModel, persona }))
    );
  }

  hasInputs(persona: IPublicPersona): boolean {
    return personaInputVariables(persona).length > 0;
  }

  selectModel(modelId: number | null): void {
    this.chatState.selectModel(modelId).catch(error => console.error('Failed to select model:', error));
  }

  async selectPersona(persona: IPublicPersona | null, view: PickerView): Promise<void> {
    if (!persona) {
      if (view.persona) await this.chatState.selectPersona(null);
      return;
    }

    // Ask for the variables (prefilled with the stored values when re-picking the same persona)
    const samePersona = persona.id === view.selection.personaId;
    const values = await askPersonaValues(this.dialog, persona, samePersona ? view.selection.personaValues : null);
    if (values === undefined) return;  // Cancelled
    if (values === null && samePersona) return;  // Nothing to change

    await this.chatState.selectPersona(persona, values);
  }
}
