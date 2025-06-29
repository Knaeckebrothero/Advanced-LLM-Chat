import { Injectable } from '@angular/core';
import { FilePreview, FilePreviewUtil, FileType, UploadStatus } from '../../data/objects/file-preview';
import { RecordingResult } from '../../data/objects/recording';

/**
 * Service for handling file-related operations such as validation, preview generation,
 * and utility functions for file type icons. This service acts as a wrapper around
 * the static FilePreviewUtil class to be injectable in components.
 */
@Injectable({
  providedIn: 'root'
})
export class FileHandlingService {
  constructor() {}

  /**
   * Validates file size using the utility function.
   * @param file File to validate.
   * @param maxSizeMB Maximum size in megabytes.
   * @returns `true` if the file size is within the limit, `false` otherwise.
   */
  validateFileSize(file: File, maxSizeMB: number = 10): boolean {
    return FilePreviewUtil.validateFileSize(file, maxSizeMB);
  }

  /**
   * Creates file previews from an array of selected files using the utility class.
   * It filters out files that exceed the size limit and creates a preview object for each valid file.
   * @param files Array of `File` objects to create previews for.
   * @param maxSizeMB The maximum allowed file size in MB.
   * @returns A promise that resolves to an array of `FilePreview` objects.
   */
  async createFilePreviews(files: File[], maxSizeMB: number = 10): Promise<FilePreview[]> {
    const validFiles = files.filter(file => this.validateFileSize(file, maxSizeMB));

    // Use the utility to create all previews
    const previewPromises = validFiles.map(file => FilePreviewUtil.createFromFile(file));

    return Promise.all(previewPromises);
  }

  /**
   * Creates a file preview for an audio recording result.
   * @param recordingResult The result object from a voice recording.
   * @returns A `FilePreview` object representing the audio recording.
   */
  createAudioFilePreview(recordingResult: RecordingResult): FilePreview {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const extension = this.getFileExtensionFromMimeType(recordingResult.mimeType);
    const fileName = `voice-message-${timestamp}.${extension}`;

    const audioFile = new File([recordingResult.blob], fileName, {
      type: recordingResult.mimeType,
      lastModified: Date.now()
    });

    return {
      id: FilePreviewUtil.generateId(),
      file: audioFile,
      name: `Voice message`,
      size: audioFile.size,
      sizeFormatted: FilePreviewUtil.formatFileSize(audioFile.size),
      type: FileType.AUDIO,
      mimeType: audioFile.type,
      uploadStatus: UploadStatus.PENDING,
    };
  }

  /**
   * Gets the appropriate Material Design icon name for a given file type.
   * @param type The FileType enum value.
   * @returns The name of the Material icon to use.
   */
  getFileIcon(type: FileType): string {
    return FilePreviewUtil.getFileIcon(type);
  }

  /**
   * Determines the file extension from a MIME type string.
   * @param mimeType The MIME type of the file.
   * @returns A file extension string.
   */
  private getFileExtensionFromMimeType(mimeType: string): string {
    const typeMap: { [key: string]: string } = {
      'audio/webm': 'webm',
      'audio/ogg': 'ogg',
      'audio/mp4': 'm4a',
      'audio/mpeg': 'mp3',
      'audio/wav': 'wav'
    };
    return typeMap[mimeType.split(';')[0]] || 'webm';
  }
}
