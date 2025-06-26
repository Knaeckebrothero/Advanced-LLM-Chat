import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private currentTheme: 'light' | 'dark' | 'os' = 'os';
  private effectiveTheme$: BehaviorSubject<'light' | 'dark'>;

  constructor() {
    // Determine the initial theme but DON'T apply it here yet.
    // AppComponent will call setTheme() almost immediately.
    const initialTheme = this.getEffectiveTheme();
    this.effectiveTheme$ = new BehaviorSubject(initialTheme);
    // REMOVED: this.applyTheme(initialTheme);
    // We let the initial call from AppComponent handle the first application.

    // The listener remains the same.
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e: MediaQueryListEvent) => {
      if (this.currentTheme === 'os') {
        const newTheme = e.matches ? 'dark' : 'light';
        this.applyTheme(newTheme);
        this.effectiveTheme$.next(newTheme);
      }
    });
  }

  setTheme(theme: 'light' | 'dark' | 'os'): void {
    this.currentTheme = theme;
    const effective = this.getEffectiveTheme();
    this.applyTheme(effective);
    this.effectiveTheme$.next(effective);
  }

  // ... rest of the service is unchanged

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
    if (!body.classList.contains(theme)) {
      body.classList.remove('light', 'dark');
      body.classList.add(theme);
    }
  }

  public getEffectiveTheme$(): Observable<'light' | 'dark'> {
    return this.effectiveTheme$.asObservable();
  }
}
