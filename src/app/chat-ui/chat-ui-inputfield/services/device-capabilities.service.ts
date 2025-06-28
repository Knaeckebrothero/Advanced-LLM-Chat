import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { DeviceCapabilities } from '../models/input-field-state.interface';

@Injectable({
  providedIn: 'root'
})
export class DeviceCapabilitiesService {
  private capabilities$ = new BehaviorSubject<DeviceCapabilities>({
    hasCamera: false,
    hasMultipleCameras: false,
    hasGeolocation: false,
    hasAudioInput: false,
    isMobile: false
  });

  constructor() {
    this.detectCapabilities();
  }

  getCapabilities(): Observable<DeviceCapabilities> {
    return this.capabilities$.asObservable();
  }

  private async detectCapabilities(): Promise<void> {
    const capabilities: DeviceCapabilities = {
      hasCamera: false,
      hasMultipleCameras: false,
      hasGeolocation: false,
      hasAudioInput: false,
      isMobile: this.isMobileDevice()
    };

    // Camera detection
    if (navigator.mediaDevices &&
        typeof navigator.mediaDevices.getUserMedia === 'function' &&
        window.isSecureContext) {
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = devices.filter(device => device.kind === 'videoinput');
        const audioDevices = devices.filter(device => device.kind === 'audioinput');

        capabilities.hasCamera = videoDevices.length > 0;
        capabilities.hasMultipleCameras = videoDevices.length > 1;
        capabilities.hasAudioInput = audioDevices.length > 0;
      } catch (error) {
        console.warn('Error detecting media devices:', error);
      }
    }

    // Geolocation detection
    capabilities.hasGeolocation = 'geolocation' in navigator && window.isSecureContext;

    this.capabilities$.next(capabilities);
  }

  private isMobileDevice(): boolean {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  }
}
