/**
 * Recording Data Models
 */

/**
 * Configuration settings for recording functionality.
 */
export interface IRecordingConfig {
  isHoldToRecord: boolean;
  maxDuration: number; // in seconds
  mimeType?: string;
  audioConstraints?: MediaTrackConstraints;
}

/**
 * Result of a media recording process.
 */
export interface IRecordingResult {
  blob: Blob;
  duration: number; // in seconds
  mimeType: string;
}

/**
 * Current state of a recording.
 */
export interface IRecordingState {
  isRecording: boolean;
  duration: number; // in seconds
  audioLevel: number;
}

/**
 * Visualization bar for audio waveform display.
 */
export interface IVisualizationBar {
  height: number;
  timestamp: number;
  x: number;
}
