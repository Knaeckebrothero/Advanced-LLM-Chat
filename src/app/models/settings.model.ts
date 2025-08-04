import {Language, Theme} from "./enum";


/**
 * Settings model shared across the application
 */
export interface Settings {
  theme: Theme;
  language: Language;
}
