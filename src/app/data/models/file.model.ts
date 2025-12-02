/**
 * File Data Models
 */

export enum FileType {
  IMAGE = 'image',
  VIDEO = 'video',
  AUDIO = 'audio',
  DOCUMENT = 'document',
  OTHER = 'other'
}

export enum UploadStatus {
  PENDING = 'pending',
  UPLOADING = 'uploading',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled'
}

// Minimal reference for API communication
export interface IFileAttachment {
  fileId: string;
  fileName: string;
  fileSize: number;
  mimeType: string;
}

// Full preview object for local state
export interface IFilePreview {
  id: string;
  file: File;
  name: string;
  size: number;
  sizeFormatted: string;
  type: FileType;
  mimeType: string;
  preview?: string;
  uploadProgress?: number;
  uploadStatus: UploadStatus;
  error?: string;
}
