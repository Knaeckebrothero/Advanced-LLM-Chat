export interface RecordingConfig {
  isHoldToRecord: boolean;
  maxDuration: number; // in seconds
  mimeType?: string;
  audioConstraints?: MediaTrackConstraints;
}

export interface RecordingResult {
  blob: Blob;
  duration: number; // in seconds
  mimeType: string;
}
