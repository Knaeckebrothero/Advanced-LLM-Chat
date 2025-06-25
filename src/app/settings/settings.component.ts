import { Component } from '@angular/core';
import { ThemeService } from '../../styles/themes/theme.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  templateUrl: './settings.component.html',
  styleUrls: ['./settings.component.scss'],
})
export class SettingsComponent {
  selectedTheme: 'light' | 'dark' | 'os';

  constructor(private themeService: ThemeService) {
    this.selectedTheme = this.themeService.getCurrentTheme();
  }

  setTheme(event: Event): void {
    const theme = (event.target as HTMLInputElement).value as 'light' | 'dark' | 'os';
    this.themeService.setTheme(theme);
    this.selectedTheme = theme;
  }
}
