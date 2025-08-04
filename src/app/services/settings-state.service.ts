import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { map, shareReplay } from 'rxjs/operators';
import { SettingsRepository, SettingsWithMetadata } from '../repositories/settings.repository';
import { ThemeService } from './theme.service';
import { Settings } from '../models/settings.model';
import {Language, Theme} from "../models/enum";

export interface AppSettings extends Settings {
  // From SettingsWithMetadata
  id?: string;
  timestamp?: Date;
  syncHash?: string;
  // Computed properties
  isEnglish?: boolean;
  isDarkMode?: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class SettingsStateService {
  // Current settings state
  private settings$ = this.settingsRepository.getCurrent().pipe(
    map(settings => this.enrichSettings(settings)),
    shareReplay(1)
  );

  // Loading and sync states
  public isLoading$ = new BehaviorSubject<boolean>(false);
  public isSyncing$ = this.settingsRepository.syncing$;
  public lastError$ = new BehaviorSubject<string | null>(null);

  constructor(
    private settingsRepository: SettingsRepository,
    private themeService: ThemeService
  ) {
    // Apply theme when settings change
    this.settings$.subscribe(settings => {
      if (settings) {
        // If theme is undefined, respect system preference
        if (settings.theme === undefined) {
          this.themeService.setTheme(Theme.Auto);
        } else {
          // Apply user's preference
          this.themeService.setTheme(settings.theme);
        }
      }
    });
  }

  /**
   * Get current settings
   */
  get settings(): Observable<AppSettings | null> {
    return this.settings$;
  }

  /**
   * Get specific setting value
   */
  getSetting<K extends keyof AppSettings>(key: K): Observable<AppSettings[K] | undefined> {
    return this.settings$.pipe(
      map(settings => settings?.[key])
    );
  }

  /**
   * Load settings (from cache or backend)
   */
  async loadSettings(): Promise<void> {
    this.isLoading$.next(true);
    this.lastError$.next(null);

    try {
      // Repository will handle loading from IndexedDB first
      // If online, it will sync with backend
      await this.settingsRepository.sync();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to load settings';
      this.lastError$.next(errorMessage);
      console.error('Failed to load settings:', error);
    } finally {
      this.isLoading$.next(false);
    }
  }

  /**
   * Save settings
   */
  async saveSettings(settings: Partial<AppSettings>): Promise<void> {
    this.isLoading$.next(true);
    this.lastError$.next(null);

    try {
      const current = await this.getCurrentSettings();
      const updated: SettingsWithMetadata = {
        ...current,
        ...settings,
        theme: settings.theme || current?.theme || Theme.Auto,
        language: settings.language || current?.language || Language.English
      };

      await this.settingsRepository.save(updated);

      // Apply theme if changed
      if (settings.theme !== undefined) {
        this.themeService.setTheme(settings.theme);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to save settings';
      this.lastError$.next(errorMessage);
      throw error;
    } finally {
      this.isLoading$.next(false);
    }
  }

  /**
   * Force sync with backend
   */
  async syncSettings(): Promise<void> {
    this.lastError$.next(null);

    try {
      await this.settingsRepository.sync();
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to sync settings';
      this.lastError$.next(errorMessage);
      throw error;
    }
  }

  /**
   * Helper to get current settings synchronously
   */
  private async getCurrentSettings(): Promise<AppSettings | null> {
    return new Promise((resolve) => {
      this.settings$.pipe(
        map(settings => settings)
      ).subscribe(settings => resolve(settings));
    });
  }

  /**
   * Enrich settings with computed properties
   */
  private enrichSettings(settings: SettingsWithMetadata | null): AppSettings | null {
    if (!settings) return null;

    // When theme is undefined, default to auto
    const themeValue = settings.theme || Theme.Auto;

    return {
      ...settings,
      theme: themeValue,
      isEnglish: settings.language === Language.English,
      isDarkMode: this.themeService.getEffectiveTheme(themeValue) === 'dark'
    };
  }
}
