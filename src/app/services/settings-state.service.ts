import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { distinctUntilChanged, filter, map, skip } from 'rxjs/operators';
import { SettingsRepository } from '../repositories/settings.repository';
import { ThemeService } from './theme.service';
import { AppSettings } from '../models/settings.model';
import { Language, Theme } from '../models/enum';
import { TranslateService } from '@ngx-translate/core';
import { AuthService } from '../auth/auth.service';

const DEFAULT_SETTINGS: AppSettings = {
  theme: Theme.Auto,
  language: Language.English,
  lastUpdated: 0,
};

@Injectable({ providedIn: 'root' })
export class SettingsStateService {
  private settingsSubject = new BehaviorSubject<AppSettings>(DEFAULT_SETTINGS);
  public settings$ = this.settingsSubject.asObservable();

  /**
   * Get the current settings value synchronously
   */
  getCurrentSettings(): AppSettings {
    return this.settingsSubject.value;
  }

  constructor(
    private repository: SettingsRepository,
    private themeService: ThemeService,
    private translate: TranslateService,
    private authService: AuthService
  ) {
    this.loadInitialSettings();

    // The first load runs before login (it then only finds local settings), so load
    // again whenever another user logs in, e.g. to apply their theme and background
    this.authService.currentUser$.pipe(
      map(user => user?.id ?? null),
      distinctUntilChanged(),
      skip(1),
      filter(userId => userId !== null)
    ).subscribe(() => this.loadInitialSettings(!this.authService.isGuest));
  }

  private async loadInitialSettings(preferRemote = false) {
    try {
      const settings = await this.repository.getSettings(preferRemote);
      this.settingsSubject.next(settings);
      this.themeService.setTheme(settings.theme);
      this.translate.use(settings.language); // ADD THIS LINE
    } catch (error) {
      console.error('Failed to load initial settings:', error);
      this.settingsSubject.next(DEFAULT_SETTINGS);
      this.themeService.setTheme(DEFAULT_SETTINGS.theme);
      this.translate.use(DEFAULT_SETTINGS.language); // ADD THIS LINE
    }
  }

  async updateSettings(newSettings: Partial<AppSettings>) {
    const currentSettings = this.settingsSubject.value;
    const updatedSettings: AppSettings = {
      ...currentSettings,
      ...newSettings,
      lastUpdated: Date.now(),
    };

    this.settingsSubject.next(updatedSettings);

    if (newSettings.theme) {
      this.themeService.setTheme(newSettings.theme);
    }

    if (newSettings.language) {
      this.translate.use(newSettings.language);
    }

    await this.repository.saveSettings(updatedSettings);
  }
}
