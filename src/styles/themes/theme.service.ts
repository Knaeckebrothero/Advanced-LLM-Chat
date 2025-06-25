import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private currentTheme: 'light' | 'dark' | 'os' = 'os'; // Standard
  private effectiveTheme$: BehaviorSubject<'light' | 'dark'>;

  constructor() {
    // Initialisiere Theme bei Start
    const initialTheme = this.getEffectiveTheme();
    this.effectiveTheme$ = new BehaviorSubject(initialTheme);
    this.applyTheme(initialTheme);

    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e: MediaQueryListEvent) => {
      if (this.currentTheme === 'os') {
        const newTheme = e.matches ? 'dark' : 'light';
        this.applyTheme(newTheme);
        this.effectiveTheme$.next(newTheme); // Notify subscribers of the change
      }
    });
  }

  setTheme(theme: 'light' | 'dark' | 'os'): void {
    this.currentTheme = theme;
    const effective = this.getEffectiveTheme();
    this.applyTheme(effective);
    this.effectiveTheme$.next(effective); // Notify subscribers of the change
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

  // This method exposes the theme state as an observable for other components to subscribe to.
  public getEffectiveTheme$(): Observable<'light' | 'dark'> {
    return this.effectiveTheme$.asObservable();
  }
}
