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
 * A stored file as the server names it (backend/services/file_store.py file_ref(),
 * docs/files.md): in a step's metadata, a file a tool created in the answer (`files`) or one
 * that is shown with it anyway (`shownFiles`), and in the list of a conversation's files.
 */
export interface IFileRef {
  fileId: string;
  name: string;
  mimeType: string;
  size?: number;    // Bytes
  width?: number;   // Images: pixels
  height?: number;
}

/** A file in the list of its conversation's files (GET /api/files, file_store.file_entry()). */
export interface IChatFile extends IFileRef {
  /** Attached by the user, or created by a tool of the agent (an MCP server's image, say). */
  source?: 'upload' | 'tool';
  /** A tool's file: the tool's title, "Civitai: Run step". */
  origin?: string;
  /** When it was stored (UTC, ISO). */
  createdAt?: string;
  /** In the list of all files: the conversation it belongs to. */
  conversationId?: string;
  conversationName?: string;
}

/** A page of the files of all the user's conversations (GET /api/files/all). */
export interface IAllFiles {
  /** The conversations by their newest file, each conversation's files together, newest first. */
  files: IChatFile[];
  /** How many uploads and files of tools there are in all. */
  counts: { upload: number; tool: number };
  /** The bytes all of them take. */
  size: number;
}

/** The size of a file's preview image: at most 256 or 1024 pixels on its longer edge. */
export type FilePreviewSize = 'small' | 'large';
