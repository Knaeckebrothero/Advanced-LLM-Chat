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
  file?: File;  // Optional - not available after deserialization from IndexedDB
  name: string;
  size: number;
  sizeFormatted: string;
  type: FileType;
  mimeType: string;
  preview?: string;
  uploadProgress?: number;
  uploadStatus: UploadStatus;
  error?: string;
  transcript?: string;  // For audio files - transcript from backend transcription
  base64Data?: string;  // For audio files - base64 encoded audio data for offline playback
}

/**
 * A stored file as a step's metadata names it (backend/services/file_store.py file_ref(),
 * docs/files.md): a file a tool created in the answer (`files`) or one the agent shows
 * (`shownFiles`).
 */
export interface IFileRef {
  fileId: string;
  name: string;
  mimeType: string;
  size?: number;    // Bytes
  width?: number;   // Images: pixels
  height?: number;
}

/** The size of a file's preview image: at most 256 or 1024 pixels on its longer edge. */
export type FilePreviewSize = 'small' | 'large';
