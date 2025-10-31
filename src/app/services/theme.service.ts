import { Injectable, Inject, Renderer2, RendererFactory2 } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { BehaviorSubject, Observable } from 'rxjs';
import {Theme} from "../models/enum";

@Injectable({
  providedIn: 'root'
})
export class ThemeService {
  private renderer: Renderer2;
  private readonly STORAGE_KEY = 'theme-preference';

  private themeSubject = new BehaviorSubject<Theme>(Theme.Auto);
  public theme$: Observable<Theme> = this.themeSubject.asObservable();

  private mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

  constructor(
    @Inject(DOCUMENT) private document: Document,
    private rendererFactory: RendererFactory2
  ) {
    this.renderer = rendererFactory.createRenderer(null, null);
    this.initializeTheme();
    this.setupSystemThemeListener();
  }

   initializeTheme(): void {
    const storedTheme = this.getStoredTheme() as Theme;
    const initialTheme = storedTheme || Theme.Auto;
    this.setTheme(initialTheme);
  }

  private setupSystemThemeListener(): void {
    this.mediaQuery.addEventListener('change', (e) => {
      if (this.themeSubject.value === Theme.Auto) {
        this.applyThemeToDOM(e.matches ? 'dark' : 'light');
      }
    });
  }

  public setTheme(theme: Theme): void {
    this.themeSubject.next(theme);
    this.storeTheme(theme);

    const effectiveTheme = this.getEffectiveTheme(theme);
    this.applyThemeToDOM(effectiveTheme);
  }

  public getEffectiveTheme(theme?: Theme): 'light' | 'dark' {
    const currentTheme = theme || this.themeSubject.value;

    if (currentTheme === Theme.Auto) {
      return this.mediaQuery.matches ? 'dark' : 'light';
    }

    return currentTheme;
  }

  private applyThemeToDOM(theme: 'light' | 'dark'): void {
    const body = this.document.body;
    this.renderer.removeClass(body, 'theme-light');
    this.renderer.removeClass(body, 'theme-dark');
    this.renderer.addClass(body, `theme-${theme}`);

    // Mark as initialized after first theme application to enable transitions
    if (!body.classList.contains('theme-initialized')) {
      setTimeout(() => {
        this.renderer.addClass(body, 'theme-initialized');
      }, 100);
    }
  }

  public toggleTheme(): void {
    const themes: Theme[] = [Theme.Light, Theme.Dark, Theme.Auto];
    const currentIndex = themes.indexOf(this.themeSubject.value);
    const nextTheme = themes[(currentIndex + 1) % themes.length];
    this.setTheme(nextTheme);
  }

  /**
   * Returns the currently active theme preference (light, dark, or auto).
   * @returns The current theme preference as a string.
   */
  public getCurrentTheme(): Theme {
    return this.themeSubject.value;
  }

  /**
   * Returns the effective theme being displayed (light or dark).
   * @returns The actual theme being displayed.
   */
  public getCurrentEffectiveTheme(): 'light' | 'dark' {
    return this.getEffectiveTheme();
  }

  /**
   * Stores the selected theme in localStorage.
   * @param themeName The theme to store.
   */
  private storeTheme(themeName: string): void {
    localStorage.setItem(this.STORAGE_KEY, themeName);
  }

  /**
   * Retrieves the stored theme from localStorage.
   * @returns The stored theme name or null if not found.
   */
  private getStoredTheme(): string | null {
    return localStorage.getItem(this.STORAGE_KEY);
  }
}
