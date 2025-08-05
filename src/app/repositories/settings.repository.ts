import { Injectable } from '@angular/core';
import { DBService } from '../data/db.service';
import { ApiService } from '../services/api.service';
import { AppSettings } from '../models/settings.model';
import { Language, Theme } from '../models/enum';

const DEFAULT_SETTINGS: AppSettings = {
  theme: Theme.Auto,
  language: Language.English,
  lastUpdated: 0,
};

const SETTINGS_KEY = 'user-settings';

@Injectable({ providedIn: 'root' })
export class SettingsRepository {
  constructor(private dbService: DBService, private apiService: ApiService) {}

  async getSettings(): Promise<AppSettings> {
    const db = await this.dbService.getDb();
    let localSettings: AppSettings | undefined;

    try {
      localSettings = await db.get('settings', 'user-settings');
    } catch (error) {
      console.warn('Could not fetch local settings from IndexedDB. Using remote/default.', error);
      localSettings = undefined;
    }

    try {
      const remoteSettings = await this.apiService.getSettings();
      if (
        remoteSettings &&
        (!localSettings || remoteSettings.lastUpdated > localSettings.lastUpdated)
      ) {
        const storableSettings = { ...remoteSettings, id: 'user-settings' };
        await db.put('settings', storableSettings);
        return remoteSettings;
      }
    } catch (error) {
      console.warn('Could not fetch remote settings. Using local.', error);
    }

    return localSettings || DEFAULT_SETTINGS;
  }

  async saveSettings(settings: AppSettings): Promise<void> {
    const db = await this.dbService.getDb();
    const storableSettings = { ...settings, id: SETTINGS_KEY };
    await db.put('settings', storableSettings);

    try {
      await this.apiService.saveSettings(settings);
    } catch (error) {
      console.error(
        'Failed to save settings to server. Will sync later.',
        error
      );
    }
  }
}
