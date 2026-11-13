import { Component, ElementRef, Inject } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { DecimalPipe } from '@angular/common';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import {
  ISkillCreate,
  ISkillOut,
  SKILL_CONTENT_MAX,
  SKILL_DESCRIPTION_MAX,
  SKILL_NAME_MAX,
  SKILL_NAME_PATTERN
} from '../data/models/catalog.model';
import { CatalogAdminStore } from './catalog-admin.store';
import { describeHttpError, DIALOG_ERROR, INVALID_FIELD, revealInDialog } from './catalog-admin.utils';

export interface SkillDialogData {
  skill: ISkillOut | null;  // null = a new skill
}

/** Write or edit a skill (docs/skills.md): its name, the description the agent picks it by, and its text. */
@Component({
  selector: 'app-skill-dialog',
  standalone: true,
  imports: [
    DecimalPipe,
    ReactiveFormsModule,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSlideToggleModule,
    TranslateModule
  ],
  template: `
    <h2 mat-dialog-title>{{ (isNew ? 'catalog.admin.skills.addTitle' : 'catalog.admin.skills.editTitle') | translate }}</h2>

    <form [formGroup]="form" (ngSubmit)="save()">
      <mat-dialog-content class="catalog-dialog-content skill-dialog-content">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>{{ 'catalog.admin.fields.name' | translate }}</mat-label>
          <input matInput formControlName="name" required class="code-input" placeholder="image-generation"
                 autocomplete="off" spellcheck="false" [maxlength]="nameMax">
          <mat-hint>{{ (isNew ? 'catalog.admin.skills.nameHint' : 'catalog.admin.skills.renameHint') | translate }}</mat-hint>
          @if (form.controls['name'].hasError('required')) {
            <mat-error>{{ 'catalog.admin.validation.required' | translate }}</mat-error>
          } @else if (form.controls['name'].hasError('pattern')) {
            <mat-error>{{ 'catalog.admin.skills.nameInvalid' | translate }}</mat-error>
          }
        </mat-form-field>

        <mat-form-field appearance="outline" class="full-width">
          <mat-label>{{ 'catalog.admin.fields.description' | translate }}</mat-label>
          <textarea matInput formControlName="description" required [maxlength]="descriptionMax"
                    cdkTextareaAutosize cdkAutosizeMinRows="2" cdkAutosizeMaxRows="6"
                    [placeholder]="'catalog.admin.skills.descriptionPlaceholder' | translate"></textarea>
          <mat-hint>{{ 'catalog.admin.skills.descriptionHint' | translate }}</mat-hint>
          <mat-hint align="end">{{ length('description') | number }} / {{ descriptionMax | number }}</mat-hint>
          @if (form.controls['description'].hasError('required')) {
            <mat-error>{{ 'catalog.admin.validation.required' | translate }}</mat-error>
          }
        </mat-form-field>

        <mat-form-field appearance="outline" class="full-width">
          <mat-label>{{ 'catalog.admin.skills.content' | translate }}</mat-label>
          <!-- Grows with the text (up to a limit), so a long skill scrolls with the dialog, not in a small box -->
          <textarea matInput formControlName="content" required class="code-input" [maxlength]="contentMax"
                    cdkTextareaAutosize cdkAutosizeMinRows="12" cdkAutosizeMaxRows="28" spellcheck="false"
                    [placeholder]="'catalog.admin.skills.contentPlaceholder' | translate"></textarea>
          <mat-hint>{{ 'catalog.admin.skills.contentHint' | translate }}</mat-hint>
          <mat-hint align="end">{{ length('content') | number }} / {{ contentMax | number }}</mat-hint>
          @if (form.controls['content'].hasError('required')) {
            <mat-error>{{ 'catalog.admin.validation.required' | translate }}</mat-error>
          }
        </mat-form-field>

        <div class="toggle-with-hint">
          <mat-slide-toggle formControlName="enabled">{{ 'catalog.admin.fields.enabled' | translate }}</mat-slide-toggle>
          <p class="toggle-hint">{{ 'catalog.admin.skills.enabledHint' | translate }}</p>
        </div>

        @if (error) {
          <p class="dialog-error" role="alert"><mat-icon aria-hidden="true">error_outline</mat-icon>{{ error }}</p>
        }
      </mat-dialog-content>

      <mat-dialog-actions align="end">
        <button mat-button type="button" mat-dialog-close>{{ 'catalog.common.cancel' | translate }}</button>
        <button mat-flat-button color="primary" type="submit" [disabled]="saving">
          @if (saving) {
            <mat-spinner diameter="18"></mat-spinner>
          }
          {{ 'catalog.common.save' | translate }}
        </button>
      </mat-dialog-actions>
    </form>
  `,
  styleUrls: ['./catalog-dialog.scss'],
  styles: [`
    // Wider than the other dialogs: the text is long Markdown
    .skill-dialog-content { width: min(760px, calc(100vw - 32px)); }
  `]
})
export class SkillDialogComponent {
  readonly nameMax = SKILL_NAME_MAX;
  readonly descriptionMax = SKILL_DESCRIPTION_MAX;
  readonly contentMax = SKILL_CONTENT_MAX;

  form: FormGroup;
  skill: ISkillOut | null;
  saving = false;
  error: string | null = null;

  constructor(
    @Inject(MAT_DIALOG_DATA) data: SkillDialogData,
    private dialogRef: MatDialogRef<SkillDialogComponent, ISkillOut>,
    private host: ElementRef<HTMLElement>,
    private store: CatalogAdminStore,
    private translate: TranslateService,
    fb: FormBuilder
  ) {
    this.skill = data.skill;
    const s = data.skill;
    this.form = fb.group({
      name: [s?.name ?? '', [Validators.required, Validators.pattern(SKILL_NAME_PATTERN)]],
      description: [s?.description ?? '', Validators.required],
      content: [s?.content ?? '', Validators.required],
      enabled: [s?.enabled ?? true]
    });
  }

  get isNew(): boolean {
    return this.skill === null;
  }

  length(field: 'description' | 'content'): number {
    return (this.form.controls[field].value ?? '').length;
  }

  async save(): Promise<void> {
    if (this.saving) return;
    // Spaces around the name are a typing slip, not part of it
    const name = this.form.controls['name'];
    name.setValue((name.value ?? '').trim());
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      revealInDialog(this.host.nativeElement, INVALID_FIELD);
      return;
    }
    const v = this.form.getRawValue();
    const body: ISkillCreate = {
      name: v.name,
      description: v.description.trim(),
      content: v.content.trim(),
      enabled: !!v.enabled
    };

    this.saving = true;
    this.error = null;
    try {
      const saved = await this.store.saveSkill(this.skill?.id ?? null, body);
      this.dialogRef.close(saved);
    } catch (error) {
      this.error = describeHttpError(error, this.translate);
      revealInDialog(this.host.nativeElement, DIALOG_ERROR);
    } finally {
      this.saving = false;
    }
  }
}
