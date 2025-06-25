import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private currentTheme: 'light' | 'dark' | 'os' = 'os'; // Standard

  constructor() {
    // Initialisiere Theme bei Start
    this.applyTheme(this.getEffectiveTheme());
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
      if (this.currentTheme === 'os') {
        this.applyTheme(e.matches ? 'dark' : 'light');
      }
    });
  }

  setTheme(theme: 'light' | 'dark' | 'os'): void {
    this.currentTheme = theme;
    this.applyTheme(this.getEffectiveTheme());
  }

  getCurrentTheme(): 'light' | 'dark' | 'os' {
    return this.currentTheme;
  }

  private getEffectiveTheme(): 'light' | 'dark' {
    if (this.currentTheme === 'os') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    return this.currentTheme;
  }

  public applyTheme(theme: 'light' | 'dark'): void {
    const body = document.body;
    body.classList.remove('light', 'dark');
    body.classList.add(theme);
  }
}
