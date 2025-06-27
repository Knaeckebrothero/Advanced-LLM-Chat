import { Component, OnInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { FilePreview, FilePreviewUtil } from '../../data/objects/file-preview';


@Component({
  selector: 'app-camera-capture-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './camera-capture-dialog.component.html',
  styleUrls: ['./camera-capture-dialog.component.scss']
})
export class CameraCaptureDialogComponent implements OnInit, OnDestroy {
  @ViewChild('videoElement') videoElement!: ElementRef<HTMLVideoElement>;
  @ViewChild('canvasElement') canvasElement!: ElementRef<HTMLCanvasElement>;

  stream: MediaStream | null = null;
  isLoading = true;
  error: string | null = null;
  capturedImage: string | null = null;
  facingMode: 'user' | 'environment' = 'environment'; // Default to back camera
  hasMultipleCameras = false;

  constructor(
    public dialogRef: MatDialogRef<CameraCaptureDialogComponent>
  ) {}

  ngOnInit() {
    this.checkCameraCount();
    this.startCamera();
  }

  ngOnDestroy() {
    this.stopCamera();
  }

  private async checkCameraCount() {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoDevices = devices.filter(device => device.kind === 'videoinput');
      this.hasMultipleCameras = videoDevices.length > 1;
    } catch (error) {
      console.error('Error checking camera count:', error);
    }
  }

  async startCamera() {
    try {
      this.isLoading = true;
      this.error = null;

      // Stop any existing stream
      this.stopCamera();

      // Request camera access with preferred facing mode
      const constraints: MediaStreamConstraints = {
        video: {
          facingMode: this.facingMode,
          width: { ideal: 1920 },
          height: { ideal: 1080 }
        }
      };

      this.stream = await navigator.mediaDevices.getUserMedia(constraints);

      // Wait for video element to be available
      setTimeout(() => {
        if (this.videoElement && this.videoElement.nativeElement) {
          this.videoElement.nativeElement.srcObject = this.stream;
          this.isLoading = false;
        }
      }, 100);

    } catch (error) {
      console.error('Error accessing camera:', error);
      this.isLoading = false;

      if (error instanceof DOMException) {
        switch(error.name) {
          case 'NotAllowedError':
            this.error = 'Camera access denied. Please allow camera access and try again.';
            break;
          case 'NotFoundError':
            this.error = 'No camera found on this device.';
            break;
          case 'NotReadableError':
            this.error = 'Camera is already in use by another application.';
            break;
          default:
            this.error = 'Unable to access camera. Please try again.';
        }
      } else {
        this.error = 'An unexpected error occurred while accessing the camera.';
      }
    }
  }

  private stopCamera() {
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
      this.stream = null;
    }
  }

  switchCamera() {
    this.facingMode = this.facingMode === 'user' ? 'environment' : 'user';
    this.startCamera();
  }

  capturePhoto() {
    if (!this.videoElement || !this.canvasElement) return;

    const video = this.videoElement.nativeElement;
    const canvas = this.canvasElement.nativeElement;
    const context = canvas.getContext('2d');

    if (!context) return;

    // Set canvas dimensions to match video
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    // Draw the current video frame to canvas
    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    // Convert to data URL
    this.capturedImage = canvas.toDataURL('image/jpeg', 0.9);

    // Stop the camera stream to show captured image
    this.stopCamera();
  }

  retakePhoto() {
    this.capturedImage = null;
    this.startCamera();
  }

  async savePhoto() {
    if (!this.capturedImage) return;

    try {
      // Convert data URL to blob
      const response = await fetch(this.capturedImage);
      const blob = await response.blob();

      // Create a File object with timestamp name
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      const file = new File([blob], `photo-${timestamp}.jpg`, {
        type: 'image/jpeg',
        lastModified: Date.now()
      });

      // Create FilePreview object
      const filePreview = await FilePreviewUtil.createFromFile(file);

      // Return the file preview
      this.dialogRef.close(filePreview);

    } catch (error) {
      console.error('Error saving photo:', error);
      this.error = 'Failed to save photo. Please try again.';
    }
  }

  cancel() {
    this.dialogRef.close();
  }
}
