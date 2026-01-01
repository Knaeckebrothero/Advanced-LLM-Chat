import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { SettingsStateService } from './settings-state.service';
import { SettingsRepository } from '../repositories/settings.repository';
import { ThemeService } from './theme.service';
import { TranslateService } from '@ngx-translate/core';
import { AppSettings } from '../models/settings.model';
import { Language, Theme } from '../models/enum';

describe('SettingsStateService', () => {
  let service: SettingsStateService;
  let mockSettingsRepo: jasmine.SpyObj<SettingsRepository>;
  let mockThemeService: jasmine.SpyObj<ThemeService>;
  let mockTranslateService: jasmine.SpyObj<TranslateService>;

  const mockSettings: AppSettings = {
    theme: Theme.Dark,
    language: Language.English,
    lastUpdated: Date.now()
  };

  beforeEach(() => {
    // Create mock services
    mockSettingsRepo = jasmine.createSpyObj('SettingsRepository',
      ['getSettings', 'saveSettings']);
    mockThemeService = jasmine.createSpyObj('ThemeService',
      ['setTheme', 'getCurrentTheme']);
    mockTranslateService = jasmine.createSpyObj('TranslateService',
      ['use']);

    // Set up default mock returns
    mockSettingsRepo.getSettings.and.returnValue(Promise.resolve(mockSettings));
    mockSettingsRepo.saveSettings.and.returnValue(Promise.resolve());

    TestBed.configureTestingModule({
      providers: [
        SettingsStateService,
        { provide: SettingsRepository, useValue: mockSettingsRepo },
        { provide: ThemeService, useValue: mockThemeService },
        { provide: TranslateService, useValue: mockTranslateService }
      ]
    });

    service = TestBed.inject(SettingsStateService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  describe('Settings Loading', () => {
    it('should load settings on initialization', async () => {
      // Wait for async initialization
      await new Promise(resolve => setTimeout(resolve, 10));

      expect(mockSettingsRepo.getSettings).toHaveBeenCalled();
      expect(mockThemeService.setTheme).toHaveBeenCalledWith(Theme.Dark);
      expect(mockTranslateService.use).toHaveBeenCalledWith(Language.English);
    });

    it('should expose settings via settings$ observable', (done) => {
      service.settings$.subscribe(settings => {
        expect(settings).toBeTruthy();
        done();
      });
    });

    it('should provide current settings synchronously', () => {
      const current = service.getCurrentSettings();
      expect(current).toBeTruthy();
    });
  });

  describe('Settings Updates', () => {
    it('should update settings', async () => {
      const updates: Partial<AppSettings> = { theme: Theme.Light };
      await service.updateSettings(updates);

      expect(mockSettingsRepo.saveSettings).toHaveBeenCalled();
      expect(mockThemeService.setTheme).toHaveBeenCalledWith(Theme.Light);
    });

    it('should update language when changed', async () => {
      const updates: Partial<AppSettings> = { language: Language.German };
      await service.updateSettings(updates);

      expect(mockTranslateService.use).toHaveBeenCalledWith(Language.German);
    });

    it('should handle save errors gracefully', async () => {
      mockSettingsRepo.saveSettings.and.returnValue(
        Promise.reject(new Error('Save failed'))
      );

      const updates: Partial<AppSettings> = { theme: Theme.Light };

      try {
        await service.updateSettings(updates);
        fail('Should have thrown error');
      } catch (error) {
        expect(error).toBeTruthy();
      }
    });
  });

  describe('Error Handling', () => {
    it('should use default settings if initial load fails', async () => {
      mockSettingsRepo.getSettings.and.returnValue(
        Promise.reject(new Error('Load failed'))
      );

      // Create a new service instance to trigger initialization
      const newService = new SettingsStateService(
        mockSettingsRepo,
        mockThemeService,
        mockTranslateService
      );

      // Wait for async initialization
      await new Promise(resolve => setTimeout(resolve, 10));

      const current = newService.getCurrentSettings();
      expect(current).toBeTruthy();
      expect(current.theme).toBe(Theme.Auto);
      expect(current.language).toBe(Language.English);
    });
  });
});
