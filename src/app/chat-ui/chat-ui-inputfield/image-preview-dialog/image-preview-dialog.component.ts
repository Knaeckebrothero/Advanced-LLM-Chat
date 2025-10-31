import { Component, Inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MAT_DIALOG_DATA, MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';

export interface ImagePreviewDialogData {
  imageUrl: string;
  fileName: string;
  fileSize?: string;
}

@Component({
  selector: 'app-image-preview-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatIconModule,
    MatButtonModule
  ],
  templateUrl: './image-preview-dialog.component.html',
  styleUrls: ['./image-preview-dialog.component.scss']
})
export class ImagePreviewDialogComponent {
  constructor(
    public dialogRef: MatDialogRef<ImagePreviewDialogComponent>,
    @Inject(MAT_DIALOG_DATA) public data: ImagePreviewDialogData
  ) {}

  close(): void {
    this.dialogRef.close();
  }

  // Handle click on backdrop
  onBackdropClick(event: MouseEvent): void {
    // Check if click was on the backdrop (not the image)
    if ((event.target as HTMLElement).classList.contains('dialog-container')) {
      this.close();
    }
  }

  // Prevent image click from closing dialog
  onImageClick(event: MouseEvent): void {
    event.stopPropagation();
  }

  // Download the image
  downloadImage(): void {
    const link = document.createElement('a');
    link.href = this.data.imageUrl;
    link.download = this.data.fileName;
    link.click();
  }
}