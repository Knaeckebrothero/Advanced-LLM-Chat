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
  CURRENCIES,
  IProviderCreate,
  IProviderOut,
  IProviderUpdate,
  PRIVACY_TIERS,
  PROVIDER_KINDS
} from '../data/models/catalog.model';
import { CatalogAdminStore } from './catalog-admin.store';
import { describeHttpError, formatJson, jsonObjectValidator, parseJsonObject, textOrNull } from './catalog-admin.utils';

export interface ProviderDialogData {
  provider: IProviderOut | null;  // null = add a new provider
}

/** Add or edit a provider. The API key is write-only: empty keeps the stored key. */
@Component({
  selector: 'app-provider-dialog',
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
  templateUrl: './provider-dialog.component.html',
  styleUrls: ['./catalog-dialog.scss']
})
export class ProviderDialogComponent {
  readonly kinds = PROVIDER_KINDS;
  readonly tiers = PRIVACY_TIERS;
  readonly currencies = CURRENCIES;

  form: FormGroup;
  provider: IProviderOut | null;
  removeKey = false;
  saving = false;
  error: string | null = null;

  constructor(
    @Inject(MAT_DIALOG_DATA) data: ProviderDialogData,
    private dialogRef: MatDialogRef<ProviderDialogComponent, IProviderOut>,
    private store: CatalogAdminStore,
    private translate: TranslateService,
    fb: FormBuilder
  ) {
    this.provider = data.provider;
    const p = data.provider;
    this.form = fb.group({
      name: [p?.name ?? '', Validators.required],
      kind: [p?.kind ?? 'openai_compatible', Validators.required],
      baseUrl: [p?.baseUrl ?? ''],
      apiKey: [''],
      apiKeyEnv: [p?.apiKeyEnv ?? '', Validators.pattern(/^[A-Za-z_][A-Za-z0-9_]*$/)],
      privacyTier: [p?.privacyTier ?? 'trusted', Validators.required],
      currency: [p?.currency ?? 'USD', Validators.required],
      defaultHeaders: [formatJson(p?.defaultHeaders), jsonObjectValidator(true)],
      notes: [p?.notes ?? ''],
      enabled: [p?.enabled ?? true]
    });
  }

  get isNew(): boolean {
    return this.provider === null;
  }

  toggleRemoveKey(): void {
    this.removeKey = !this.removeKey;
    if (this.removeKey) {
      this.form.controls['apiKey'].setValue('');
      this.form.controls['apiKey'].disable();
    } else {
      this.form.controls['apiKey'].enable();
    }
  }

  async save(): Promise<void> {
    if (this.form.invalid || this.saving) {
      this.form.markAllAsTouched();
      return;
    }
    const v = this.form.getRawValue();
    const base = {
      name: v.name.trim(),
      kind: v.kind,
      baseUrl: textOrNull(v.baseUrl),
      apiKeyEnv: textOrNull(v.apiKeyEnv),
      privacyTier: v.privacyTier,
      currency: v.currency,
      defaultHeaders: parseJsonObject<Record<string, string>>(v.defaultHeaders),
      notes: textOrNull(v.notes),
      enabled: !!v.enabled
    };
    const apiKey = textOrNull(v.apiKey);

    let body: IProviderCreate | IProviderUpdate;
    if (this.isNew) {
      body = { ...base, ...(apiKey && { apiKey }) };
    } else {
      // Left out = keep the stored key, "" = remove it
      body = { ...base };
      if (this.removeKey) body.apiKey = '';
      else if (apiKey) body.apiKey = apiKey;
    }

    this.saving = true;
    this.error = null;
    try {
      const saved = await this.store.saveProvider(this.provider?.id ?? null, body);
      this.dialogRef.close(saved);
    } catch (error) {
      this.error = describeHttpError(error, this.translate);
    } finally {
      this.saving = false;
    }
  }
}
