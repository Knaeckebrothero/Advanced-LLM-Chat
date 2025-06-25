import { Component, OnInit } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

// Angular Material Modules
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

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
  // The main object holding the component's state, bound to the template
  settings: Settings = {
    model: 'openai/gpt-4o',
    temperature: 0.5,
    top_p: 0.5,
    systemPrompt: '',
    darkMode: 0,
    languageIsEnglish: 1
  };

  // Arrays for the select dropdowns in the template
  models: string[] = [];
  temperatures: number[] = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0];
  topPValues: number[] = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0];

  private initialSettings!: Settings;
  private readonly defaultSettings: Settings = { ...this.settings }; // Store hardcoded defaults for reset

  constructor(
    private settingsService: SettingsService,
    private statusBar: StatusBarService
  ) {}

  ngOnInit(): void {
    this.loadSettings();
    this.loadLLMs();
  }

  private loadLLMs(): void {
    this.settingsService.getLLMs()
      .then(llms => {
        this.models = llms;
        // If the current model isn't in the list, default to the first one
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
    // Attempt to load from backend first
    this.settingsService.getSettings().subscribe({
      next: (settings) => {
        this.settings = { ...settings };
        this.initialSettings = { ...settings }; // Store for reset functionality
        this.applyDarkMode();
        this.statusBar.showMessage('Settings loaded from server.', 'success');
      },
      error: () => {
        // Fallback to local storage if backend fails
        const local = this.settingsService.loadLocal();
        if (local) {
          this.settings = { ...local };
          this.initialSettings = { ...local };
          this.applyDarkMode();
          this.statusBar.showMessage('Loaded local settings.', 'info');
        } else {
          // If no settings are found, use and store the component's defaults
          this.initialSettings = { ...this.defaultSettings };
          this.settings = { ...this.defaultSettings };
          this.applyDarkMode();
          this.statusBar.showMessage('No settings found. Using defaults.', 'warning');
        }
      },
    });
  }

  toggleTheme(): void {
    this.applyDarkMode();
  }

  private applyDarkMode(): void {
    if (this.settings.darkMode) {
      document.body.classList.add('dark-mode');
    } else {
      document.body.classList.remove('dark-mode');
    }
  }

  toggleLanguage(): void {
    const lang = this.settings.languageIsEnglish ? 'en' : 'de';
    // You can add translation logic here if needed
    console.log('Language switched to:', lang);
  }

  resetSettings(): void {
    // Reset only the specified fields to their hardcoded default values.
    // User-specific settings like model, dark mode, and language are preserved.
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
        this.statusBar.toggleSidenav(); // Close the settings panel
      },
      error: () => {
        this.settingsService.saveLocal(this.settings);
        this.statusBar.showMessage('Failed to save to server. Saved locally.', 'error');
        this.statusBar.toggleSidenav(); // Also close the panel on error
      },
    });
  }
}
