import { AudioLevelSmoother } from './audio-level-smoother';
import { AUDIO_VISUALIZATION_CONFIG } from './audio-constants';


/**
 * The VoiceAudioProcessor class processes audio data from an AnalyserNode
 * and calculates normalized voice levels based on decibel thresholds.
 * It includes functionality for smoothing audio levels and normalizing
 * them according to predefined configuration thresholds for audio visualization.
 */
export class VoiceAudioProcessor {
  private analyser: AnalyserNode;
  private readonly timeDomainData: Uint8Array;
  private smoother: AudioLevelSmoother;

  constructor(analyserNode: AnalyserNode) {
    this.analyser = analyserNode;
    this.analyser.fftSize = AUDIO_VISUALIZATION_CONFIG.FFT_SIZE;
    this.analyser.smoothingTimeConstant = AUDIO_VISUALIZATION_CONFIG.SMOOTHING_TIME_CONSTANT;

    this.timeDomainData = new Uint8Array(this.analyser.fftSize);
    this.smoother = new AudioLevelSmoother();
  }

  getVoiceLevel(): number {
    // Use time domain for accurate voice levels
    this.analyser.getByteTimeDomainData(this.timeDomainData);

    // Calculate RMS
    let sum = 0;
    for (let i = 0; i < this.timeDomainData.length; i++) {
      const sample = (this.timeDomainData[i] - 128) / 128; // Normalize to -1 to 1
      sum += sample * sample;
    }
    const rms = Math.sqrt(sum / this.timeDomainData.length);

    // Convert to decibels
    const db = 20 * Math.log10(Math.max(rms, 0.0001)); // Avoid log(0)

    // Normalize for voice (your specified mapping)
    const normalized = this.normalizeVoiceLevel(db);

    // Apply smoothing to prevent jumpy bars
    return this.smoother.smooth(normalized);
  }

  private normalizeVoiceLevel(db: number): number {
    // Voice-specific thresholds from constants
    const SILENCE_DB = AUDIO_VISUALIZATION_CONFIG.SILENCE_DB;
    const QUIET_DB = AUDIO_VISUALIZATION_CONFIG.QUIET_DB;
    const NORMAL_DB = AUDIO_VISUALIZATION_CONFIG.NORMAL_DB;
    const LOUD_DB = AUDIO_VISUALIZATION_CONFIG.LOUD_DB;
    const VERY_LOUD_DB = AUDIO_VISUALIZATION_CONFIG.VERY_LOUD_DB;
    const MAX_DB = AUDIO_VISUALIZATION_CONFIG.MAX_DB;

    if (db <= SILENCE_DB) return 1;
    if (db <= QUIET_DB) return this.lerp(1, 20, (db - SILENCE_DB) / (QUIET_DB - SILENCE_DB));
    if (db <= NORMAL_DB) return this.lerp(20, 40, (db - QUIET_DB) / (NORMAL_DB - QUIET_DB));
    if (db <= LOUD_DB) return this.lerp(40, 60, (db - NORMAL_DB) / (LOUD_DB - NORMAL_DB));
    if (db <= VERY_LOUD_DB) return this.lerp(60, 80, (db - LOUD_DB) / (VERY_LOUD_DB - LOUD_DB));
    return this.lerp(80, 100, Math.min(1, (db - VERY_LOUD_DB) / (MAX_DB - VERY_LOUD_DB)));
  }

  private lerp(a: number, b: number, t: number): number {
    return a + (b - a) * Math.max(0, Math.min(1, t));
  }
}
