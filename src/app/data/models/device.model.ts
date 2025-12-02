/**
 * Device Capability Models
 */

export interface IDeviceCapabilities {
  hasCamera: boolean;
  hasMultipleCameras: boolean;
  hasGeolocation: boolean;
  hasAudioInput: boolean;
  isMobile: boolean;
}
