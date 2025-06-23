import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

// Angular Material Modules
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatDialogRef } from '@angular/material/dialog';

import { SettingsService, Settings } from './settings.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSlideToggleModule,
    MatButtonModule,
    MatIconModule
  ],
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss']
})
export class SettingsComponent implements OnInit {
  // Initial default values in case loading fails
  settings: Settings = {
    model: 'GPT 4o',
    temperature: 0.5,
    top_p: 0.5,
    systemPrompt: '',
    darkMode: 0,
    languageIsEnglish: 0
  };

  models = ['GPT 3.5', 'GPT 4', 'GPT 4o'];
  temperatures: number[] = [0.1, 0.3, 0.5, 0.7, 0.9];
  topPValues: number[] = [0.1, 0.3, 0.5, 0.7, 0.9];

  constructor(
    private settingsService: SettingsService,
    private dialogRef: MatDialogRef<SettingsComponent>
  ) {}

  ngOnInit(): void {
    this.settingsService.getSettings().subscribe({
      next: (data: Settings) => {
        this.settings = {
          ...data,
          darkMode: data.darkMode ? 1 : 0,
          languageIsEnglish: data.languageIsEnglish ? 1 : 0
        };
        this.applyDarkMode();
      },
      error: () => {
        const local = this.settingsService.loadLocal();
        if (local) {
          this.settings = {
            ...local,
            darkMode: local.darkMode ? 1 : 0,
            languageIsEnglish: local.languageIsEnglish ? 1 : 0
          };
          this.applyDarkMode();
        }
      }
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
    console.log('Language switched to:', lang);
    // Optional: persist or trigger i18n switch
  }

  closeAndSave(): void {
    // Save to backend
    this.settingsService.saveSettings({
      ...this.settings,
      // convert boolean to 0/1 explicitly if needed
      darkMode: this.settings.darkMode ? 1 : 0,
      languageIsEnglish: this.settings.languageIsEnglish ? 1 : 0
    }).subscribe();

    // Save locally
    this.settingsService.saveLocal(this.settings);
    this.dialogRef.close(this.settings);
  }

  resetSettings(): void {
    this.settings = {
      model: 'GPT 4o',
      temperature: 0.5,
      top_p: 0.5,
      systemPrompt: '',
      darkMode: 0,
      languageIsEnglish: 0
    };
    this.applyDarkMode();
  }
}
