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

/**
 * One stored file in the chat (docs/files.md): an image as its preview, any other file as a card
 * with its name. A click opens the file in the preview dialog, where it can be downloaded.
 * Its parent sets the height (--file-tile-height); an image takes its width from its shape.
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

  url: string | null = null;
  failed = false;
  private shownFileId: string | null = null;

  constructor(private previews: FilePreviewsService, private dialog: MatDialog) {}

  ngOnChanges(): void {
    if (this.file.fileId === this.shownFileId) return;
    const fileId = this.shownFileId = this.file.fileId;
    this.url = null;
    this.failed = false;
    if (!this.isImage) return;
    this.previews.url(fileId, this.size).then(
      url => { if (this.shownFileId === fileId) this.url = url; },
      () => { if (this.shownFileId === fileId) this.failed = true; }
    );
  }

  get isImage(): boolean {
    return this.file.mimeType.startsWith('image/');
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

  /** A picture keeps its shape while it loads; panoramas and tall strips are cropped to 3:1. */
  @HostBinding('style.aspect-ratio')
  get aspectRatio(): string | null {
    if (!this.isPicture) return null;
    const { width, height } = this.file;
    if (!width || !height) return '1';
    return String(Math.min(3, Math.max(1 / 3, width / height)));
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
