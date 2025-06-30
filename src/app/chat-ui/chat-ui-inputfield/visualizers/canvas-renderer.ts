import { VisualizationBar } from '../../../data/objects/recording'


/**
 * The CanvasRenderer class is responsible for rendering visual elements
 * on an HTML canvas. It is designed to render bars for visualizations,
 * incorporating features such as gradients, rounded corners, and shadows
 * for each bar. The rendering is optimized for performance and visual
 * aesthetics.
 */
export class CanvasRenderer {
  private ctx: CanvasRenderingContext2D;
  private readonly BAR_WIDTH: number;
  private readonly TOTAL_BAR_SPACE: number;

  // Theme colors
  private bgColor: string;
  private barColorTop: string;
  private barColorMiddle: string;
  private barColorBottom: string;
  private fallbackBarColor: string;

  // Gradient for bars
  private barGradient: CanvasGradient | null = null;

  constructor(
    private canvas: HTMLCanvasElement,
    barWidth: number,
    totalBarSpace: number
  ) {
    this.ctx = canvas.getContext('2d', {
      alpha: false,
      desynchronized: true
    })!;

    this.BAR_WIDTH = barWidth;
    this.TOTAL_BAR_SPACE = totalBarSpace;

    // Get theme colors from computed styles
    const computedStyle = getComputedStyle(this.canvas);
    this.bgColor = computedStyle.getPropertyValue('--recording-bg').trim() || '#FFFFFF';
    this.barColorTop = computedStyle.getPropertyValue('--recording-bar-color-top').trim() || '#66B3FF';
    this.barColorMiddle = computedStyle.getPropertyValue('--recording-bar-color-middle').trim() || '#4CA5DC';
    this.barColorBottom = computedStyle.getPropertyValue('--recording-bar-color-bottom').trim() || '#3399D6';
    this.fallbackBarColor = computedStyle.getPropertyValue('--primary-color').trim() || '#4CA5DC';


    // Create gradient for bars
    this.createBarGradient();
  }

  private createBarGradient(): void {
    // Create a vertical gradient for more visual appeal
    this.barGradient = this.ctx.createLinearGradient(0, 0, 0, this.canvas.height);
    this.barGradient.addColorStop(0, this.barColorTop);
    this.barGradient.addColorStop(0.5, this.barColorMiddle);
    this.barGradient.addColorStop(1, this.barColorBottom);
  }

  renderFrame(bars: VisualizationBar[]): void {
    // Clear with theme background color
    this.ctx.fillStyle = this.bgColor;
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    // Only render visible bars
    const visibleBars = bars.filter(bar =>
      bar.x > -this.TOTAL_BAR_SPACE && bar.x < this.canvas.width
    );

    // Draw bars with gradient and rounded corners
    if (this.barGradient) {
      this.ctx.fillStyle = this.barGradient;
    } else {
      this.ctx.fillStyle = this.fallbackBarColor; // Fallback color
    }

    visibleBars.forEach(bar => {
      // Increase sensitivity and add minimum height for better visibility
      const normalizedHeight = Math.max(bar.height * 1.8, 5); // Minimum 5px height
      const barHeight = (normalizedHeight / 100) * this.canvas.height;
      const cappedHeight = Math.min(barHeight, this.canvas.height - 4); // Leave 4px margin
      const y = this.canvas.height - cappedHeight;

      const x = Math.floor(bar.x);

      // Draw rounded rectangle for each bar
      this.drawRoundedRect(x, y, this.BAR_WIDTH, cappedHeight, 4);

      // Add subtle shadow effect
      this.ctx.shadowColor = 'rgba(0, 0, 0, 0.1)';
      this.ctx.shadowBlur = 4;
      this.ctx.shadowOffsetX = 2;
      this.ctx.shadowOffsetY = 2;
      this.ctx.fill();

      // Reset shadow for next bar
      this.ctx.shadowBlur = 0;
      this.ctx.shadowOffsetX = 0;
      this.ctx.shadowOffsetY = 0;
    });
  }

  private drawRoundedRect(x: number, y: number, width: number, height: number, radius: number): void {
    // Ensure radius isn't larger than half the smallest dimension
    radius = Math.min(radius, width / 2, height / 2);

    this.ctx.beginPath();
    // Top left corner
    this.ctx.moveTo(x + radius, y);
    // Top right corner
    this.ctx.lineTo(x + width - radius, y);
    this.ctx.arc(x + width - radius, y + radius, radius, -Math.PI / 2, 0);
    // Bottom right corner
    this.ctx.lineTo(x + width, y + height - radius);
    this.ctx.arc(x + width - radius, y + height - radius, radius, 0, Math.PI / 2);
    // Bottom left corner
    this.ctx.lineTo(x + radius, y + height);
    this.ctx.arc(x + radius, y + height - radius, radius, Math.PI / 2, Math.PI);
    // Back to top left
    this.ctx.lineTo(x, y + radius);
    this.ctx.arc(x + radius, y + radius, radius, Math.PI, -Math.PI / 2);
    this.ctx.closePath();
  }
}
