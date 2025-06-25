import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private currentTheme: 'light' | 'dark' = 'light'; // Standard

  constructor() {
    // Initialisiere Theme bei Start
    this.applyTheme(this.currentTheme);
  }

  setTheme(theme: 'light' | 'dark'): void {
    this.currentTheme = theme;
    this.applyTheme(theme);
  }

  getCurrentTheme(): 'light' | 'dark' {
    return this.currentTheme;
  }

  public applyTheme(theme: 'light' | 'dark'): void {
    const body = document.body;
    body.classList.remove('light', 'dark');
    body.classList.add(theme);
  }
}
