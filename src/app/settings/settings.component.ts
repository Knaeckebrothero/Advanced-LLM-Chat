import { Component } from '@angular/core';
import { ThemeService } from '../../styles/themes/theme.service';

@Component({
    selector: 'app-settings',
    standalone: true,
    templateUrl: './settings.component.html',
    styleUrls: ['./settings.component.scss'],
})
export class SettingsComponent {
    isDarkMode = false;

    constructor(private themeService: ThemeService) {
        this.isDarkMode = this.themeService.getCurrentTheme() === 'dark';
    }

    toggleDarkMode(event: Event): void {
        const checked = (event.target as HTMLInputElement).checked;
        this.themeService.setTheme(checked ? 'dark' : 'light');
        this.isDarkMode = checked;
    }
}
