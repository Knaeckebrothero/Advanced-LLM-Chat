import { Injectable } from '@angular/core';
import { FilePreview, FilePreviewUtil, FileType, UploadStatus } from '../../data/objects/file-preview';
import { RecordingResult } from '../../data/objects/recording';


/**
 * Service for handling file-related operations such as validation, preview generation,
 * and utility functions for file type icons and extensions.
 */
@Injectable({
  providedIn: 'root'
})
export class FileHandlingService {
  constructor() {}

  /**
   * Validates file size
   * @param file File to validate
   * @param maxSizeMB Maximum size in MB
   * @returns boolean indicating if file is valid
   */
  validateFileSize(file: File, maxSizeMB: number = 10): boolean {
    return FilePreviewUtil.validateFileSize(file, maxSizeMB);
  }

  /**
   * Creates file previews from selected files
   * @param files Array of files to create previews for
   * @param maxSizeMB Maximum size in MB
   * @returns Promise with array of file previews
   */
  async createFilePreviews(files: File[], maxSizeMB: number = 10): Promise<FilePreview[]> {
    const validFiles = files.filter(file => this.validateFileSize(file, maxSizeMB));
    const previews: FilePreview[] = [];

    for (const file of validFiles) {
      try {
        const preview = await FilePreviewUtil.createFromFile(file);
        previews.push(preview);
      } catch (error) {
        console.error('Error creating file preview:', error);
      }
    }

    return previews;
  }

  /**
   * Creates a file preview for an audio recording
   * @param recordingResult The result of a voice recording
   * @returns Promise<FilePreview> for the audio recording with base64 data
   */
  async createAudioFilePreview(recordingResult: RecordingResult): Promise<FilePreview> {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const extension = this.getFileExtension(recordingResult.mimeType);
    const fileName = `voice-message-${timestamp}.${extension}`;
    const duration = this.formatDuration(recordingResult.duration);

    // Create a File object from the blob
    const audioFile = new File([recordingResult.blob], fileName, {
      type: recordingResult.mimeType,
      lastModified: Date.now()
    });

    // Convert blob to base64 for offline storage/playback
    const base64Data = await this.blobToBase64(recordingResult.blob);

    // Create FilePreview with base64 data
    return {
      id: FilePreviewUtil.generateId(),
      file: audioFile,
      name: `Voice message (${duration})`,
      size: audioFile.size,
      sizeFormatted: FilePreviewUtil.formatFileSize(audioFile.size),
      type: FileType.AUDIO,
      mimeType: audioFile.type,
      uploadStatus: UploadStatus.PENDING,
      base64Data: base64Data
    };
  }

  /**
   * Converts a Blob to a base64 data URL
   * @param blob Blob to convert
   * @returns Promise with base64 data URL string
   */
  private blobToBase64(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        resolve(reader.result as string);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  /**
   * Gets the appropriate icon for a file type
   * @param type FileType or string representation of file type
   * @returns Material icon name
   */
  getFileIcon(type: FileType | string): string {
    return FilePreviewUtil.getFileIcon(type as any);
  }

  /**
   * Gets file extension from MIME type
   * @param mimeType MIME type string
   * @returns File extension
   */
  private getFileExtension(mimeType: string): string {
    const typeMap: { [key: string]: string } = {
      'audio/webm': 'webm',
      'audio/ogg': 'ogg',
      'audio/mp4': 'm4a',
      'audio/mpeg': 'mp3',
      'audio/wav': 'wav'
    };

    return typeMap[mimeType.split(';')[0]] || 'webm';
  }

  /**
   * Formats duration in MM:SS format
   * @param seconds Duration in seconds
   * @returns Formatted duration string
   */
  private formatDuration(seconds: number): string {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
  }
}
