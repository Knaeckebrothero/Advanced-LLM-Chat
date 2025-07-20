import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, takeUntil } from 'rxjs';

// Angular Material Modules
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

// New architecture services
import { SettingsStateService, AppSettings } from '../services/settings-state.service';
import { SyncEngineService } from '../repositories/sync-engine.service';
import { StatusBarService } from '../status-bar/status-bar.service';
import { Settings } from './settings.service';

/**
 * Settings component using the new unified data architecture.
 * This demonstrates how components interact with the state services
 * rather than directly with repositories or API services.
 */
@Component({
  selector: 'app-settings-new',
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
export class SettingsNewComponent implements OnInit, OnDestroy {
  // Local form model
  settings: Settings = {
    model: 'openai/gpt-4o',
    temperature: 0.5,
    top_p: 0.5,
    systemPrompt: '',
    darkMode: 0,
    languageIsEnglish: 1
  };

  // UI state
  models: string[] = [];
  temperatures: number[] = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0];
  topPValues: number[] = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0];
  
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
    private statusBar: StatusBarService
  ) {}

  ngOnInit(): void {
    // Load settings through the state service
    this.loadSettings();
    this.loadAvailableModels();
    
    // Subscribe to settings changes
    this.settingsState.settings
      .pipe(takeUntil(this.destroy$))
      .subscribe(settings => {
        if (settings) {
          this.settings = {
            model: settings.model,
            temperature: settings.temperature,
            top_p: settings.top_p,
            systemPrompt: settings.systemPrompt,
            darkMode: settings.darkMode,
            languageIsEnglish: settings.languageIsEnglish
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

  private async loadAvailableModels(): Promise<void> {
    try {
      this.models = await this.settingsState.getAvailableModels();
      if (this.models.length > 0 && !this.models.includes(this.settings.model)) {
        this.settings.model = this.models[0];
      }
    } catch (error) {
      this.statusBar.showMessage('Failed to load available models', 'error');
      console.error(error);
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
      model: 'openai/gpt-4o',
      temperature: 0.5,
      top_p: 0.5,
      systemPrompt: '',
      darkMode: 0,
      languageIsEnglish: 1
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
    this.settings.darkMode = this.settings.darkMode === 1 ? 0 : 1;
  }

  /**
   * Toggle language
   */
  toggleLanguage(): void {
    this.settings.languageIsEnglish = this.settings.languageIsEnglish === 1 ? 0 : 1;
  }
}