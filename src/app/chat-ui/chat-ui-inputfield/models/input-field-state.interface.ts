import { FilePreview } from '../../../data/objects/file-preview';

export interface InputFieldState {
  messageText: string;
  filePreviews: FilePreview[];
  isRecording: boolean;
  recordingDuration: number;
  recordingStartTime: number;
  hasContent: boolean;
}

export interface DeviceCapabilities {
  hasCamera: boolean;
  hasMultipleCameras: boolean;
  hasGeolocation: boolean;
  hasAudioInput: boolean;
  isMobile: boolean;
}
