import { Component, Inject, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MAT_DIALOG_DATA, MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { FileType } from '../../data/models';
import { ApiService } from '../../services/api.service';
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
}

@Component({
  selector: 'app-file-preview-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatIconModule,
    MatButtonModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './file-preview-dialog.component.html',
  styleUrls: ['./file-preview-dialog.component.scss']
})
export class FilePreviewDialogComponent implements OnInit, OnDestroy {
  state: FilePreviewState = 'loading';
  contentUrl: string | null = null;
  errorMessage: string = '';
  // For zoom/pan functionality
  zoomLevel: number = 1;
  private minZoom: number = 0.5;
  private maxZoom: number = 4;
  private zoomStep: number = 0.25;

  constructor(
    public dialogRef: MatDialogRef<FilePreviewDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: FilePreviewDialogData,
    private apiService: ApiService,
    private dbService: DBService,
    private messageRepository: MessageRepository
  ) {}

  ngOnInit(): void {
    this.loadContent();
  }

  ngOnDestroy(): void {
    // Revoke object URL to free memory
    if (this.contentUrl && !this.data.localUrl) {
      URL.revokeObjectURL(this.contentUrl);
    }
  }

  private async loadContent(): Promise<void> {
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

    // Otherwise, fetch from backend
    try {
      const blob = await this.apiService.getFile(this.data.fileId);
      this.contentUrl = URL.createObjectURL(blob);
      this.state = 'loaded';

      // If this is an image and we have message info, regenerate and save the thumbnail preview
      if (this.isImage() && this.data.messageId && this.data.conversationId) {
        this.regenerateAndSavePreview(blob);
      }
    } catch (error) {
      console.error('Failed to load file:', error);
      this.errorMessage = 'Failed to load file. Please try again.';
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

  download(): void {
    if (!this.contentUrl) return;

    const link = document.createElement('a');
    link.href = this.contentUrl;
    link.download = this.data.fileName;
    link.click();
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
