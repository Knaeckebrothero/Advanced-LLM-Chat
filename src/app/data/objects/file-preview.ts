export interface FilePreview {
  id: string;                    // Unique identifier for the preview
  file: File;                    // The actual File object
  name: string;                  // File name
  size: number;                  // File size in bytes
  sizeFormatted: string;         // Human-readable size (e.g., "2.5 MB")
  type: FileType;                // Type category
  mimeType: string;              // Original MIME type
  preview?: string;              // Data URL for image/video thumbnails
  uploadProgress?: number;       // Upload progress (0-100)
  uploadStatus?: UploadStatus;   // Current upload status
  error?: string;                // Error message if upload failed
}

export enum FileType {
  IMAGE = 'image',
  VIDEO = 'video',
  AUDIO = 'audio',  // TODO: Remove this one
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

// Utility class for file handling
export class FilePreviewUtil {

  // Generate a unique ID for the file preview
  static generateId(): string {
    return `file-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  // Format file size to human-readable string
  static formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  // Determine file type from MIME type
  static getFileType(mimeType: string): FileType {
    if (mimeType.startsWith('image/')) return FileType.IMAGE;
    if (mimeType.startsWith('video/')) return FileType.VIDEO;
    if (mimeType.startsWith('audio/')) return FileType.AUDIO;

    const documentTypes = [
      'application/pdf',
      'application/msword',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'text/plain',
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    ];

    if (documentTypes.includes(mimeType)) return FileType.DOCUMENT;

    return FileType.OTHER;
  }

  // Create FilePreview from File object
  static async createFromFile(file: File): Promise<FilePreview> {
    const filePreview: FilePreview = {
      id: this.generateId(),
      file: file,
      name: file.name,
      size: file.size,
      sizeFormatted: this.formatFileSize(file.size),
      type: this.getFileType(file.type),
      mimeType: file.type,
      uploadStatus: UploadStatus.PENDING
    };

    // Generate preview for images
    if (filePreview.type === FileType.IMAGE) {
      try {
        filePreview.preview = await this.generateImagePreview(file);
      } catch (error) {
        console.error('Failed to generate image preview:', error);
      }
    }

    return filePreview;
  }

  // Generate image preview as data URL
  private static generateImagePreview(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();

      reader.onload = (e) => {
        resolve(e.target?.result as string);
      };

      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  // Validate file size (example: max 10MB)
  static validateFileSize(file: File, maxSizeMB: number = 10): boolean {
    const maxSizeBytes = maxSizeMB * 1024 * 1024;
    return file.size <= maxSizeBytes;
  }

  // Get icon name for file type (for Material Icons)
  static getFileIcon(type: FileType): string {
    switch (type) {
      case FileType.IMAGE:
        return 'image';
      case FileType.VIDEO:
        return 'videocam';
      case FileType.AUDIO:
        return 'audiotrack';
      case FileType.DOCUMENT:
        return 'description';
      default:
        return 'insert_drive_file';
    }
  }
}
