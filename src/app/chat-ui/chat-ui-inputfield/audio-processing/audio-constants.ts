export const AUDIO_VISUALIZATION_CONFIG = {
  BAR_INTERVAL: 500,        // 0.5 seconds
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
