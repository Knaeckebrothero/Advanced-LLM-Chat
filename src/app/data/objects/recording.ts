/**
 * Represents the configuration settings for recording functionality.
 *
 * @interface RecordingConfig
 *
 * @property {boolean} isHoldToRecord - Indicates whether the recording should be activated by holding a button.
 * @property {number} maxDuration - Specifies the maximum duration of the recording in seconds.
 * @property {string} [mimeType] - Optional property specifying the MIME type of the recording.
 * @property {MediaTrackConstraints} [audioConstraints] - Optional audio constraints to be used during the recording.
 */
export interface RecordingConfig {
  isHoldToRecord: boolean;
  maxDuration: number; // in seconds
  mimeType?: string;
  audioConstraints?: MediaTrackConstraints;
}

/**
 * An interface representing the result of a media recording process.
 *
 * This interface provides details about the recording, including the recorded data as a Blob,
 * the duration of the recording in seconds, and the MIME type of the recorded media.
 *
 * Properties:
 * - blob: The recorded media data represented as a Blob object.
 * - duration: The length of the recording in seconds.
 * - mimeType: The MIME type of the recorded media, indicating the format.
 */
export interface RecordingResult {
  blob: Blob;
  duration: number; // in seconds
  mimeType: string;
}

/**
 * An interface representing the state of a recording.
 *
 * Properties:
 * - `isRecording`: Indicates whether the recording is currently active.
 * - `duration`: Represents the total duration of the recording in seconds.
 * - `audioLevel`: Specifies the current audio level during the recording, typically used for monitoring purposes.
 */
export interface RecordingState {
  isRecording: boolean;
  duration: number;  // in seconds
  audioLevel: number;
}

/**
 * Represents a visualization bar with properties defining its appearance and position.
 *
 * @interface VisualizationBar
 * @property {number} height Specifies the height of the visualization bar.
 * @property {number} timestamp Denotes the timestamp associated with the bar, typically representing a moment in time.
 * @property {number} x Defines the horizontal position of the visualization bar.
 */
export interface VisualizationBar {
  height: number;
  timestamp: number;
  x: number;
}
