import { Component, Inject } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import {
  IModelCreate,
  IModelOut,
  IProviderOut,
  PRIVACY_TIERS,
  REASONING_MODES
} from '../data/models/catalog.model';
import { CatalogAdminStore } from './catalog-admin.store';
import {
  describeHttpError,
  formatJson,
  jsonObjectValidator,
  numberOrNull,
  parseJsonObject,
  textOrNull
} from './catalog-admin.utils';

export interface ModelDialogData {
  model: IModelOut | null;  // null = add a new model
  providers: IProviderOut[];
  providerId?: number;  // Preselected provider for a new model
}

/** Add or edit a model with all its settings. */
@Component({
  selector: 'app-model-dialog',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSlideToggleModule,
    TranslateModule
  ],
  templateUrl: './model-dialog.component.html',
  styleUrls: ['./catalog-dialog.scss']
})
export class ModelDialogComponent {
  readonly tiers = PRIVACY_TIERS;
  readonly reasoningModes = REASONING_MODES;
  readonly effortSuggestions = ['minimal', 'low', 'medium', 'high'];

  form: FormGroup;
  model: IModelOut | null;
  providers: IProviderOut[];
  saving = false;
  error: string | null = null;

  constructor(
    @Inject(MAT_DIALOG_DATA) data: ModelDialogData,
    private dialogRef: MatDialogRef<ModelDialogComponent, IModelOut>,
    private store: CatalogAdminStore,
    private translate: TranslateService,
    fb: FormBuilder
  ) {
    this.model = data.model;
    this.providers = data.providers;
    const m = data.model;
    this.form = fb.group({
      providerId: [m?.providerId ?? data.providerId ?? data.providers[0]?.id ?? null, Validators.required],
      displayName: [m?.displayName ?? '', Validators.required],
      modelId: [m?.modelId ?? '', Validators.required],
      description: [m?.description ?? ''],
      supportsTools: [m?.supportsTools ?? true],
      supportsVision: [m?.supportsVision ?? false],
      reasoning: [m?.reasoning ?? 'none'],
      reasoningPassback: [m?.reasoningPassback ?? false],
      reasoningEffort: [m?.reasoningEffort ?? ''],
      temperature: [m?.temperature ?? null, [Validators.min(0), Validators.max(2)]],
      topP: [m?.topP ?? null, [Validators.min(0), Validators.max(1)]],
      maxOutputTokens: [m?.maxOutputTokens ?? null, [Validators.min(1)]],
      contextWindow: [m?.contextWindow ?? null, [Validators.min(1)]],
      inputPricePerMtok: [m?.inputPricePerMtok ?? null, [Validators.min(0)]],
      outputPricePerMtok: [m?.outputPricePerMtok ?? null, [Validators.min(0)]],
      extraBody: [formatJson(m?.extraBody), jsonObjectValidator()],
      privacyTier: [m?.privacyTier ?? null],
      isAuxiliary: [m?.isAuxiliary ?? false],
      availableToGuests: [m?.availableToGuests ?? false],
      enabled: [m?.enabled ?? true],
      sortOrder: [m?.sortOrder ?? 0, [Validators.required]],
      notes: [m?.notes ?? '']
    });
  }

  get isNew(): boolean {
    return this.model === null;
  }

  get selectedProvider(): IProviderOut | undefined {
    return this.providers.find(p => p.id === this.form.controls['providerId'].value);
  }

  async save(): Promise<void> {
    if (this.form.invalid || this.saving) {
      this.form.markAllAsTouched();
      return;
    }
    const v = this.form.getRawValue();
    // Every field is sent; null clears an optional one
    const body: IModelCreate = {
      providerId: v.providerId,
      displayName: v.displayName.trim(),
      modelId: v.modelId.trim(),
      description: textOrNull(v.description),
      supportsTools: !!v.supportsTools,
      supportsVision: !!v.supportsVision,
      reasoning: v.reasoning,
      reasoningPassback: !!v.reasoningPassback,
      reasoningEffort: textOrNull(v.reasoningEffort),
      temperature: numberOrNull(v.temperature),
      topP: numberOrNull(v.topP),
      maxOutputTokens: numberOrNull(v.maxOutputTokens),
      contextWindow: numberOrNull(v.contextWindow),
      inputPricePerMtok: numberOrNull(v.inputPricePerMtok),
      outputPricePerMtok: numberOrNull(v.outputPricePerMtok),
      extraBody: parseJsonObject(v.extraBody),
      privacyTier: v.privacyTier || null,
      isAuxiliary: !!v.isAuxiliary,
      availableToGuests: !!v.availableToGuests,
      enabled: !!v.enabled,
      sortOrder: numberOrNull(v.sortOrder) ?? 0,
      notes: textOrNull(v.notes)
    };

    this.saving = true;
    this.error = null;
    try {
      const saved = await this.store.saveModel(this.model?.id ?? null, body);
      this.dialogRef.close(saved);
    } catch (error) {
      this.error = describeHttpError(error, this.translate);
    } finally {
      this.saving = false;
    }
  }
}
