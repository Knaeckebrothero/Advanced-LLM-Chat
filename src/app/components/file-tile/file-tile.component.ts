import { Component, HostBinding, Input, OnChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';
import { FilePreviewSize, FileType, IFileRef } from '../../data/models/file.model';
import { FilePreviewUtil } from '../../data/objects/message';
import { FilePreviewsService } from '../../services/file-previews.service';
import { FilePreviewDialogComponent, FilePreviewDialogData } from '../file-preview-dialog/file-preview-dialog.component';

// A picture's tile is at most this much wider than high, or higher than wide
const MAX_RATIO = 3;

/**
 * One stored file in the chat (docs/files.md): an image as its preview, any other file as a card
 * with its name (a PDF with its first page). A click opens the file in the preview dialog, where
 * it can be downloaded.
 *
 * Its parent sets the height (--file-tile-height). A picture takes its width from its shape and
 * is always shown whole: where the column is narrower than that, the tile gets lower instead of
 * cropping, and a panorama or a long strip sits inside a 3:1 tile over a blurred copy of itself.
 */
@Component({
  selector: 'app-file-tile',
  standalone: true,
  imports: [CommonModule, MatIconModule, MatTooltipModule, TranslateModule],
  templateUrl: './file-tile.component.html',
  styleUrls: ['./file-tile.component.scss']
})
export class FileTileComponent implements OnChanges {
  @Input({ required: true }) file!: IFileRef;
  /** Which preview to load: small for a row of thumbnails, large for the files of an answer. */
  @Input() size: FilePreviewSize = 'small';
  /** What the picture shows, for screen readers and the tooltip (else the file's name). */
  @Input() label = '';

  url: string | null = null;
  failed = false;
  private shownFileId: string | null = null;

  constructor(private previews: FilePreviewsService, private dialog: MatDialog) {}

  ngOnChanges(): void {
    if (this.file.fileId === this.shownFileId) return;
    const fileId = this.shownFileId = this.file.fileId;
    this.url = null;
    this.failed = false;
    if (!this.isImage && !this.isPdf) return;
    // A PDF's card only has room for a small picture of its first page
    this.previews.url(fileId, this.isImage ? this.size : 'small').then(
      url => { if (this.shownFileId === fileId) this.url = url; },
      () => { if (this.shownFileId === fileId) this.failed = true; }
    );
  }

  get isImage(): boolean {
    return this.file.mimeType.startsWith('image/');
  }

  get isPdf(): boolean {
    return this.file.mimeType === 'application/pdf';
  }

  /** Shown as a picture: an image whose preview loaded or is still loading. */
  @HostBinding('class.is-picture')
  get isPicture(): boolean {
    return this.isImage && !this.failed;
  }

  @HostBinding('class.is-small')
  get isSmall(): boolean {
    return this.size === 'small';
  }

  /** The picture's own shape (width / height); null when its size is unknown. */
  private get shape(): number | null {
    const { width, height } = this.file;
    return width && height ? width / height : null;
  }

  /** The tile's shape, known before the picture loads: the picture's, within 1:3 and 3:1. */
  @HostBinding('style.--file-tile-ratio')
  get ratio(): string | null {
    if (!this.isPicture) return null;
    return String(Math.min(MAX_RATIO, Math.max(1 / MAX_RATIO, this.shape ?? 1)));
  }

  /** The picture doesn't fill its tile (longer or wider than the tile, or of unknown size). */
  get letterboxed(): boolean {
    const shape = this.shape;
    return shape === null || shape > MAX_RATIO || shape < 1 / MAX_RATIO;
  }

  get type(): FileType {
    return FilePreviewUtil.getFileType(this.file.mimeType);
  }

  get icon(): string {
    return FilePreviewUtil.getFileIcon(this.type);
  }

  get sizeText(): string {
    return this.file.size ? FilePreviewUtil.formatFileSize(this.file.size) : '';
  }

  open(): void {
    const data: FilePreviewDialogData = {
      fileId: this.file.fileId,
      fileName: this.file.name,
      fileSize: this.sizeText || undefined,
      fileType: this.type,
      mimeType: this.file.mimeType
    };
    this.dialog.open(FilePreviewDialogComponent, {
      data,
      panelClass: 'file-preview-dialog-panel',
      hasBackdrop: false,  // The dialog has its own
      maxWidth: '100vw',
      maxHeight: '100vh',
      width: '100vw',
      height: '100vh'
    });
  }
}
