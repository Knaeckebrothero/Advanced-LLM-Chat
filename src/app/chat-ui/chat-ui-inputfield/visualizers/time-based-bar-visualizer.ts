import { AudioVisualizer, VisualizationBar } from './audio-visualizer.interface';
import { OptimizedCanvasRenderer } from './optimized-canvas-renderer';
import { AUDIO_VISUALIZATION_CONFIG } from '../audio-processing/audio-constants';

export class TimeBasedBarVisualizer implements AudioVisualizer {
  private bars: VisualizationBar[] = [];
  private lastBarTime = 0;
  private readonly BAR_INTERVAL = AUDIO_VISUALIZATION_CONFIG.BAR_INTERVAL;
  private readonly BAR_WIDTH = AUDIO_VISUALIZATION_CONFIG.BAR_WIDTH;
  private readonly BAR_GAP = AUDIO_VISUALIZATION_CONFIG.BAR_GAP;
  private readonly TOTAL_BAR_SPACE = this.BAR_WIDTH + this.BAR_GAP;
  private readonly SCROLL_SPEED = AUDIO_VISUALIZATION_CONFIG.SCROLL_SPEED;

  private animationId: number | null = null;
  private lastAnimationTime = 0;
  private renderer: OptimizedCanvasRenderer;

  constructor(
    private canvas: HTMLCanvasElement,
    private audioLevelCallback: () => number
  ) {
    this.renderer = new OptimizedCanvasRenderer(
      canvas,
      this.BAR_WIDTH,
      this.BAR_GAP,
      this.TOTAL_BAR_SPACE
    );
  }

  start(): void {
    this.lastAnimationTime = performance.now();
    this.lastBarTime = this.lastAnimationTime;
    this.animationId = requestAnimationFrame(this.animate);
  }

  stop(): void {
    if (this.animationId !== null) {
      cancelAnimationFrame(this.animationId);
      this.animationId = null;
    }
    this.bars = [];
  }

  updateDimensions(width: number, height: number): void {
    // This method is part of the AudioVisualizer interface
    // The canvas dimensions are automatically updated when the canvas element is resized
  }

  private animate = (currentTime: number): void => {
    const deltaTime = currentTime - this.lastAnimationTime;
    this.lastAnimationTime = currentTime;

    // Add new bar every interval
    if (currentTime - this.lastBarTime >= this.BAR_INTERVAL) {
      const audioLevel = this.audioLevelCallback();
      this.addNewBar(audioLevel);
      this.lastBarTime = currentTime;
    }

    // Update bar positions (scroll left)
    this.updateBarPositions(deltaTime);

    // Render frame
    this.renderer.renderFrame(this.bars);

    this.animationId = requestAnimationFrame(this.animate);
  };

  private addNewBar(height: number): void {
    // Position new bars with proper spacing from the start
    const lastBar = this.bars[this.bars.length - 1];
    const startX = lastBar
      ? lastBar.x + this.TOTAL_BAR_SPACE
      : this.canvas.width;

    this.bars.push({
      height,
      timestamp: Date.now(),
      x: startX
    });
  }

  private updateBarPositions(deltaTime: number): void {
    const scrollDistance = (this.SCROLL_SPEED * deltaTime) / 1000;

    // Update positions and remove off-screen bars
    this.bars = this.bars.filter(bar => {
      bar.x -= scrollDistance;
      return bar.x > -(this.BAR_WIDTH + this.BAR_GAP); // Keep bars until fully off-screen including gap
    });
  }
}
