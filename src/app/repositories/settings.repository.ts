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

  /**
   * Load the settings: the server's if they are newer than the local copy (or
   * preferRemote is set, e.g. right after a login), else the local ones.
   */
  /** The settings stored in this browser, without asking the backend (for the start, before a session exists). */
  async getLocalSettings(): Promise<AppSettings> {
    try {
      const db = await this.dbService.getDb();
      return (await db.get('settings', SETTINGS_KEY)) || DEFAULT_SETTINGS;
    } catch (error) {
      console.warn('Could not fetch local settings from IndexedDB. Using default.', error);
      return DEFAULT_SETTINGS;
    }
  }

  async getSettings(preferRemote = false): Promise<AppSettings> {
    const db = await this.dbService.getDb();
    let localSettings: AppSettings | undefined;

    try {
      localSettings = await db.get('settings', SETTINGS_KEY);
    } catch (error) {
      console.warn('Could not fetch local settings from IndexedDB. Using remote/default.', error);
      localSettings = undefined;
    }

    try {
      const remoteSettings = await this.apiService.getSettings();
      if (
        remoteSettings &&
        (preferRemote || !localSettings || toMillis(remoteSettings.lastUpdated) > toMillis(localSettings.lastUpdated))
      ) {
        // An older backend leaves newer fields out (default model, background, editing mode): keep the local values then
        const merged: AppSettings = {
          ...remoteSettings,
          defaultModelId: remoteSettings.defaultModelId !== undefined
            ? remoteSettings.defaultModelId
            : localSettings?.defaultModelId ?? null,
          background: remoteSettings.background ?? localSettings?.background,
          backgroundDim: remoteSettings.backgroundDim ?? localSettings?.backgroundDim,
          backgroundBlur: remoteSettings.backgroundBlur ?? localSettings?.backgroundBlur,
          editingMode: remoteSettings.editingMode ?? localSettings?.editingMode,
        };
        const storableSettings = { ...merged, id: SETTINGS_KEY };
        await db.put('settings', storableSettings);
        return merged;
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

/** The server sends lastUpdated in seconds, the app stores Date.now() in milliseconds. */
function toMillis(timestamp: number | undefined): number {
  if (!timestamp) {
    return 0;
  }
  return timestamp < 1e11 ? timestamp * 1000 : timestamp;
}
