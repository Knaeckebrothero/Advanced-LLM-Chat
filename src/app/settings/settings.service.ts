import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { ApiService } from '../api/api.service';

// Custom type for the three valid theme options
export type Theme = 'light' | 'dark' | 'os';

// Interface that matches the backend structure with the improved Theme type
export interface Settings {
  model: string;
  temperature: number;
  top_p: number;
  systemPrompt: string;
  theme: Theme; // <-- Replaced 'darkMode' with the specific 'Theme' type
  languageIsEnglish: number;
}

@Injectable({ providedIn: 'root' })
export class SettingsService {
  private readonly API_URL = 'https://localhost:8443/api/settings';
  private readonly LOCAL_KEY = 'user_settings';

  constructor(private http: HttpClient, private apiService: ApiService) {}

  /**
   * Get available LLMs from backend.
   */
  getLLMs(): Promise<string[]> {
    return this.apiService.getLLMs();
  }

  /**
   * Load settings from backend. The return type now ensures the theme
   * property is one of the three valid options.
   */
  getSettings(): Observable<Settings> {
    return this.http.get<Settings>(this.API_URL, { withCredentials: true });
  }

  /**
   * Save settings to backend. The parameter now requires a valid
   * theme property.
   */
  saveSettings(settings: Settings): Observable<any> {
    return this.http.put(this.API_URL, settings, { withCredentials: true });
  }

  /**
   * Load locally stored settings from localStorage.
   */
  loadLocal(): Settings | null {
    const raw = localStorage.getItem(this.LOCAL_KEY);
    return raw ? JSON.parse(raw) : null;
  }

  /**
   * Store settings to localStorage.
   */
  saveLocal(settings: Settings): void {
    localStorage.setItem(this.LOCAL_KEY, JSON.stringify(settings));
  }
}
