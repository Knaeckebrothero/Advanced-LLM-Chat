import { Injectable, NgZone } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { RecordingConfig, RecordingResult } from '../models/recording-config.interface';
import { VoiceAudioProcessor } from '../audio-processing/voice-audio-processor';
import { TimeBasedBarVisualizer } from '../visualizers/time-based-bar-visualizer';

export interface RecordingState {
  isRecording: boolean;
  duration: number;
  audioLevel: number;
}

@Injectable({
  providedIn: 'root'
})
export class VoiceRecordingService {
  private mediaRecorder: MediaRecorder | null = null;
  private audioStream: MediaStream | null = null;
  private audioChunks: Blob[] = [];
  private recordingState$ = new BehaviorSubject<RecordingState>({
    isRecording: false,
    duration: 0,
    audioLevel: 0
  });
  private recordingStartTime: number = 0;
  private recordingTimer: any;
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private audioProcessor: VoiceAudioProcessor | null = null;
  private barVisualizer: TimeBasedBarVisualizer | null = null;

  constructor(private ngZone: NgZone) {}

  getRecordingState(): Observable<RecordingState> {
    return this.recordingState$.asObservable();
  }

  async startRecording(config: RecordingConfig, canvas?: HTMLCanvasElement): Promise<void> {
    try {
      // Request microphone access with specified constraints
      const constraints = {
        audio: config.audioConstraints || {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      };

      this.audioStream = await navigator.mediaDevices.getUserMedia(constraints);
      this.recordingStartTime = Date.now();
      this.audioChunks = [];

      // Set up audio context and analyzer for visualization
      if (this.audioStream) {
        this.setupAudioProcessing(this.audioStream);
      }

      // Set up visualization if canvas is provided
      if (canvas && this.audioProcessor) {
        this.setupVisualization(canvas);
      }

      // Create and start media recorder
      const mimeType = config.mimeType || this.getSupportedMimeType();
      this.mediaRecorder = new MediaRecorder(this.audioStream, { mimeType });

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };

      this.mediaRecorder.start(100); // Collect data every 100ms

      // Start timer to track recording duration
      this.startRecordingTimer();

      // Update recording state
      this.recordingState$.next({
        ...this.recordingState$.value,
        isRecording: true
      });
    } catch (error) {
      console.error('Error starting recording:', error);
      this.cleanup();
      throw error;
    }
  }

  async stopRecording(): Promise<RecordingResult | null> {
    if (!this.mediaRecorder || !this.recordingState$.value.isRecording) {
      return null;
    }

    return new Promise<RecordingResult>((resolve) => {
      this.mediaRecorder!.onstop = () => {
        const duration = this.recordingState$.value.duration;
        const audioBlob = new Blob(this.audioChunks, {
          type: this.mediaRecorder!.mimeType || 'audio/webm'
        });

        const result: RecordingResult = {
          blob: audioBlob,
          duration,
          mimeType: this.mediaRecorder!.mimeType || 'audio/webm'
        };

        this.cleanup();
        resolve(result);
      };

      this.mediaRecorder!.stop();
    });
  }

  cancelRecording(): void {
    if (this.mediaRecorder && this.recordingState$.value.isRecording) {
      this.mediaRecorder.stop();
      this.cleanup();
    }
  }

  private startRecordingTimer(): void {
    this.recordingTimer = setInterval(() => {
      const elapsed = Math.floor((Date.now() - this.recordingStartTime) / 1000);

      // Update recording state with new duration and audio level
      this.recordingState$.next({
        ...this.recordingState$.value,
        duration: elapsed,
        audioLevel: this.audioProcessor?.getVoiceLevel() || 0
      });
    }, 100);
  }

  private setupAudioProcessing(stream: MediaStream): void {
    try {
      // Create audio context
      this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();

      // Create analyser node
      this.analyser = this.audioContext.createAnalyser();

      // Connect stream to analyser
      const source = this.audioContext.createMediaStreamSource(stream);
      source.connect(this.analyser);

      // Create audio processor
      this.audioProcessor = new VoiceAudioProcessor(this.audioContext, this.analyser);
    } catch (error) {
      console.error('Error setting up audio processing:', error);
    }
  }

  private setupVisualization(canvas: HTMLCanvasElement): void {
    if (!this.audioProcessor) return;

    // Run visualization outside Angular zone for better performance
    this.ngZone.runOutsideAngular(() => {
      this.barVisualizer = new TimeBasedBarVisualizer(
        canvas,
        () => this.audioProcessor?.getVoiceLevel() || 0
      );

      // Start the visualization
      this.barVisualizer.start();
    });
  }

  private getSupportedMimeType(): string {
    const types = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/ogg',
      'audio/mp4',
      'audio/mpeg'
    ];

    for (const type of types) {
      if (MediaRecorder.isTypeSupported(type)) {
        return type;
      }
    }

    return '';
  }

  private cleanup(): void {
    // Stop recording timer
    if (this.recordingTimer) {
      clearInterval(this.recordingTimer);
      this.recordingTimer = null;
    }

    // Stop visualization
    if (this.barVisualizer) {
      this.barVisualizer.stop();
      this.barVisualizer = null;
    }

    // Stop audio tracks
    if (this.audioStream) {
      this.audioStream.getTracks().forEach(track => track.stop());
      this.audioStream = null;
    }

    // Close audio context
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
      this.analyser = null;
      this.audioProcessor = null;
    }

    // Reset recording state
    this.recordingState$.next({
      isRecording: false,
      duration: 0,
      audioLevel: 0
    });

    this.mediaRecorder = null;
    this.audioChunks = [];
  }
}
