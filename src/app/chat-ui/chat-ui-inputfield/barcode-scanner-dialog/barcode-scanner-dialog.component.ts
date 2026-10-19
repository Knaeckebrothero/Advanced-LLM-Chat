import { Component, AfterViewInit, OnDestroy, NgZone } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatDialogRef, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { TranslateModule } from '@ngx-translate/core';
import { ApiService } from '../../../services/api.service';

@Component({
  selector: 'app-barcode-scanner-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatDialogModule,
    MatIconModule,
    MatButtonModule,
    MatProgressSpinnerModule,
    TranslateModule
  ],
  templateUrl: './barcode-scanner-dialog.component.html',
  styleUrls: ['./barcode-scanner-dialog.component.scss']
})
export class BarcodeScannerDialogComponent implements AfterViewInit, OnDestroy {
  scanning = false;
  error: string | null = null;
  detectedCode: string | null = null;
  capturing = false;

  private html5Qrcode: any = null;
  private readonly SCANNER_ELEMENT_ID = 'barcode-scanner-region';

  constructor(
    public dialogRef: MatDialogRef<BarcodeScannerDialogComponent>,
    private ngZone: NgZone,
    private apiService: ApiService
  ) {}

  ngAfterViewInit(): void {
    // Small delay to ensure the DOM element is rendered inside the dialog
    setTimeout(() => this.startScanning(), 100);
  }

  async startScanning(): Promise<void> {
    try {
      const { Html5Qrcode, Html5QrcodeSupportedFormats } = await import('html5-qrcode');

      // formatsToSupport MUST be passed to the constructor, not start()
      this.html5Qrcode = new Html5Qrcode(this.SCANNER_ELEMENT_ID, {
        formatsToSupport: [
          Html5QrcodeSupportedFormats.EAN_13,
          Html5QrcodeSupportedFormats.EAN_8,
          Html5QrcodeSupportedFormats.UPC_A,
          Html5QrcodeSupportedFormats.UPC_E,
        ],
        useBarCodeDetectorIfSupported: true,
        verbose: false,
      });

      // Compute a responsive scan region based on the viewport
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;
      const qrboxWidth = Math.min(Math.floor(viewportWidth * 0.8), 400);
      const qrboxHeight = Math.min(Math.floor(viewportHeight * 0.2), 180);

      await this.html5Qrcode.start(
        { facingMode: 'environment' },
        { fps: 15, qrbox: { width: qrboxWidth, height: qrboxHeight } },
        (decodedText: string) => {
          this.ngZone.run(() => {
            this.onBarcodeDetected(decodedText);
          });
        },
        () => {
          // Per-frame scan failure — normal, no barcode in this frame
        }
      );

      this.scanning = true;
    } catch (err: any) {
      this.ngZone.run(() => {
        if (err?.name === 'NotAllowedError' || err?.message?.includes('Permission')) {
          this.error = 'Camera access denied. Please allow camera access and try again.';
        } else {
          this.error = 'Could not start camera. Please check your device settings.';
        }
      });
    }
  }

  private async onBarcodeDetected(ean: string): Promise<void> {
    // Prevent double-detection
    if (this.detectedCode) return;

    this.detectedCode = ean;

    // Brief pause to show detection feedback, then close
    await this.stopScanner();
    setTimeout(() => {
      this.dialogRef.close(ean);
    }, 400);
  }

  /**
   * Capture the current video frame and send it to the backend for
   * server-side decoding with pyzbar. Fallback for when the client-side
   * ZXing JS decoder cannot detect the barcode.
   */
  async captureAndScan(): Promise<void> {
    if (this.capturing || this.detectedCode) return;
    this.capturing = true;
    this.error = null;

    try {
      // Find the video element rendered by html5-qrcode
      const video = document.querySelector(
        `#${this.SCANNER_ELEMENT_ID} video`
      ) as HTMLVideoElement | null;

      if (!video || video.videoWidth === 0) {
        this.error = 'Camera not ready. Please wait and try again.';
        return;
      }

      // Draw the current frame to a canvas
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d')!;
      ctx.drawImage(video, 0, 0);

      // Convert to base64 JPEG (strip the data:image/jpeg;base64, prefix)
      const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
      const base64 = dataUrl.split(',')[1];

      // Send to backend
      const response = await this.apiService.scanBarcode(base64);

      if (response.barcodes.length > 0) {
        const ean = response.barcodes[0].data;
        this.ngZone.run(() => {
          this.onBarcodeDetected(ean);
        });
      } else {
        this.ngZone.run(() => {
          this.error = 'No barcode found. Try moving closer or adjusting the angle.';
          // Clear error after a few seconds so user can try again
          setTimeout(() => { this.error = null; }, 3000);
        });
      }
    } catch (err) {
      console.error('Server-side barcode scan failed:', err);
      this.ngZone.run(() => {
        this.error = 'Could not scan barcode. Please try again.';
        setTimeout(() => { this.error = null; }, 3000);
      });
    } finally {
      this.ngZone.run(() => {
        this.capturing = false;
      });
    }
  }

  async cancel(): Promise<void> {
    await this.stopScanner();
    this.dialogRef.close(null);
  }

  private async stopScanner(): Promise<void> {
    try {
      if (this.html5Qrcode?.isScanning) {
        await this.html5Qrcode.stop();
      }
      this.html5Qrcode?.clear();
    } catch {
      // Ignore cleanup errors
    }
  }

  ngOnDestroy(): void {
    // Ensure scanner is stopped if dialog is closed externally
    if (this.html5Qrcode?.isScanning) {
      this.html5Qrcode.stop().catch(() => {});
    }
  }
}
