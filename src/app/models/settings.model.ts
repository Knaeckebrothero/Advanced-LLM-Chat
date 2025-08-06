import {Language, Theme} from "./enum";


/**
 * Settings model shared across the application
 */

export interface AppSettings {
  theme: Theme;
  language: Language;
  lastUpdated: number; // Unix timestamp
}
