import { Component, OnInit } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

// Angular Material Modules
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

// Import the new ThemeService
import { ThemeService } from '../theme/theme.service';
import { SettingsService, Settings } from './settings.service';
import { StatusBarService } from '../status-bar/status-bar.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatIconModule
  ],
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss']
})
export class SettingsComponent implements OnInit {
  settings: Settings = {
    model: 'openai/gpt-4o',
    temperature: 0.5,
    top_p: 0.5,
    systemPrompt: '',
    darkMode: 0,
    languageIsEnglish: 1
  };

  models: string[] = [];
  temperatures: number[] = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0];
  topPValues: number[] = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0];

  private initialSettings!: Settings;
  private readonly defaultSettings: Settings = { ...this.settings };

  constructor(
    private settingsService: SettingsService,
    private statusBar: StatusBarService,
    private themeService: ThemeService // Inject the ThemeService
  ) {}

  ngOnInit(): void {
    this.loadSettings();
    this.loadLLMs();
  }

  private loadLLMs(): void {
    this.settingsService.getLLMs()
      .then(llms => {
        this.models = llms;
        if (llms.length > 0 && !llms.includes(this.settings.model)) {
          this.settings.model = llms[0];
        }
      })
      .catch(err => {
        this.statusBar.showMessage('Failed to load available models.', 'error');
        console.error(err);
      });
  }

  private loadSettings(): void {
    this.settingsService.getSettings().subscribe({
      next: (settings) => {
        this.settings = { ...settings };
        this.initialSettings = { ...settings };
        // Don't override the theme service's stored preference
        // The theme service handles its own persistence
        this.statusBar.showMessage('Settings loaded from server.', 'success');
      },
      error: () => {
        const local = this.settingsService.loadLocal();
        if (local) {
          this.settings = { ...local };
          this.initialSettings = { ...local };
          this.statusBar.showMessage('Loaded local settings.', 'info');
        } else {
          this.initialSettings = { ...this.defaultSettings };
          this.settings = { ...this.defaultSettings };
          this.statusBar.showMessage('No settings found. Using defaults.', 'warning');
        }
      },
    });
  }

  /**
   * Called when the theme toggle is changed.
   * Uses the ThemeService to toggle the theme and updates the settings model.
   */
  toggleTheme(): void {
    this.themeService.toggleTheme();
    // Update the settings object to reflect the change for saving
    const currentTheme = this.themeService.getCurrentTheme();
    // For auto mode, we'll use the effective theme for backward compatibility
    this.settings.darkMode = (currentTheme === 'dark' || 
      (currentTheme === 'auto' && this.themeService.getCurrentEffectiveTheme() === 'dark')) ? 1 : 0;
  }
  
  /**
   * Get the current theme display icon
   */
  getThemeIcon(): string {
    const theme = this.themeService.getCurrentTheme();
    if (theme === 'auto') {
      return 'brightness_auto';
    }
    return theme === 'dark' ? 'dark_mode' : 'light_mode';
  }

  toggleLanguage(): void {
    const lang = this.settings.languageIsEnglish ? 'en' : 'de';
    console.log('Language switched to:', lang);
  }

  resetSettings(): void {
    this.settings.temperature = this.defaultSettings.temperature;
    this.settings.top_p = this.defaultSettings.top_p;
    this.settings.systemPrompt = this.defaultSettings.systemPrompt;
    this.statusBar.showMessage('Model settings have been reset to default.', 'info');
  }

  closeAndSave(): void {
    this.settingsService.saveSettings(this.settings).subscribe({
      next: () => {
        this.settingsService.saveLocal(this.settings);
        this.statusBar.showMessage('Settings saved successfully.', 'success');
        this.statusBar.toggleSidenav();
      },
      error: () => {
        this.settingsService.saveLocal(this.settings);
        this.statusBar.showMessage('Failed to save to server. Saved locally.', 'error');
        this.statusBar.toggleSidenav();
      },
    });
  }
}
