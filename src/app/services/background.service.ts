import { Inject, Injectable, OnDestroy } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { BehaviorSubject, combineLatest, Subscription } from 'rxjs';
import { DBService } from '../data/db.service';
import { SettingsStateService } from './settings-state.service';
import {
  AppSettings,
  BACKGROUND_BLUR_MAX,
  BACKGROUND_DIM_MAX,
  BackgroundChoice,
} from '../models/settings.model';

/** The built-in chat backgrounds (src/assets/backgrounds). */
export const BUILT_IN_BACKGROUNDS: Record<Exclude<BackgroundChoice, 'none' | 'custom'>, string> = {
  aurora: 'assets/backgrounds/aurora.svg',
  ridges: 'assets/backgrounds/ridges.svg',
};

export const DEFAULT_BACKGROUND_DIM = 25;
export const DEFAULT_BACKGROUND_BLUR = 0;

const IMAGE_KEY = 'background-image';
const MAX_IMAGE_SIDE = 2560;                 // Larger images are scaled down before storing
const MAX_UNSCALED_BYTES = 3 * 1024 * 1024;  // Smaller images within MAX_IMAGE_SIDE are stored as they are
const MAX_INPUT_BYTES = 40 * 1024 * 1024;

/** Slider values shown while dragging, before they are saved. */
interface BackgroundPreview {
  dim?: number;
  blur?: number;
}

/**
 * Applies the chat background from the user settings.
 *
 * Sets --user-background-image, --user-background-dim and --user-background-blur
 * on the root element and the class has-background-image on the body, which the
 * content area (app.component.scss) and the chat components use. The user's own
 * image is kept in IndexedDB and never uploaded.
 */
@Injectable({ providedIn: 'root' })
export class BackgroundService implements OnDestroy {
  private customImageUrlSubject = new BehaviorSubject<string | null>(null);
  /** Object URL of the user's own image in this browser, or null. */
  readonly customImageUrl$ = this.customImageUrlSubject.asObservable();

  private previewSubject = new BehaviorSubject<BackgroundPreview>({});
  private subscription: Subscription;

  constructor(
    @Inject(DOCUMENT) private document: Document,
    private dbService: DBService,
    private settingsState: SettingsStateService
  ) {
    this.subscription = combineLatest([
      this.settingsState.settings$,
      this.customImageUrlSubject,
      this.previewSubject,
    ]).subscribe(([settings, customUrl, preview]) => this.apply(settings, customUrl, preview));
    this.loadCustomImage();
  }

  ngOnDestroy(): void {
    this.subscription.unsubscribe();
    this.setObjectUrl(null);
  }

  /** Absolute URL of a built-in background, for CSS and thumbnails. */
  builtInUrl(choice: keyof typeof BUILT_IN_BACKGROUNDS): string {
    return new URL(BUILT_IN_BACKGROUNDS[choice], this.document.baseURI).href;
  }

  /** Show slider values right away while dragging; they are saved separately on release. */
  preview(preview: BackgroundPreview): void {
    this.previewSubject.next(preview);
  }

  clearPreview(): void {
    this.previewSubject.next({});
  }

  /**
   * Use an image file as the chat background. Large images are scaled down;
   * the image stays in this browser.
   *
   * @throws Error('not-an-image') or Error('too-large') for unusable files.
   */
  async setCustomImage(file: File): Promise<void> {
    if (!file.type.startsWith('image/')) {
      throw new Error('not-an-image');
    }
    if (file.size > MAX_INPUT_BYTES) {
      throw new Error('too-large');
    }

    const blob = await this.prepareImage(file);
    const db = await this.dbService.getDb();
    await db.put('appearance', { id: IMAGE_KEY, blob, updatedAt: Date.now() });
    this.setObjectUrl(blob);
    await this.settingsState.updateSettings({ background: 'custom' });
  }

  /** Delete the user's own image; a chat that used it falls back to no background. */
  async removeCustomImage(): Promise<void> {
    const db = await this.dbService.getDb();
    await db.delete('appearance', IMAGE_KEY);
    this.setObjectUrl(null);
    if (this.settingsState.getCurrentSettings().background === 'custom') {
      await this.settingsState.updateSettings({ background: 'none' });
    }
  }

  private async loadCustomImage(): Promise<void> {
    try {
      const db = await this.dbService.getDb();
      const entry = await db.get('appearance', IMAGE_KEY);
      this.setObjectUrl(entry?.blob ?? null);
    } catch (error) {
      console.warn('Could not load the background image from IndexedDB', error);
    }
  }

  private setObjectUrl(blob: Blob | null): void {
    const previous = this.customImageUrlSubject.value;
    this.customImageUrlSubject.next(blob ? URL.createObjectURL(blob) : null);
    if (previous) {
      URL.revokeObjectURL(previous);
    }
  }

  /** Scale large images down to MAX_IMAGE_SIDE and store them as JPEG. */
  private async prepareImage(file: File): Promise<Blob> {
    let bitmap: ImageBitmap;
    try {
      bitmap = await createImageBitmap(file);
    } catch {
      // Formats the browser can't decode into a bitmap (e.g. some SVGs) are kept as they are
      if (file.size <= MAX_UNSCALED_BYTES) {
        return file;
      }
      throw new Error('not-an-image');
    }

    const scale = Math.min(1, MAX_IMAGE_SIDE / Math.max(bitmap.width, bitmap.height));
    if (scale === 1 && file.size <= MAX_UNSCALED_BYTES) {
      bitmap.close();
      return file;
    }

    const canvas = this.document.createElement('canvas');
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();

    return new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        result => (result ? resolve(result) : reject(new Error('not-an-image'))),
        'image/jpeg',
        0.88
      )
    );
  }

  private apply(settings: AppSettings, customUrl: string | null, preview: BackgroundPreview): void {
    const root = this.document.documentElement;
    const body = this.document.body;
    const choice = settings.background ?? 'none';

    let imageUrl: string | null = null;
    if (choice === 'custom') {
      imageUrl = customUrl;  // None on devices without the image
    } else if (choice !== 'none' && BUILT_IN_BACKGROUNDS[choice]) {
      imageUrl = this.builtInUrl(choice);
    }

    if (!imageUrl) {
      root.style.removeProperty('--user-background-image');
      root.style.removeProperty('--user-background-dim');
      root.style.removeProperty('--user-background-blur');
      body.classList.remove('has-background-image');
      return;
    }

    const dim = clamp(preview.dim ?? settings.backgroundDim ?? DEFAULT_BACKGROUND_DIM, 0, BACKGROUND_DIM_MAX);
    const blur = clamp(preview.blur ?? settings.backgroundBlur ?? DEFAULT_BACKGROUND_BLUR, 0, BACKGROUND_BLUR_MAX);
    root.style.setProperty('--user-background-image', `url("${imageUrl}")`);
    root.style.setProperty('--user-background-dim', String(dim / 100));
    root.style.setProperty('--user-background-blur', `${blur}px`);
    body.classList.add('has-background-image');
  }
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, Math.round(value)));
}
