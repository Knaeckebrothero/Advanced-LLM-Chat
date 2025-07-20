import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable, of, firstValueFrom } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { BaseRepository, SyncResult } from './base.repository';
import { DBService } from '../data/db.service';
import { ApiService } from '../services/api.service';
import { Settings } from '../settings/settings.service';
import { environment } from '../environments/environment';

export interface SettingsWithMetadata extends Settings {
  id?: string;
  timestamp?: Date;
  syncHash?: string;
}

@Injectable({
  providedIn: 'root'
})
export class SettingsRepository extends BaseRepository<SettingsWithMetadata> {
  private readonly SETTINGS_KEY = 'app_settings';
  private readonly STORE_NAME = 'settings';
  
  constructor(
    dbService: DBService,
    apiService: ApiService,
    private http: HttpClient
  ) {
    super(dbService, apiService);
    this.loadFromIndexedDB();
  }

  getAll(): Observable<SettingsWithMetadata[]> {
    return this.cache$.asObservable();
  }

  getById(id: string | number): Observable<SettingsWithMetadata | null> {
    return this.cache$.pipe(
      map(settings => settings.find(s => s.id === id) || null)
    );
  }

  getCurrent(): Observable<SettingsWithMetadata | null> {
    return this.cache$.pipe(
      map(settings => settings.length > 0 ? settings[0] : null)
    );
  }

  async save(settings: SettingsWithMetadata): Promise<SettingsWithMetadata> {
    settings.id = this.SETTINGS_KEY;
    settings.timestamp = new Date();
    
    try {
      await this.saveToIndexedDB(settings);
      
      if (await this.isOnline()) {
        await this.saveToBackend(settings);
      }
      
      this.updateCache([settings]);
      return settings;
    } catch (error) {
      console.error('Failed to save settings:', error);
      throw error;
    }
  }

  async delete(id: string | number): Promise<void> {
    throw new Error('Settings cannot be deleted');
  }

  async computeHash(settings: SettingsWithMetadata[]): Promise<string> {
    if (settings.length === 0) return '';
    
    const current = settings[0];
    const data = JSON.stringify({
      model: current.model,
      temperature: current.temperature,
      top_p: current.top_p,
      systemPrompt: current.systemPrompt,
      darkMode: current.darkMode,
      languageIsEnglish: current.languageIsEnglish
    });
    
    return this.computeHashFromString(data);
  }

  async sync(): Promise<SyncResult> {
    this.isSyncing$.next(true);
    
    try {
      const localSettings = this.cache$.getValue();
      const localHash = await this.computeHash(localSettings);
      
      const remoteSettings = await this.fetchFromBackend();
      if (!remoteSettings) {
        return {
          success: false,
          itemsUpdated: 0,
          errors: ['Failed to fetch settings from backend']
        };
      }
      
      const remoteHash = await this.computeHash([remoteSettings]);
      
      if (localHash !== remoteHash) {
        remoteSettings.id = this.SETTINGS_KEY;
        remoteSettings.timestamp = new Date();
        remoteSettings.syncHash = remoteHash;
        
        await this.saveToIndexedDB(remoteSettings);
        this.updateCache([remoteSettings]);
        this.lastSyncTime = new Date();
        
        return {
          success: true,
          itemsUpdated: 1
        };
      }
      
      this.lastSyncTime = new Date();
      return {
        success: true,
        itemsUpdated: 0
      };
    } catch (error) {
      console.error('Settings sync failed:', error);
      return {
        success: false,
        itemsUpdated: 0,
        errors: [error instanceof Error ? error.message : 'Unknown error']
      };
    } finally {
      this.isSyncing$.next(false);
    }
  }

  private async loadFromIndexedDB(): Promise<void> {
    try {
      const db = await this.dbService.getDb();
      const transaction = db.transaction([this.STORE_NAME], 'readonly');
      const store = transaction.objectStore(this.STORE_NAME);
      
      const result = await store.get(this.SETTINGS_KEY);
      if (result) {
        this.updateCache([result]);
      }
    } catch (error) {
      console.error('Failed to load settings from IndexedDB:', error);
    }
  }

  private async saveToIndexedDB(settings: SettingsWithMetadata): Promise<void> {
    const db = await this.dbService.getDb();
    const transaction = db.transaction([this.STORE_NAME], 'readwrite');
    const store = transaction.objectStore(this.STORE_NAME);
    await store.put(settings);
  }

  private async saveToBackend(settings: SettingsWithMetadata): Promise<void> {
    const settingsDto: Settings = {
      model: settings.model,
      temperature: settings.temperature,
      top_p: settings.top_p,
      systemPrompt: settings.systemPrompt,
      darkMode: settings.darkMode,
      languageIsEnglish: settings.languageIsEnglish
    };
    
    const response = await firstValueFrom(
      this.http.put(`${environment.apiUrl}/api/settings`, settingsDto, { 
        withCredentials: true 
      })
    );
  }

  private async fetchFromBackend(): Promise<SettingsWithMetadata | null> {
    try {
      const settings = await firstValueFrom(
        this.http.get<Settings>(`${environment.apiUrl}/api/settings`, { 
          withCredentials: true 
        })
      );
      return settings as SettingsWithMetadata;
    } catch (error) {
      console.error('Failed to fetch settings from backend:', error);
      return null;
    }
  }

  private async isOnline(): Promise<boolean> {
    try {
      const response = await fetch(`${environment.apiUrl}/api/auth/me`, {
        method: 'GET',
        credentials: 'include'
      });
      return response.ok;
    } catch {
      return false;
    }
  }
}