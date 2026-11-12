import { Injectable } from '@angular/core';
import { FilePreviewSize } from '../data/models/file.model';
import { ApiService } from './api.service';

// Previews kept in memory; the oldest go first
const MAX_PREVIEWS = 300;

/**
 * The preview images of stored files (GET /api/files/{id}/thumbnail), as object URLs for <img>.
 * They are fetched with the session like every API call, since the browser may only show images
 * from the app's own address or ones the app loaded itself. A file's content never changes, so
 * a preview is fetched once and kept.
 */
@Injectable({ providedIn: 'root' })
export class FilePreviewsService {
  private previews = new Map<string, Promise<string>>();

  constructor(private api: ApiService) {}

  /** The object URL of a file's preview; rejects for a file that has none (no image, or gone). */
  url(fileId: string, size: FilePreviewSize): Promise<string> {
    const key = `${size}:${fileId}`;
    let preview = this.previews.get(key);
    if (!preview) {
      preview = this.api.getFileThumbnail(fileId, size).then(blob => URL.createObjectURL(blob));
      this.previews.set(key, preview);
      // A failed one is asked for again next time
      preview.catch(() => this.previews.delete(key));
      this.trim();
    }
    return preview;
  }

  private trim(): void {
    while (this.previews.size > MAX_PREVIEWS) {
      const [key, oldest] = this.previews.entries().next().value!;
      this.previews.delete(key);
      oldest.then(url => URL.revokeObjectURL(url)).catch(() => undefined);
    }
  }
}
