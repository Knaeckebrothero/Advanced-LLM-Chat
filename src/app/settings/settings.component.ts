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
      complete: () => {
        this.onThemeChange();
      }
    });
  }

  onThemeChange(): void {
    this.themeService.setTheme(this.settings.theme);
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

  cancel(): void {
    this.dialogRef.close();
  }
}
