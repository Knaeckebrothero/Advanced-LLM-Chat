import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatDialogRef } from '@angular/material/dialog';
import { SettingsStateService } from '../services/settings-state.service';
import { CatalogService } from '../services/catalog.service';
import { AuthService } from '../auth/auth.service';
import { UIStateService } from '../services/ui-state.service';
import { AppSettings, BACKGROUND_BLUR_MAX, BACKGROUND_DIM_MAX, BackgroundChoice } from '../models/settings.model';
import {
  BackgroundService,
  BUILT_IN_BACKGROUNDS,
  DEFAULT_BACKGROUND_BLUR,
  DEFAULT_BACKGROUND_DIM,
} from '../services/background.service';
import { Language, Theme } from '../models/enum';
import { IPublicModel } from '../data/models/catalog.model';
import { ModelSelectComponent } from '../components/catalog/model-select.component';
import { Observable } from 'rxjs';
import {TranslateModule, TranslatePipe, TranslateService} from '@ngx-translate/core';


@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [CommonModule, MatIconModule, TranslateModule, ModelSelectComponent],
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
})
export class SettingsComponent {
  settings$: Observable<AppSettings | null>;
  models$: Observable<IPublicModel[]>;
  isAdmin$: Observable<boolean>;

  themeOptions = [
    { value: Theme.Light, icon: 'light_mode', label: 'Light' },
    { value: Theme.Dark, icon: 'dark_mode', label: 'Dark' },
    { value: Theme.Auto, icon: 'brightness_auto', label: 'Auto' },
  ];

  languageOptions = [
    { value: Language.English, label: 'EN' },
    { value: Language.German, label: 'DE' },
  ];

  backgroundOptions: { value: BackgroundChoice; label: string }[] = [
    { value: 'none', label: 'background.none' },
    { value: 'aurora', label: 'background.aurora' },
    { value: 'ridges', label: 'background.ridges' },
    { value: 'custom', label: 'background.custom' },
  ];
  readonly dimMax = BACKGROUND_DIM_MAX;
  readonly blurMax = BACKGROUND_BLUR_MAX;
  customImageUrl$: Observable<string | null>;
  // Slider values while dragging (saved on release)
  dimPreview: number | null = null;
  blurPreview: number | null = null;
  imageError: string | null = null;

  constructor(
    private settingsState: SettingsStateService,
    private dialogRef: MatDialogRef<SettingsComponent>,
    private translate: TranslateService,
    private catalogService: CatalogService,
    private authService: AuthService,
    private router: Router,
    private uiState: UIStateService,
    private backgroundService: BackgroundService
  ) {
    this.customImageUrl$ = this.backgroundService.customImageUrl$;
    this.settings$ = this.settingsState.settings$;
    this.models$ = this.catalogService.models$;
    this.isAdmin$ = this.authService.isAdmin$;
  }

  updateTheme(theme: Theme): void {
    this.settingsState.updateSettings({ theme });
  }

  updateLanguage(language: Language): void {
    this.settingsState.updateSettings({ language });
  }

  /** Model for new conversations; null = the first model of the catalog. */
  updateDefaultModel(defaultModelId: number | null): void {
    this.settingsState.updateSettings({ defaultModelId });
  }

  /** A default model that is gone from the catalog counts as automatic. */
  selectedDefaultModel(settings: AppSettings, models: IPublicModel[]): number | null {
    const id = settings.defaultModelId ?? null;
    return models.some(m => m.id === id) ? id : null;
  }

  activeBackground(settings: AppSettings): BackgroundChoice {
    return settings.background ?? 'none';
  }

  /** CSS background of a choice's thumbnail. */
  backgroundThumb(choice: BackgroundChoice, customUrl: string | null): string | null {
    if (choice === 'custom') {
      return customUrl ? `url("${customUrl}")` : null;
    }
    if (choice === 'none') {
      return null;
    }
    return `url("${this.backgroundService.builtInUrl(choice as keyof typeof BUILT_IN_BACKGROUNDS)}")`;
  }

  /** Pick a background; "Your image" without an image in this browser opens the file picker. */
  chooseBackground(choice: BackgroundChoice, customUrl: string | null, fileInput: HTMLInputElement): void {
    this.imageError = null;
    if (choice === 'custom' && !customUrl) {
      fileInput.click();
      return;
    }
    this.settingsState.updateSettings({ background: choice });
  }

  async onImageSelected(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';  // Picking the same file again still fires change
    if (!file) {
      return;
    }
    this.imageError = null;
    try {
      await this.backgroundService.setCustomImage(file);
    } catch (error) {
      const reason = error instanceof Error ? error.message : '';
      this.imageError = reason === 'too-large' ? 'background.errorTooLarge' : 'background.errorNotImage';
    }
  }

  removeCustomImage(): void {
    this.imageError = null;
    this.backgroundService.removeCustomImage();
  }

  backgroundDim(settings: AppSettings): number {
    return this.dimPreview ?? settings.backgroundDim ?? DEFAULT_BACKGROUND_DIM;
  }

  backgroundBlur(settings: AppSettings): number {
    return this.blurPreview ?? settings.backgroundBlur ?? DEFAULT_BACKGROUND_BLUR;
  }

  previewDim(event: Event): void {
    this.dimPreview = Number((event.target as HTMLInputElement).value);
    this.backgroundService.preview({ dim: this.dimPreview, blur: this.blurPreview ?? undefined });
  }

  previewBlur(event: Event): void {
    this.blurPreview = Number((event.target as HTMLInputElement).value);
    this.backgroundService.preview({ dim: this.dimPreview ?? undefined, blur: this.blurPreview });
  }

  async saveBackgroundAdjustments(): Promise<void> {
    const changes: Partial<AppSettings> = {};
    if (this.dimPreview !== null) {
      changes.backgroundDim = this.dimPreview;
    }
    if (this.blurPreview !== null) {
      changes.backgroundBlur = this.blurPreview;
    }
    await this.settingsState.updateSettings(changes);
    this.dimPreview = null;
    this.blurPreview = null;
    this.backgroundService.clearPreview();
  }

  openCatalogAdmin(): void {
    this.dialogRef.close();
    this.uiState.closeSidebarOnMobile();
    this.router.navigate(['/admin/catalog']);
  }

  close(): void {
    this.dialogRef.close();
  }
}
