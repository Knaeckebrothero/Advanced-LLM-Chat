import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { MatDialogRef } from '@angular/material/dialog';
import { SettingsStateService } from '../services/settings-state.service';
import { AppSettings } from '../models/settings.model';
import { Language, Theme } from '../models/enum';
import { Observable } from 'rxjs';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [CommonModule, MatIconModule],
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
})
export class SettingsComponent implements OnInit {
  settings$: Observable<AppSettings | null>;

  themeOptions = [
    { value: Theme.Light, icon: 'light_mode', label: 'Light' },
    { value: Theme.Dark, icon: 'dark_mode', label: 'Dark' },
    { value: Theme.Auto, icon: 'brightness_auto', label: 'Auto' },
  ];

  languageOptions = [
    { value: Language.English, label: 'EN' },
    { value: Language.German, label: 'DE' },
  ];

  constructor(
    private settingsState: SettingsStateService,
    private dialogRef: MatDialogRef<SettingsComponent>
  ) {
    this.settings$ = this.settingsState.settings$;
  }

  ngOnInit(): void {}

  updateTheme(theme: Theme): void {
    this.settingsState.updateSettings({ theme });
  }

  updateLanguage(language: Language): void {
    this.settingsState.updateSettings({ language });
  }

  close(): void {
    this.dialogRef.close();
  }
}
