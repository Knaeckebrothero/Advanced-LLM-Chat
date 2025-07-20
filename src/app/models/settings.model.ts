/**
 * Settings model shared across the application
 */
export interface Settings {
  model: string;
  temperature: number;
  top_p: number;
  systemPrompt: string;
  darkMode: number;
  languageIsEnglish: number;
}