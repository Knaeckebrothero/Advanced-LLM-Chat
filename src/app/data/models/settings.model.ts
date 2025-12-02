/**
 * Settings Data Models
 * Mirrors backend/models/settings.py
 */

export interface IAppSettings {
  theme: string;
  language: string;
}

export interface IAppSettingsWithMeta extends IAppSettings {
  lastUpdated: number;
}

// Extended settings for frontend-specific options
export interface IUserSettings extends IAppSettings {
  // LLM settings
  selectedModel?: string;
  temperature?: number;
  topP?: number;
  systemPrompt?: string;

  // UI settings
  sidebarCollapsed?: boolean;
  messageDisplayMode?: 'compact' | 'comfortable';

  // Recording settings
  isHoldToRecord?: boolean;
  maxRecordingDuration?: number;
}
