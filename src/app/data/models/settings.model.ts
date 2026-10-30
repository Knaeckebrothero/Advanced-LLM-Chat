/**
 * Settings Data Models
 * Mirrors backend/models/settings.py
 */

export interface IAppSettings {
  theme: string;
  language: string;
  defaultModelId?: number | null;  // Catalog model for new conversations
  background?: 'none' | 'aurora' | 'ridges' | 'custom';  // Chat background
  backgroundDim?: number;   // 0-80 %
  backgroundBlur?: number;  // 0-20 px
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
