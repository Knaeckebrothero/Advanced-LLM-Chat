/**
 * Configuration object for audio visualization settings and audio processing parameters.
 *
 * Properties:
 * - BAR_INTERVAL (number): The interval in milliseconds for updating each audio bar. Default is 500ms (0.5 seconds).
 * - BAR_WIDTH (number): The width of each visualization bar in pixels.
 * - BAR_GAP (number): The gap between visualization bars in pixels.
 * - SCROLL_SPEED (number): The scroll speed of the visualization display in pixels per second.
 * - CANVAS_HEIGHT (number): The height of the canvas used for rendering the visualization in pixels.
 *
 * Audio Processing:
 * - FFT_SIZE (number): The size of the FFT (Fast Fourier Transform) used for audio frequency analysis. Determines the granularity of the frequency bins.
 * - SMOOTHING_TIME_CONSTANT (number): A value between 0 and 1 for controlling the smoothing of audio frequency data. Higher values mean smoother results.
 *
 * Voice Level Thresholds:
 * - SILENCE_DB (number): The decibel level considered silence. Default is -60 dB.
 * - QUIET_DB (number): The decibel level range considered quiet. Default is -40 dB.
 * - NORMAL_DB (number): The decibel level range considered normal. Default is -25 dB.
 * - LOUD_DB (number): The decibel level range considered loud. Default is -15 dB.
 * - VERY_LOUD_DB (number): The decibel level range considered very loud. Default is -5 dB.
 * - MAX_DB (number): The maximum decibel level. Default is 0 dB.
 *
 * Smoothing:
 * - ATTACK_RATE (number): The rate at which the visualization responds to increasing input values, typically for quick response to audio peaks.
 * - RELEASE_RATE (number): The rate at which the visualization decays when the input decreases, providing a smooth fallback effect.
 */
export const AUDIO_VISUALIZATION_CONFIG = {
  BAR_INTERVAL: 500,
  BAR_WIDTH: 24,
  BAR_GAP: 8,
  SCROLL_SPEED: 60,
  CANVAS_HEIGHT: 80,

  // Audio processing
  FFT_SIZE: 2048,
  SMOOTHING_TIME_CONSTANT: 0.3,

  // Voice level thresholds
  SILENCE_DB: -60,
  QUIET_DB: -40,
  NORMAL_DB: -25,
  LOUD_DB: -15,
  VERY_LOUD_DB: -5,
  MAX_DB: 0,

  // Smoothing
  ATTACK_RATE: 0.8,
  RELEASE_RATE: 0.15
};
