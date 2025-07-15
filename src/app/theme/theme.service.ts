import { Injectable, inject } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { DOCUMENT } from '@angular/common';

export type Theme = 'light' | 'dark' | 'auto';

@Injectable({
  providedIn: 'root'
})
export class ThemeService {
  private document = inject(DOCUMENT);
  private readonly STORAGE_KEY = 'theme-preference';

  private themeSubject = new BehaviorSubject<Theme>('auto');
  public theme$: Observable<Theme> = this.themeSubject.asObservable();

  private mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

  constructor() {
    this.initializeTheme();
    this.setupSystemThemeListener();
  }

  private initializeTheme(): void {
    const storedTheme = localStorage.getItem(this.STORAGE_KEY) as Theme;
    const initialTheme = storedTheme || 'auto';
    this.setTheme(initialTheme);
  }

  private setupSystemThemeListener(): void {
    this.mediaQuery.addEventListener('change', (e) => {
      if (this.themeSubject.value === 'auto') {
        this.applyThemeToDOM(e.matches ? 'dark' : 'light');
      }
    });
  }

  public setTheme(theme: Theme): void {
    this.themeSubject.next(theme);
    localStorage.setItem(this.STORAGE_KEY, theme);

    const effectiveTheme = this.getEffectiveTheme(theme);
    this.applyThemeToDOM(effectiveTheme);
  }

  public getEffectiveTheme(theme?: Theme): 'light' | 'dark' {
    const currentTheme = theme || this.themeSubject.value;

    if (currentTheme === 'auto') {
      return this.mediaQuery.matches ? 'dark' : 'light';
    }

    return currentTheme;
  }

  private applyThemeToDOM(theme: 'light' | 'dark'): void {
    const body = this.document.body;
    body.classList.remove('theme-light', 'theme-dark');
    body.classList.add(`theme-${theme}`);
  }

  public toggleTheme(): void {
    const themes: Theme[] = ['light', 'dark', 'auto'];
    const currentIndex = themes.indexOf(this.themeSubject.value);
    const nextTheme = themes[(currentIndex + 1) % themes.length];
    this.setTheme(nextTheme);
  }
}
