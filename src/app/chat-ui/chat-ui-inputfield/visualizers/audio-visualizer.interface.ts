export interface AudioVisualizer {
  start(): void;
  stop(): void;
  updateDimensions(width: number, height: number): void;
}

export interface VisualizationBar {
  height: number;
  timestamp: number;
  x: number;
}
