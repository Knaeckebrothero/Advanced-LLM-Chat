import {Language, Theme} from "./enum";

/**
 * Chat background: none, one of the built-in images, or an image the user picked,
 * which is kept in this browser only (other devices then show no image).
 */
export type BackgroundChoice = 'none' | 'aurora' | 'ridges' | 'custom';

export const BACKGROUND_DIM_MAX = 80;  // %
export const BACKGROUND_BLUR_MAX = 20; // px

/**
 * Guided: you edit your own messages, and an edited message is answered again.
 * Manual: you edit any message (an answer only in its text) and insert messages; nothing is generated.
 */
export type EditingMode = 'guided' | 'manual';

/**
 * Settings model shared across the application
 */

export interface AppSettings {
  theme: Theme;
  language: Language;
  lastUpdated: number; // Unix timestamp
  defaultModelId?: number | null; // Catalog model for new conversations (null = first available)
  background?: BackgroundChoice;  // Chat background (default 'none')
  backgroundDim?: number;         // 0-80 %: how much the theme background color covers the image
  backgroundBlur?: number;        // 0-20 px
  editingMode?: EditingMode;      // default 'guided'
}
