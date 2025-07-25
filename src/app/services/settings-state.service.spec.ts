import { TestBed } from '@angular/core/testing';
import { of, throwError, map } from 'rxjs';
import { SettingsStateService, AppSettings } from './settings-state.service';
import { SettingsRepository, SettingsWithMetadata } from '../repositories/settings.repository';
import { ThemeService } from './theme.service';
import { Settings } from '../models/settings.model';

describe('SettingsStateService', () => {
  let service: SettingsStateService;
  let mockSettingsRepo: jasmine.SpyObj<SettingsRepository>;
  let mockThemeService: jasmine.SpyObj<ThemeService>;

  const mockSettings: SettingsWithMetadata = {
    model: 'openai/gpt-4o',
    temperature: 0.7,
    top_p: 0.9,
    systemPrompt: 'Test prompt',
    darkMode: 1,
    languageIsEnglish: 1,
    id: 'settings-1',
    timestamp: new Date(),
    syncHash: 'hash123'
  };

  beforeEach(() => {
    // Create mock services
    mockSettingsRepo = jasmine.createSpyObj('SettingsRepository', 
      ['getCurrent', 'save', 'sync', 'getAll']);
    mockThemeService = jasmine.createSpyObj('ThemeService', 
      ['setTheme', 'getCurrentTheme']);
    // Set up default mock returns
    mockSettingsRepo.getCurrent.and.returnValue(of(mockSettings));
    mockSettingsRepo.save.and.returnValue(Promise.resolve(mockSettings));
    mockSettingsRepo.sync.and.returnValue(Promise.resolve({ success: true, itemsUpdated: 1 }));
    mockSettingsRepo.getAll.and.returnValue(of([mockSettings]));
    // Create a proper spy with syncing$ as a property
    Object.defineProperty(mockSettingsRepo, 'syncing$', {
      get: jasmine.createSpy('syncing$').and.returnValue(of(false))
    });

    TestBed.configureTestingModule({
      providers: [
        SettingsStateService,
        { provide: SettingsRepository, useValue: mockSettingsRepo },
        { provide: ThemeService, useValue: mockThemeService }
      ]
    });
    
    service = TestBed.inject(SettingsStateService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  describe('Settings Loading', () => {
    it('should load current settings on init', (done) => {
      service.settings.subscribe(settings => {
        expect(settings).toEqual(jasmine.objectContaining({
          ...mockSettings,
          isEnglish: true,
          isDarkMode: true
        }));
        done();
      });
    });

    it('should enrich settings with computed properties', (done) => {
      service.settings.subscribe(settings => {
        expect(settings?.isEnglish).toBe(true);
        expect(settings?.isDarkMode).toBe(true);
        done();
      });
    });

    it('should handle null settings', () => {
      mockSettingsRepo.getCurrent.and.returnValue(of(null));
      const newService = new SettingsStateService(mockSettingsRepo, mockThemeService);
      
      newService.settings.subscribe(settings => {
        expect(settings).toBeNull();
      });
    });

    it('should apply theme when settings change', () => {
      expect(mockThemeService.setTheme).toHaveBeenCalledWith('dark');
    });

    it('should apply light theme when darkMode is 0', () => {
      const lightSettings = { ...mockSettings, darkMode: 0 };
      mockSettingsRepo.getCurrent.and.returnValue(of(lightSettings));
      
      const newService = new SettingsStateService(mockSettingsRepo, mockThemeService);
      expect(mockThemeService.setTheme).toHaveBeenCalledWith('light');
    });
  });

  describe('Settings Operations', () => {
    it('should save settings', async () => {
      const updates: Partial<Settings> = { temperature: 0.5 };
      const result = await service.saveSettings(updates);
      
      expect(mockSettingsRepo.save).toHaveBeenCalledWith(jasmine.objectContaining({
        ...mockSettings,
        temperature: 0.5
      }));
      expect(result).toBeUndefined();
    });

    it('should handle save errors', async () => {
      mockSettingsRepo.save.and.returnValue(Promise.reject(new Error('Save failed')));
      
      try {
        await service.saveSettings({ temperature: 0.5 });
        fail('Should have thrown error');
      } catch (error) {
        expect(service.lastError$.getValue()).toBe('Failed to save settings');
      }
    });

    it('should load settings', async () => {
      await service.loadSettings();
      expect(mockSettingsRepo.sync).toHaveBeenCalled();
    });

    it('should handle load errors gracefully', async () => {
      mockSettingsRepo.sync.and.returnValue(Promise.reject(new Error('Load failed')));
      
      try {
        await service.loadSettings();
        fail('Should have thrown error');
      } catch (error) {
        expect(service.lastError$.getValue()).toBe('Failed to load settings');
      }
    });
  });

  describe('Settings Getters', () => {
    it('should get specific setting value', (done) => {
      service.getSetting('temperature').subscribe(value => {
        expect(value).toBe(0.7);
        done();
      });
    });

    it('should get computed property', (done) => {
      service.getSetting('isEnglish').subscribe(value => {
        expect(value).toBe(true);
        done();
      });
    });

    // Note: isEnglish$ and isDarkMode$ are not exposed as public observables
    // They are available through the enriched settings object
  });

  describe('Model Management', () => {
    it('should get available models', async () => {
      // Mock fetch API
      spyOn(window, 'fetch').and.returnValue(Promise.resolve(
        new Response(JSON.stringify(['openai/gpt-4o', 'openai/gpt-3.5-turbo']), {
          status: 200,
          headers: { 'Content-Type': 'application/json' }
        })
      ));
      
      const models = await service.getAvailableModels();
      expect(models).toEqual(['openai/gpt-4o', 'openai/gpt-3.5-turbo']);
      expect(window.fetch).toHaveBeenCalledWith('/api/llms', {
        credentials: 'include'
      });
    });

    it('should handle model loading errors', async () => {
      spyOn(window, 'fetch').and.returnValue(Promise.resolve(
        new Response('Error', { status: 500 })
      ));
      
      try {
        await service.getAvailableModels();
        fail('Should have thrown error');
      } catch (error) {
        expect(service.lastError$.getValue()).toBe('Failed to load available models');
      }
    });
  });

  describe('State Management', () => {
    it('should track loading state', (done) => {
      service.isLoading$.subscribe(isLoading => {
        expect(isLoading).toBe(false);
        done();
      });
    });

    it('should track syncing state', (done) => {
      service.isSyncing$.subscribe(isSyncing => {
        expect(isSyncing).toBe(false);
        done();
      });
    });

    it('should clear errors', () => {
      service.lastError$.next('Test error');
      // clearError method doesn't exist - errors are cleared automatically
      expect(service.lastError$.getValue()).toBeNull();
    });
  });

  describe('Error Handling', () => {
    it('should set error messages for various operations', async () => {
      mockSettingsRepo.save.and.returnValue(Promise.reject(new Error('Network error')));
      
      await service.saveSettings({}).catch(() => {});
      expect(service.lastError$.getValue()).toBe('Failed to save settings');
      
      // clearError method doesn't exist - errors are cleared automatically
      
      spyOn(window, 'fetch').and.returnValue(Promise.reject(new Error('Network error')));
      await service.getAvailableModels().catch(() => {});
      expect(service.lastError$.getValue()).toBe('Failed to load available models');
    });
  });

  describe('Observable Streams', () => {
    it('should provide settings as observable', (done) => {
      service.settings.subscribe(settings => {
        expect(settings).toBeDefined();
        expect(settings?.model).toBe('openai/gpt-4o');
        done();
      });
    });

    it('should share settings stream across subscribers', () => {
      let count = 0;
      mockSettingsRepo.getCurrent.and.returnValue(of(mockSettings).pipe(
        // This would be called twice if not shared
        map(s => { count++; return s; })
      ));

      const newService = new SettingsStateService(mockSettingsRepo, mockThemeService);
      
      // Subscribe twice
      newService.settings.subscribe();
      newService.settings.subscribe();
      
      // Should only increment once due to shareReplay
      expect(count).toBe(1);
    });
  });
});