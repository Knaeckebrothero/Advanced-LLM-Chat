import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';
import { SettingsRepository } from '../repositories/settings.repository';
import { ThemeService } from './theme.service';
import { AppSettings } from '../models/settings.model';
import { Language, Theme } from '../models/enum';

const DEFAULT_SETTINGS: AppSettings = {
  theme: Theme.Auto,
  language: Language.English,
  lastUpdated: 0,
};

@Injectable({ providedIn: 'root' })
export class SettingsStateService {
  private settingsSubject = new BehaviorSubject<AppSettings>(DEFAULT_SETTINGS);
  public settings$ = this.settingsSubject.asObservable();

  constructor(
    private repository: SettingsRepository,
    private themeService: ThemeService
  ) {
    this.loadInitialSettings();
  }

  private async loadInitialSettings() {
    const settings = await this.repository.getSettings();
    this.settingsSubject.next(settings);
    this.themeService.setTheme(settings.theme);
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

    await this.repository.saveSettings(updatedSettings);
  }
}
