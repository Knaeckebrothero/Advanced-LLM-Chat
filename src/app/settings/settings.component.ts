import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, takeUntil } from 'rxjs';

// Angular Material Modules
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatDialogRef } from '@angular/material/dialog';

// New architecture services
import { SettingsStateService, AppSettings } from '../services/settings-state.service';
import { SyncEngineService } from '../repositories/sync-engine.service';
import { StatusBarService } from '../status-bar/status-bar.service';
import { Settings } from '../models/settings.model';
import {Language, Theme} from "../models/enum";

/**
 * Settings component using the new unified data architecture.
 * This demonstrates how components interact with the state services
 * rather than directly with repositories or API services.
 */
@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss']
})
export class SettingsComponent implements OnInit, OnDestroy {
  // Local form model
  settings: Settings = {
    theme: Theme.Auto,
    language: Language.English
  };

  // Loading states from the state service
  isLoading$ = this.settingsState.isLoading$;
  isSyncing$ = this.settingsState.isSyncing$;
  lastError$ = this.settingsState.lastError$;

  // Sync status from sync engine
  syncStatus$ = this.syncEngine.status$;

  private destroy$ = new Subject<void>();
  private initialSettings!: Settings;

  constructor(
    private settingsState: SettingsStateService,
    private syncEngine: SyncEngineService,
    private statusBar: StatusBarService,
    private dialogRef: MatDialogRef<SettingsComponent>
  ) {}

  ngOnInit(): void {
    // Load settings through the state service
    this.loadSettings();

    // Subscribe to settings changes
    this.settingsState.settings
      .pipe(takeUntil(this.destroy$))
      .subscribe(settings => {
        if (settings) {
          this.settings = {
            theme: settings.theme,
            language: settings.language
          };
          this.initialSettings = { ...this.settings };
        }
      });

    // Subscribe to sync errors
    this.settingsState.lastError$
      .pipe(takeUntil(this.destroy$))
      .subscribe(error => {
        if (error) {
          this.statusBar.showMessage(error, 'error');
        }
      });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  private async loadSettings(): Promise<void> {
    try {
      await this.settingsState.loadSettings();
      this.statusBar.showMessage('Settings loaded successfully', 'success');
    } catch (error) {
      this.statusBar.showMessage('Failed to load settings', 'error');
    }
  }

  /**
   * Save settings using the new architecture
   */
  async saveSettings(): Promise<void> {
    try {
      await this.settingsState.saveSettings(this.settings);
      this.initialSettings = { ...this.settings };
      this.statusBar.showMessage('Settings saved successfully', 'success');
    } catch (error) {
      this.statusBar.showMessage('Failed to save settings', 'error');
    }
  }

  /**
   * Force sync with backend
   */
  async syncNow(): Promise<void> {
    try {
      await this.syncEngine.syncNow();
      this.statusBar.showMessage('Sync completed', 'success');
    } catch (error) {
      this.statusBar.showMessage('Sync failed', 'error');
    }
  }

  /**
   * Reset to default settings
   */
  resetToDefaults(): void {
    this.settings = {
      theme: Theme.Auto,
      language: Language.English
    };
    this.statusBar.showMessage('Reset to default settings', 'info');
  }

  /**
   * Check if settings have been modified
   */
  get isDirty(): boolean {
    return JSON.stringify(this.settings) !== JSON.stringify(this.initialSettings);
  }

  /**
   * Toggle theme
   */
  toggleTheme(): void {
    const themes: Theme[] = [Theme.Light, Theme.Dark, Theme.Auto];
    const currentIndex = themes.indexOf(this.settings.theme);
    this.settings.theme = themes[(currentIndex + 1) % themes.length];
  }

  /**
   * Toggle language
   */
  toggleLanguage(): void {
    this.settings.language = this.settings.language === Language.English ? Language.German : Language.English;
  }

  /**
   * Get theme icon based on current theme
   */
  getThemeIcon(): string {
    switch (this.settings.theme) {
      case Theme.Dark:
        return 'dark_mode';
      case Theme.Light:
        return 'light_mode';
      default:
        return 'brightness_auto';
    }
  }

  /**
   * Reset settings (alias for resetToDefaults)
   */
  resetSettings(): void {
    this.resetToDefaults();
  }

  /**
   * Close and save settings
   */
  async closeAndSave(): Promise<void> {
    await this.saveSettings();
    this.dialogRef.close();
  }
}
