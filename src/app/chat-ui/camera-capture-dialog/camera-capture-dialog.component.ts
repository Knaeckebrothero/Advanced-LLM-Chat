import { Component, OnInit, OnDestroy, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { FilePreviewUtil } from '../../data/objects/file-preview';


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
    this.checkCameraAvailability();
    this.checkCameraCount();
    this.startCamera();
  }

  private async checkCameraAvailability() {
    try {
      // First check if the API is available
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        console.error('getUserMedia API not available');
        this.error = 'Camera API not supported in this browser.';
        this.isLoading = false;
        return;
      }

      // Check if we're in a secure context
      if (!window.isSecureContext) {
        console.error('Not in secure context (HTTPS required)');
        this.error = 'Camera requires HTTPS. Please use a secure connection.';
        this.isLoading = false;
        return;
      }

      console.log('Camera API available and in secure context');
    } catch (error) {
      console.error('Error checking camera availability:', error);
    }
  }

  ngOnDestroy() {
    this.stopCamera();
  }

  private async checkCameraCount() {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoDevices = devices.filter(device => device.kind === 'videoinput');

      console.log('All devices:', devices);
      console.log('Video devices found:', videoDevices);

      this.hasMultipleCameras = videoDevices.length > 1;

      // Log device details for debugging
      videoDevices.forEach((device, index) => {
        console.log(`Camera ${index + 1}:`, {
          deviceId: device.deviceId,
          label: device.label || 'Unnamed camera',
          groupId: device.groupId
        });
      });
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

      // Log for debugging
      console.log('Starting camera with facing mode:', this.facingMode);

      // Try simpler constraints first (Linux compatibility)
      let constraints: MediaStreamConstraints = {
        video: {
          facingMode: this.facingMode
        }
      };

      try {
        this.stream = await navigator.mediaDevices.getUserMedia(constraints);
      } catch (firstError) {
        console.warn('Failed with facing mode, trying basic video constraint');
        // Fallback to most basic constraint for Linux compatibility
        constraints = { video: true };
        this.stream = await navigator.mediaDevices.getUserMedia(constraints);
      }

      console.log('Got media stream:', this.stream);
      console.log('Video tracks:', this.stream.getVideoTracks());

      // Use a longer timeout and add event listeners for Linux systems
      if (this.videoElement && this.videoElement.nativeElement) {
        const video = this.videoElement.nativeElement;

        // Set srcObject immediately
        video.srcObject = this.stream;

        // Handle the loadedmetadata event
        video.onloadedmetadata = () => {
          console.log('Video metadata loaded');
          video.play().then(() => {
            console.log('Video playing');
            this.isLoading = false;
          }).catch(playError => {
            console.error('Error playing video:', playError);
            this.error = 'Camera stream started but video playback failed.';
            this.isLoading = false;
          });
        };

        // Fallback timeout
        setTimeout(() => {
          if (this.isLoading) {
            console.warn('Camera loading timeout');
            this.isLoading = false;
            if (!this.error) {
              this.error = 'Camera is taking too long to respond. Please try again.';
            }
          }
        }, 5000);
      }

    } catch (error) {
      console.error('Error accessing camera:', error);
      this.isLoading = false;

      if (error instanceof DOMException) {
        console.error('DOMException details:', error.name, error.message);
        switch(error.name) {
          case 'NotAllowedError':
          case 'PermissionDeniedError':
            this.error = 'Camera access denied. Please allow camera access in your browser settings and try again.';
            break;
          case 'NotFoundError':
          case 'DevicesNotFoundError':
            this.error = 'No camera found. Please check if your camera is connected and not being used by another application.';
            break;
          case 'NotReadableError':
          case 'TrackStartError':
            this.error = 'Camera is already in use by another application. Please close other video apps and try again.';
            break;
          case 'OverconstrainedError':
            this.error = 'Camera does not support the requested settings. Trying with basic settings...';
            // Try again with basic constraints
            try {
              this.stream = await navigator.mediaDevices.getUserMedia({ video: true });
              this.startCamera(); // Retry with the new stream
              return;
            } catch (retryError) {
              this.error = 'Unable to access camera even with basic settings.';
            }
            break;
          default:
            this.error = `Camera error (${error.name}): ${error.message}`;
        }
      } else {
        this.error = 'An unexpected error occurred while accessing the camera. Check browser console for details.';
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
