import { Injectable, Inject, Renderer2, RendererFactory2 } from '@angular/core';
import { DOCUMENT } from '@angular/common';

@Injectable({
  providedIn: 'root'
})
export class ThemeService {
  private renderer: Renderer2;
  private currentTheme: string;

  constructor(
    @Inject(DOCUMENT) private document: Document,
    private rendererFactory: RendererFactory2
  ) {
    // We need the renderer to safely manipulate the DOM
    this.renderer = rendererFactory.createRenderer(null, null);
    this.currentTheme = this.getStoredTheme() || 'light'; // Default to light theme
  }

  /**
   * Initializes the theme on application startup.
   * It checks for a saved theme in localStorage or respects the user's system preferences.
   */
  initializeTheme(): void {
    const storedTheme = this.getStoredTheme();
    if (storedTheme) {
      this.setTheme(storedTheme);
    } else {
      // If no theme is stored, check the user's system preference
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      this.setTheme(prefersDark ? 'dark' : 'light');
    }
  }

  /**
   * Sets the application's theme by adding a class to the body element.
   * @param themeName The name of the theme to apply ('light' or 'dark').
   */
  setTheme(themeName: string): void {
    // Remove previous theme classes
    this.renderer.removeClass(this.document.body, 'theme-light');
    this.renderer.removeClass(this.document.body, 'theme-dark');

    // Add the new theme class
    this.renderer.addClass(this.document.body, `theme-${themeName}`);
    this.currentTheme = themeName;

    // Save the user's preference
    this.storeTheme(themeName);
  }

  /**
   * Returns the currently active theme.
   * @returns The current theme name as a string.
   */
  getCurrentTheme(): string {
    return this.currentTheme;
  }

  /**
   * Toggles between the 'light' and 'dark' themes.
   */
  toggleTheme(): void {
    const newTheme = this.currentTheme === 'light' ? 'dark' : 'light';
    this.setTheme(newTheme);
  }

  /**
   * Stores the selected theme in localStorage.
   * @param themeName The theme to store.
   */
  private storeTheme(themeName: string): void {
    localStorage.setItem('app-theme', themeName);
  }

  /**
   * Retrieves the stored theme from localStorage.
   * @returns The stored theme name or null if not found.
   */
  private getStoredTheme(): string | null {
    return localStorage.getItem('app-theme');
  }
}
