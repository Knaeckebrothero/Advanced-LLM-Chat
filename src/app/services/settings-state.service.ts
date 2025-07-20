import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { map, switchMap, shareReplay } from 'rxjs/operators';
import { SettingsRepository, SettingsWithMetadata } from '../repositories/settings.repository';
import { ThemeService } from './theme.service';

export interface AppSettings extends SettingsWithMetadata {
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
      if (settings?.darkMode !== undefined) {
        this.themeService.setTheme(settings.darkMode === 1 ? 'dark' : 'light');
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
        model: settings.model || current?.model || 'gpt-3.5-turbo',
        temperature: settings.temperature ?? current?.temperature ?? 0.7,
        top_p: settings.top_p ?? current?.top_p ?? 1,
        systemPrompt: settings.systemPrompt || current?.systemPrompt || '',
        darkMode: settings.darkMode ?? current?.darkMode ?? 0,
        languageIsEnglish: settings.languageIsEnglish ?? current?.languageIsEnglish ?? 1
      };

      await this.settingsRepository.save(updated);
      
      // Apply theme if changed
      if (settings.darkMode !== undefined) {
        this.themeService.setTheme(settings.darkMode === 1 ? 'dark' : 'light');
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
   * Get available LLM models
   */
  async getAvailableModels(): Promise<string[]> {
    try {
      // This still uses the API service directly as it's not settings data
      const response = await fetch('/api/llms', {
        credentials: 'include'
      });
      
      if (!response.ok) {
        throw new Error('Failed to fetch models');
      }
      
      return await response.json();
    } catch (error) {
      console.error('Failed to fetch models:', error);
      // Return default models as fallback
      return [
        'gpt-3.5-turbo',
        'gpt-4',
        'claude-2',
        'claude-instant-1'
      ];
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

    return {
      ...settings,
      isEnglish: settings.languageIsEnglish === 1,
      isDarkMode: settings.darkMode === 1
    };
  }
}