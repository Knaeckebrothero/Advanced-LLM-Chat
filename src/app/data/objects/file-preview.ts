/**
 * File Preview Types
 *
 * Re-exports from models/ for backwards compatibility.
 * Import directly from '@app/data/models' for new code.
 */

export type { IFilePreview as FilePreview } from '../models';
export type { IFileAttachment as FileAttachment } from '../models';
export { FileType, UploadStatus } from '../models';

// Re-export FilePreviewUtil from message.ts for backwards compatibility
export { FilePreviewUtil } from './message';
