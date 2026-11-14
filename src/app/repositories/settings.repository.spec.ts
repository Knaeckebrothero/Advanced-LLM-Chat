import { SettingsRepository } from './settings.repository';
import { DBService } from '../data/db.service';
import { ApiService } from '../services/api.service';
import { AppSettings } from '../models/settings.model';
import { Language, Theme } from '../models/enum';

describe('SettingsRepository', () => {
  let repository: SettingsRepository;
  let stored: Record<string, unknown>[];
  let api: jasmine.SpyObj<ApiService>;

  const settings: AppSettings = {
    theme: Theme.Dark,
    language: Language.English,
    lastUpdated: 1000,
    autoHidePrompt: "the server's text",
  };

  beforeEach(() => {
    stored = [];
    const db = { put: (_store: string, value: Record<string, unknown>) => { stored.push(value); return Promise.resolve(); } };
    const dbService = { getDb: () => Promise.resolve(db) } as unknown as DBService;
    api = jasmine.createSpyObj('ApiService', ['saveSettings']);
    api.saveSettings.and.returnValue(Promise.resolve());
    repository = new SettingsRepository(dbService, api);
  });

  it('should send autoHidePrompt only when it changed, and keep it locally either way', async () => {
    await repository.saveSettings(settings);
    const sent = api.saveSettings.calls.mostRecent().args[0];
    expect('autoHidePrompt' in sent).toBeFalse();
    expect(sent.theme).toBe(Theme.Dark);
    expect(stored[0]['autoHidePrompt']).toBe("the server's text");

    await repository.saveSettings({ ...settings, autoHidePrompt: '' }, true);
    expect(api.saveSettings.calls.mostRecent().args[0].autoHidePrompt).toBe('');
  });
});
