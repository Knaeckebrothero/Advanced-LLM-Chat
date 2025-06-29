import { AUDIO_VISUALIZATION_CONFIG } from './audio-constants';


/**
 * The `AudioLevelSmoother` class provides functionality to smooth audio level data,
 * allowing for gradual changes in the displayed levels to improve visualization
 * stability. It uses an attack and release mechanism to manage quick rises and slower falls
 * in audio level values.
 *
 * This class is primarily designed for use in audio visualization systems and ensures
 * consistency and smooth transitions in audio level representation.
 */
export class AudioLevelSmoother {
  private currentLevel = 0;
  private readonly ATTACK = AUDIO_VISUALIZATION_CONFIG.ATTACK_RATE;
  private readonly RELEASE = AUDIO_VISUALIZATION_CONFIG.RELEASE_RATE;

  smooth(inputLevel: number): number {
    if (inputLevel > this.currentLevel) {
      // Attack phase - quick rise for speech onset
      this.currentLevel = this.ATTACK * inputLevel + (1 - this.ATTACK) * this.currentLevel;
    } else {
      // Release phase - slower fall
      this.currentLevel = this.RELEASE * inputLevel + (1 - this.RELEASE) * this.currentLevel;
    }
    return Math.round(this.currentLevel); // Round for consistent bar heights
  }
}
