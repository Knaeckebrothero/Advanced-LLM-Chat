import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatDialogRef } from '@angular/material/dialog';
import { SettingsStateService } from '../services/settings-state.service';
import { CatalogService } from '../services/catalog.service';
import { AuthService } from '../auth/auth.service';
import { UIStateService } from '../services/ui-state.service';
import { AppSettings } from '../models/settings.model';
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

  constructor(
    private settingsState: SettingsStateService,
    private dialogRef: MatDialogRef<SettingsComponent>,
    private translate: TranslateService,
    private catalogService: CatalogService,
    private authService: AuthService,
    private router: Router,
    private uiState: UIStateService
  ) {
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

  openCatalogAdmin(): void {
    this.dialogRef.close();
    this.uiState.closeSidebarOnMobile();
    this.router.navigate(['/admin/catalog']);
  }

  close(): void {
    this.dialogRef.close();
  }
}
