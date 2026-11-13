import { Component, HostListener, Inject, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { MAT_DIALOG_DATA, MatDialog, MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { FileType } from '../../data/models';
import { IFileRef } from '../../data/models/file.model';
import { FilePreviewUtil } from '../../data/objects/message';
import { ApiService } from '../../services/api.service';
import { saveBlob, saveUrl } from '../../utils/download.util';
import { DBService } from '../../data/db.service';
import { MessageRepository } from '../../repositories/message.repository';

export type FilePreviewState = 'loading' | 'loaded' | 'error';

export interface FilePreviewDialogData {
  fileId: string;
  fileName: string;
  fileSize?: string;
  fileType: FileType;
  mimeType: string;
  // Optional: pre-loaded content (for locally available files)
  localUrl?: string;
  localFile?: File;
  // For updating message with regenerated preview
  messageId?: number;
  conversationId?: string;
  /** The files to step through from this one, in their order; this file is one of them. */
  gallery?: FilePreviewDialogData[];
}

// A swipe across the picture this far steps to the next or the previous file
const SWIPE_MIN_PX = 60;

/** A stored file as the preview dialog takes it. */
export function filePreviewData(file: IFileRef): FilePreviewDialogData {
  return {
    fileId: file.fileId,
    fileName: file.name,
    fileSize: file.size ? FilePreviewUtil.formatFileSize(file.size) : undefined,
    fileType: FilePreviewUtil.getFileType(file.mimeType),
    mimeType: file.mimeType
  };
}

/**
 * Open a stored file in the preview dialog (zoom, download).
 * @param gallery The files to step through from it (previous, next), in their order.
 */
export function openFilePreview(dialog: MatDialog, file: IFileRef, gallery?: IFileRef[]): MatDialogRef<FilePreviewDialogComponent> {
  const data = filePreviewData(file);
  if (gallery && gallery.length > 1 && gallery.some(other => other.fileId === file.fileId)) {
    data.gallery = gallery.map(other => other.fileId === file.fileId ? data : filePreviewData(other));
  }
  return dialog.open(FilePreviewDialogComponent, {
    data,
    panelClass: 'file-preview-dialog-panel',
    hasBackdrop: false,  // The dialog has its own
    maxWidth: '100vw',
    maxHeight: '100vh',
    width: '100vw',
    height: '100vh'
  });
}

@Component({
  selector: 'app-file-preview-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatIconModule,
    MatButtonModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    TranslateModule
  ],
  templateUrl: './file-preview-dialog.component.html',
  styleUrls: ['./file-preview-dialog.component.scss']
})
export class FilePreviewDialogComponent implements OnInit, OnDestroy {
  state: FilePreviewState = 'loading';
  contentUrl: string | null = null;
  textContent: string | null = null;  // For document text preview
  errorMessage: string = '';
  // For zoom/pan functionality
  zoomLevel: number = 1;
  private minZoom: number = 0.5;
  private maxZoom: number = 4;
  private zoomStep: number = 0.25;
  // The files to step through (data.gallery) and which of them is shown
  private gallery: FilePreviewDialogData[];
  index: number;
  // Counts up with every file shown: what a slower request brings for an earlier one is dropped
  private shown = 0;
  private swipeStart: { x: number; y: number } | null = null;
  downloading = false;

  constructor(
    public dialogRef: MatDialogRef<FilePreviewDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: FilePreviewDialogData,
    private apiService: ApiService,
    private dbService: DBService,
    private messageRepository: MessageRepository,
    private translate: TranslateService
  ) {
    this.gallery = data.gallery ?? [];
    this.index = Math.max(0, this.gallery.findIndex(file => file.fileId === data.fileId));
  }

  ngOnInit(): void {
    this.loadContent();
  }

  ngOnDestroy(): void {
    this.shown++;
    this.releaseContent();
  }

  /** Revoke the object URL of the file shown, to free its memory. */
  private releaseContent(): void {
    if (this.contentUrl && !this.data.localUrl) {
      URL.revokeObjectURL(this.contentUrl);
    }
    this.contentUrl = null;
  }

  /** How many files can be stepped through; 0 for a file opened alone. */
  get galleryCount(): number {
    return this.gallery.length > 1 ? this.gallery.length : 0;
  }

  get hasPrevious(): boolean {
    return this.galleryCount > 0 && this.index > 0;
  }

  get hasNext(): boolean {
    return this.galleryCount > 0 && this.index < this.gallery.length - 1;
  }

  /** Show the next file of the gallery (by = 1) or the previous one (by = -1). */
  step(by: number): void {
    const next = this.gallery[this.index + by];
    if (!this.galleryCount || !next) return;
    this.releaseContent();
    this.index += by;
    this.data = next;
    this.textContent = null;
    this.errorMessage = '';
    this.zoomLevel = 1;
    this.state = 'loading';
    void this.loadContent();
  }

  @HostListener('document:keydown', ['$event'])
  onKeydown(event: KeyboardEvent): void {
    if (!this.galleryCount || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === 'ArrowLeft') this.step(-1);
    else if (event.key === 'ArrowRight') this.step(1);
  }

  onTouchStart(event: TouchEvent): void {
    this.swipeStart = event.touches.length === 1
      ? { x: event.touches[0].clientX, y: event.touches[0].clientY } : null;
  }

  /** A swipe across a picture that isn't zoomed in steps to the next file (left) or the previous one (right). */
  onTouchEnd(event: TouchEvent): void {
    const start = this.swipeStart;
    this.swipeStart = null;
    if (!start || !this.galleryCount || this.zoomLevel > 1 || event.changedTouches.length !== 1) return;
    const dx = event.changedTouches[0].clientX - start.x;
    const dy = event.changedTouches[0].clientY - start.y;
    if (Math.abs(dx) >= SWIPE_MIN_PX && Math.abs(dx) > 2 * Math.abs(dy)) this.step(dx < 0 ? 1 : -1);
  }

  private async loadContent(): Promise<void> {
    const shown = ++this.shown;
    // If we have local content, use it directly
    if (this.data.localUrl) {
      this.contentUrl = this.data.localUrl;
      this.state = 'loaded';
      return;
    }

    if (this.data.localFile) {
      this.contentUrl = URL.createObjectURL(this.data.localFile);
      this.state = 'loaded';
      return;
    }

    // For documents, fetch text content instead of binary
    if (this.isDocument()) {
      try {
        const text = await this.apiService.getFileText(this.data.fileId);
        if (shown !== this.shown) return;
        this.textContent = text;
        this.state = 'loaded';
      } catch (error) {
        if (shown !== this.shown) return;
        // No text in it (a scan, say): it can still be downloaded
        if (error instanceof HttpErrorResponse && error.status === 404) {
          this.state = 'loaded';
          return;
        }
        console.error('Failed to load document text:', error);
        this.errorMessage = this.translate.instant('filePreview.documentFailed');
        this.state = 'error';
      }
      return;
    }

    // Otherwise, fetch binary content from backend
    try {
      const blob = await this.apiService.getFile(this.data.fileId);
      if (shown !== this.shown) return;
      this.contentUrl = URL.createObjectURL(blob);
      this.state = 'loaded';

      // If this is an image and we have message info, regenerate and save the thumbnail preview
      if (this.isImage() && this.data.messageId && this.data.conversationId) {
        this.regenerateAndSavePreview(blob);
      }
    } catch (error) {
      if (shown !== this.shown) return;
      console.error('Failed to load file:', error);
      this.errorMessage = this.translate.instant('filePreview.loadFailed');
      this.state = 'error';
    }
  }

  /**
   * Regenerate thumbnail preview from blob and save to message in IndexedDB
   */
  private async regenerateAndSavePreview(blob: Blob): Promise<void> {
    try {
      // Generate base64 preview from blob
      const preview = await this.blobToBase64(blob);

      // Get the message from IndexedDB
      const message = await this.dbService.getMessage(this.data.messageId!);
      if (!message || !message.attachments) {
        console.warn('Message not found or has no attachments');
        return;
      }

      // Find the attachment and update its preview
      const attachment = message.attachments.find(a => a.id === this.data.fileId);
      if (attachment) {
        attachment.preview = preview;

        // Update message in IndexedDB (without incrementing version - this is a local cache update)
        const serialized = message.toJSON();
        await this.dbService['db'].put('chatMessages', serialized);

        // Refresh the repository cache
        await this.messageRepository.refreshConversationCache(this.data.conversationId!);

        console.log(`Regenerated preview for attachment ${this.data.fileId}`);
      }
    } catch (error) {
      console.error('Failed to regenerate and save preview:', error);
      // Don't throw - preview regeneration failure shouldn't block the dialog
    }
  }

  /**
   * Convert blob to base64 data URL
   */
  private blobToBase64(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  close(): void {
    this.dialogRef.close();
  }

  onBackdropClick(event: MouseEvent): void {
    if ((event.target as HTMLElement).classList.contains('dialog-container')) {
      this.close();
    }
  }

  onContentClick(event: MouseEvent): void {
    event.stopPropagation();
  }

  /** The file can be saved: also a document whose text didn't load, or isn't there yet. */
  get canDownload(): boolean {
    return !this.downloading && (this.state !== 'loading' || this.isDocument());
  }

  /**
   * Save the file. What is shown is saved as it is; a document is shown as its text, so the
   * file itself is fetched first.
   */
  async download(): Promise<void> {
    if (this.contentUrl) {
      saveUrl(this.contentUrl, this.data.fileName);
      return;
    }
    if (this.downloading) return;
    const { fileId, fileName } = this.data;
    this.downloading = true;
    try {
      saveBlob(await this.apiService.getFile(fileId), fileName);
    } catch (error) {
      console.error('Failed to download file:', error);
      if (this.data.fileId === fileId) {
        this.errorMessage = this.translate.instant('filePreview.loadFailed');
        this.state = 'error';
      }
    } finally {
      this.downloading = false;
    }
  }

  retry(): void {
    this.state = 'loading';
    this.errorMessage = '';
    this.loadContent();
  }

  getFileIcon(): string {
    const iconMap: Record<FileType, string> = {
      [FileType.IMAGE]: 'image',
      [FileType.AUDIO]: 'audiotrack',
      [FileType.VIDEO]: 'videocam',
      [FileType.DOCUMENT]: 'description',
      [FileType.OTHER]: 'insert_drive_file'
    };
    return iconMap[this.data.fileType] || 'insert_drive_file';
  }

  isImage(): boolean {
    return this.data.fileType === FileType.IMAGE;
  }

  isAudio(): boolean {
    return this.data.fileType === FileType.AUDIO;
  }

  isDocument(): boolean {
    return this.data.fileType === FileType.DOCUMENT;
  }

  // Zoom control methods
  zoomIn(): void {
    if (this.zoomLevel < this.maxZoom) {
      this.zoomLevel = Math.min(this.zoomLevel + this.zoomStep, this.maxZoom);
    }
  }

  zoomOut(): void {
    if (this.zoomLevel > this.minZoom) {
      this.zoomLevel = Math.max(this.zoomLevel - this.zoomStep, this.minZoom);
    }
  }

  resetZoom(): void {
    this.zoomLevel = 1;
  }

  onWheel(event: WheelEvent): void {
    event.preventDefault();
    if (event.deltaY < 0) {
      this.zoomIn();
    } else {
      this.zoomOut();
    }
  }

  get zoomPercentage(): number {
    return Math.round(this.zoomLevel * 100);
  }

  get canZoomIn(): boolean {
    return this.zoomLevel < this.maxZoom;
  }

  get canZoomOut(): boolean {
    return this.zoomLevel > this.minZoom;
  }
}
