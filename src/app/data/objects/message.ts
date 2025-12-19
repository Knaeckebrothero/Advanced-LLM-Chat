/**
 * Message Class Implementation
 *
 * This file implements the IMessage interface from models/.
 * Uses a hybrid approach with TypeScript discriminated unions
 * to support multiple message types (text, agent) while maintaining
 * type safety and backwards compatibility.
 *
 * Note: Voice messages are now handled as text messages with audio file attachments.
 * The transcript is stored in the text content, and the audio file is an attachment.
 */

import {
  IMessage,
  IMessageMetadata,
  IMessageContent,
  ITextContent,
  IAgentContent,
  IAgentStep,
  AgentStepType,
  AgentStatus,
  AgentDisplayMode,
} from '../models';
import { IFilePreview, UploadStatus, FileType } from '../models';

// Re-export types from models for backwards compatibility
export type { ITextContent as TextContent } from '../models';
export type { IAgentContent as AgentContent } from '../models';
export type { IAgentStep as AgentStep } from '../models';
export type { AgentStepType, AgentStatus, AgentDisplayMode } from '../models';

// Re-export file types for backwards compatibility
export type { IFilePreview as FilePreview } from '../models';
export { UploadStatus, FileType } from '../models';

/**
 * Utility class for file handling
 */
export class FilePreviewUtil {
  static generateId(): string {
    return `file-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  static formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

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

  static async createFromFile(file: File): Promise<IFilePreview> {
    const filePreview: IFilePreview = {
      id: this.generateId(),
      file: file,
      name: file.name,
      size: file.size,
      sizeFormatted: this.formatFileSize(file.size),
      type: this.getFileType(file.type),
      mimeType: file.type,
      uploadStatus: UploadStatus.PENDING
    };

    if (filePreview.type === FileType.IMAGE) {
      try {
        filePreview.preview = await this.generateImagePreview(file);
      } catch (error) {
        console.error('Failed to generate image preview:', error);
      }
    }

    return filePreview;
  }

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

  static validateFileSize(file: File, maxSizeMB: number = 10): boolean {
    const maxSizeBytes = maxSizeMB * 1024 * 1024;
    return file.size <= maxSizeBytes;
  }

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

/**
 * Main Message class that implements IMessage interface.
 * Uses generics to provide type safety for specific content types.
 */
export class Message<T extends IMessageContent = IMessageContent> implements IMessage<T> {
  public metadata: IMessageMetadata;
  public content: T;

  constructor(metadata: IMessageMetadata, content: T) {
    this.metadata = metadata;
    this.content = content;
  }

  // Getters for metadata (convenience accessors)
  get id() { return this.metadata.id; }
  get conversationId() { return this.metadata.conversationId; }
  get roleName() { return this.metadata.roleName; }
  get time() { return this.metadata.time; }
  get type() { return this.content.type; }
  get version() { return this.metadata.version || 1; }
  get lastModified() { return this.metadata.lastModified || Math.floor(this.time.getTime() / 1000); }
  get rating() { return this.metadata.rating; }

  // Setters for metadata (maintaining compatibility with existing code)
  set id(newId: number) { this.metadata.id = newId; }
  set conversationId(newConversationId: string) { this.metadata.conversationId = newConversationId; }
  set roleName(newRoleName: string) { this.metadata.roleName = newRoleName; }
  set time(newTime: Date) { this.metadata.time = newTime; }
  set version(newVersion: number) { this.metadata.version = newVersion; }
  set lastModified(newLastModified: number) { this.metadata.lastModified = newLastModified; }
  set rating(newRating: number | null | undefined) { this.metadata.rating = newRating; }

  // =========================================================================
  // Factory Methods
  // =========================================================================

  static createText(
    metadata: IMessageMetadata,
    content: string,
    attachments?: IFilePreview[]
  ): Message<ITextContent> {
    return new Message(metadata, {
      type: 'text',
      content,
      attachments
    });
  }

  static createAgent(
    conversationId: string,
    steps: IAgentStep[] = [],
    finalResponse: string = '',
    status: AgentStatus = 'thinking'
  ): Message<IAgentContent> {
    return new Message(
      {
        id: Date.now(),
        conversationId,
        roleName: 'assistant',
        time: new Date(),
        version: 1,
      },
      {
        type: 'agent',
        steps,
        finalResponse,
        status,
      }
    );
  }

  // =========================================================================
  // API Conversion Methods
  // =========================================================================

  static fromApiResponse(data: any): Message {
    const messageId = data.id || Math.floor(Date.now() / 1000) + Math.floor(Math.random() * 1000);

    const metadata: IMessageMetadata = {
      id: messageId,
      conversationId: data.conversationId,
      roleName: data.roleName,
      time: new Date(data.time * 1000),
      version: data.version || 1,
      lastModified: data.lastModified || data.time,
      rating: data.rating !== undefined ? data.rating : null
    };

    if (data.type === 'agent') {
      return new Message<IAgentContent>(metadata, {
        type: 'agent',
        steps: data.steps || [],
        finalResponse: data.finalResponse || data.content || '',
        status: data.status || 'complete',
        error: data.error
      });
    } else {
      let attachments: IFilePreview[] | undefined;
      if (data.attachments && Array.isArray(data.attachments)) {
        attachments = data.attachments.map((ref: any) => ({
          id: ref.fileId || ref.id,
          file: new File([], ref.fileName || ref.name || 'unknown'),
          name: ref.fileName || ref.name || 'unknown',
          size: ref.fileSize || ref.size || 0,
          sizeFormatted: FilePreviewUtil.formatFileSize(ref.fileSize || ref.size || 0),
          type: FilePreviewUtil.getFileType(ref.mimeType || 'application/octet-stream'),
          mimeType: ref.mimeType || 'application/octet-stream',
          uploadStatus: UploadStatus.COMPLETED
        }));
      }

      return Message.createText(
        metadata,
        data.content || '',
        attachments
      );
    }
  }

  toApiSend() {
    const base = {
      conversationId: this.conversationId,
      roleName: this.roleName,
      time: Math.floor(this.time.getTime() / 1000),
      type: this.content.type,
      version: this.version,
      lastModified: this.lastModified
    };

    switch (this.content.type) {
      case 'text':
        const textContent = this.content as ITextContent;
        const attachmentRefs = textContent.attachments
          ?.filter(a => a.uploadStatus === UploadStatus.COMPLETED)
          .map(a => ({
            fileId: a.id,
            fileName: a.name,
            fileSize: a.size,
            mimeType: a.mimeType
          }));

        return {
          ...base,
          content: textContent.content,
          ...(attachmentRefs && attachmentRefs.length > 0 && { attachments: attachmentRefs })
        };

      case 'agent':
        const agentContent = this.content as IAgentContent;
        return {
          ...base,
          steps: agentContent.steps,
          finalResponse: agentContent.finalResponse,
          status: agentContent.status,
          ...(agentContent.error && { error: agentContent.error })
        };

      default:
        const _exhaustive: never = this.content;
        throw new Error(`Unknown message type: ${(_exhaustive as any).type}`);
    }
  }

  toApiGenerate(participant: string) {
    return {
      conversationId: this.conversationId,
      roleName: participant,
      time: Math.floor(this.time.getTime() / 1000),
      type: this.content.type
    };
  }

  toApiPatch() {
    if (!this.id) {
      throw new Error('Cannot patch message without ID');
    }
    if (!this.conversationId) {
      throw new Error('Cannot patch message without conversation ID');
    }

    if (this.content.type !== 'text') {
      throw new Error(`Cannot patch ${this.content.type} messages`);
    }

    return {
      id: this.id,
      conversationId: this.conversationId,
      content: (this.content as ITextContent).content
    };
  }

  toApiDelete() {
    if (!this.id) {
      throw new Error('Cannot delete message without ID');
    }
    if (!this.conversationId) {
      throw new Error('Cannot delete message without conversation ID');
    }

    return {
      id: this.id,
      conversationId: this.conversationId
    };
  }

  // =========================================================================
  // Type Guards
  // =========================================================================

  isText(): this is Message<ITextContent> {
    return this.content.type === 'text';
  }

  isAgent(): this is Message<IAgentContent> {
    return this.content.type === 'agent';
  }

  // =========================================================================
  // Backwards Compatibility Getters
  // =========================================================================

  get textContent(): string | undefined {
    if (this.isText()) {
      return this.content.content;
    }
    return undefined;
  }

  hasAttachments(): boolean {
    if (this.isText() && this.content.attachments) {
      return this.content.attachments.length > 0;
    }
    return false;
  }

  get attachments(): IFilePreview[] | undefined {
    if (this.isText()) {
      return this.content.attachments;
    }
    return undefined;
  }

  // =========================================================================
  // Agent Display Mode Helpers
  // =========================================================================

  getGroupedSteps(): Map<string | null, IAgentStep[]> {
    const groups = new Map<string | null, IAgentStep[]>();
    if (!this.isAgent()) return groups;

    for (const step of this.content.steps) {
      const key = step.callId || null;
      if (!groups.has(key)) {
        groups.set(key, []);
      }
      groups.get(key)!.push(step);
    }
    return groups;
  }

  getStepsByType(type: AgentStepType): IAgentStep[] {
    if (!this.isAgent()) return [];
    return this.content.steps.filter(s => s.type === type);
  }

  getStepTypes(): AgentStepType[] {
    if (!this.isAgent()) return [];
    return [...new Set(this.content.steps.map(s => s.type))];
  }

  getToolCallPairs(): Array<{ call: IAgentStep; result?: IAgentStep }> {
    if (!this.isAgent()) return [];

    const pairs: Array<{ call: IAgentStep; result?: IAgentStep }> = [];
    const resultsByCallId = new Map<string, IAgentStep>();

    for (const step of this.content.steps) {
      if (step.type === 'tool_result' && step.callId) {
        resultsByCallId.set(step.callId, step);
      }
    }

    for (const step of this.content.steps) {
      if (step.type === 'tool_call') {
        pairs.push({
          call: step,
          result: step.callId ? resultsByCallId.get(step.callId) : undefined
        });
      }
    }

    return pairs;
  }

  // =========================================================================
  // Utility Methods
  // =========================================================================

  getDisplayContent(): string {
    switch (this.content.type) {
      case 'text':
        return (this.content as ITextContent).content;
      case 'agent':
        return (this.content as IAgentContent).finalResponse || `Agent ${(this.content as IAgentContent).status}...`;
      default:
        return 'Unknown message type';
    }
  }

  computeHash(): number {
    const contentString = this.getDisplayContent();
    if (!contentString) return 0;

    return this.computeNumericHash(contentString);
  }

  private computeNumericHash(data: string): number {
    let hash = 0;
    if (data.length === 0) return hash;

    for (let i = 0; i < data.length; i++) {
      const char = data.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }

    return Math.abs(hash);
  }

  // =========================================================================
  // Serialization (IndexedDB)
  // =========================================================================

  toJSON(): any {
    return {
      id: this.id,
      conversationId: this.conversationId,
      roleName: this.roleName,
      time: this.time.toISOString(),
      version: this.version,
      lastModified: this.lastModified,
      rating: this.rating,
      content: this.content
    };
  }

  static fromJSON(data: any): Message {
    const metadata: IMessageMetadata = {
      id: data.id,
      conversationId: data.conversationId,
      roleName: data.roleName,
      time: new Date(data.time),
      version: data.version || 1,
      lastModified: data.lastModified || Math.floor(new Date(data.time).getTime() / 1000),
      rating: data.rating !== undefined ? data.rating : null
    };

    if (data.content) {
      switch (data.content.type) {
        case 'agent':
          return new Message<IAgentContent>(metadata, {
            type: 'agent',
            steps: data.content.steps || [],
            finalResponse: data.content.finalResponse || '',
            status: data.content.status || 'complete',
            error: data.content.error
          });
        case 'text':
        default:
          return new Message<ITextContent>(metadata, {
            type: 'text',
            content: data.content.content || '',
            attachments: data.content.attachments
          });
      }
    }

    return new Message<ITextContent>(metadata, {
      type: 'text',
      content: data.content || '',
      attachments: undefined
    });
  }
}

// For backwards compatibility
export type LegacyMessage = Message<ITextContent>;
