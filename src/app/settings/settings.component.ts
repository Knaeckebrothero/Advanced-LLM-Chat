import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDialogRef } from '@angular/material/dialog';

import { SettingsService, Settings } from './settings.service';
import { StatusBarService } from '../status-bar/status-bar.service';
import { ThemeService } from '../../styles/themes/theme.service';

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
  // The main object holding the component's state. This is the single source of truth.
  settings: Settings = {
    model: 'openai/gpt-4o',
    temperature: 0.5,
    top_p: 0.5,
    systemPrompt: '',
    theme: 'os',
    languageIsEnglish: 1
  };

  // REMOVED: The separate 'selectedTheme' property is redundant when using ngModel.

  // Arrays for the select dropdowns in the template
  models: string[] = [];
  temperatures: number[] = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0];
  topPValues: number[] = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0];

  private readonly defaultSettings: Settings = { ...this.settings };

  constructor(
    private settingsService: SettingsService,
    private statusBar: StatusBarService,
    private themeService: ThemeService,
    private dialogRef: MatDialogRef<SettingsComponent>
  ) {
    // Constructor is now cleaner. Initialization happens in ngOnInit/loadSettings.
  }

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
        this.statusBar.showMessage('Settings loaded from server.', 'success');
      },
      error: () => {
        const local = this.settingsService.loadLocal();
        if (local) {
          this.settings = { ...local };
          this.statusBar.showMessage('Loaded local settings.', 'info');
        } else {
          this.settings = { ...this.defaultSettings };
          this.statusBar.showMessage('No settings found. Using defaults.', 'warning');
        }
      },
      // FIXED: Ensure the theme is applied visually after settings are loaded.
      complete: () => {
        this.onThemeChange();
      }
    });
  }

  // REMOVED: The old 'setTheme' method is no longer needed.

  // FIXED: Added the missing 'onThemeChange' method.
  // This is called by the (ngModelChange) event in the template.
  onThemeChange(): void {
    // The 'settings.theme' property is already updated by the ngModel binding.
    // We just need to call the service to apply the new theme.
    this.themeService.setTheme(this.settings.theme);
  }

  onLanguageChange(): void {
    const lang = this.settings.languageIsEnglish ? 'en' : 'de';
    console.log('Language switched to:', lang);
  }

  resetSettings(): void {
    // Preserve theme and language on reset
    const currentTheme = this.settings.theme;
    const currentLang = this.settings.languageIsEnglish;

    this.settings = { ...this.defaultSettings }; // Reset to defaults

    // Restore user's preference
    this.settings.theme = currentTheme;
    this.settings.languageIsEnglish = currentLang;

    this.statusBar.showMessage('Model settings have been reset to default.', 'info');
  }

  closeAndSave(): void {
    this.settingsService.saveSettings(this.settings).subscribe({
      next: () => {
        this.settingsService.saveLocal(this.settings);
        this.statusBar.showMessage('Settings saved successfully.', 'success');
        this.dialogRef.close(this.settings);
      },
      error: () => {
        this.settingsService.saveLocal(this.settings);
        this.statusBar.showMessage('Failed to save to server. Saved locally.', 'error');
        this.dialogRef.close(this.settings);
      },
    });
  }

  // Renamed to be more explicit for the 'x' button's action
  cancel(): void {
    this.dialogRef.close();
  }
}
