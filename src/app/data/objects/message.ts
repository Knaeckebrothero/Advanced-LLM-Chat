import { FilePreview, UploadStatus, FilePreviewUtil } from './file-preview';

/**
 * Message Type System
 *
 * This file uses a hybrid approach with TypeScript discriminated unions
 * to support multiple message types (text, voice, etc.) while maintaining
 * type safety and backwards compatibility.
 *
 * File Handling:
 * - We use the existing FilePreview system for file attachments
 * - FilePreview contains the actual File object and tracks upload progress
 * - When sending to the API, we only send file references (FileAttachment)
 * - When receiving from the API, we reconstruct FilePreview objects
 */

/**
 * Represents the metadata structure of a message within a conversation.
 *
 * This interface defines the essential properties that all message types share,
 * providing identification and association within a conversation context.
 */
interface MessageMetadata {
  id: number;  // Unique identifier for the message
  conversationId: string;  // Id of the conversation (UUID)
  roleName: string;  // Role name of the participant who sent the message
  time: Date;  // Time the message was sent (in Date format)
  version?: number;  // Version number for optimistic locking
  lastModified?: number;  // Unix timestamp of last modification
}

/**
 * Minimal file attachment info for API communication
 * This is what we send to the server after files are uploaded
 */
interface FileAttachment {
  fileId: string;      // Server-assigned ID
  fileName: string;
  fileSize: number;
  mimeType: string;
}

/**
 * Text message content with optional attachments
 *
 * Note on file handling:
 * - attachments: FilePreview[] - Used locally, contains File objects and upload status
 * - When sending to API, we extract just the file references (FileAttachment)
 * - When receiving from API, we reconstruct FilePreview objects
 */
interface TextContent {
  type: 'text';
  content: string;
  attachments?: FilePreview[];      // Full FilePreview objects for local state
}

/**
 * Voice message content
 */
interface VoiceContent {
  type: 'voice';
  audioData: string;  // base64 encoded audio
  duration: number;  // in seconds
  mimeType: string;
  transcript?: string;  // Optional transcript for accessibility
  waveform?: number[];  // Optional waveform data for visualization
}

// Union type for all possible message content types
type MessageContent = TextContent | VoiceContent;

/**
 * Main Message class that handles all message types
 * Uses generics to provide type safety for specific content types
 */
export class Message<T extends MessageContent = MessageContent> {
  constructor(
    private metadata: MessageMetadata,
    public content: T
  ) {}

  // Getters for metadata
  get id() { return this.metadata.id; }
  get conversationId() { return this.metadata.conversationId; }
  get roleName() { return this.metadata.roleName; }
  get time() { return this.metadata.time; }
  get type() { return this.content.type; }
  get version() { return this.metadata.version || 1; }
  get lastModified() { return this.metadata.lastModified || Math.floor(this.time.getTime() / 1000); }

  // Setters for metadata (maintaining compatibility with existing code)
  set id(newId: number) { this.metadata.id = newId; }
  set conversationId(newConversationId: string) { this.metadata.conversationId = newConversationId; }
  set roleName(newRoleName: string) { this.metadata.roleName = newRoleName; }
  set time(newTime: Date) { this.metadata.time = newTime; }
  set version(newVersion: number) { this.metadata.version = newVersion; }
  set lastModified(newLastModified: number) { this.metadata.lastModified = newLastModified; }

  // Factory method for creating text messages
  static createText(
    metadata: MessageMetadata,
    content: string,
    attachments?: FilePreview[]
  ): Message<TextContent> {
    return new Message(metadata, {
      type: 'text',
      content,
      attachments
    });
  }

  // Factory method for creating voice messages
  static createVoice(
    metadata: MessageMetadata,
    audioData: string,
    duration: number,
    mimeType: string,
    transcript?: string,
    waveform?: number[]
  ): Message<VoiceContent> {
    return new Message(metadata, {
      type: 'voice',
      audioData,
      duration,
      mimeType,
      transcript,
      waveform
    });
  }

  // Factory method to create from API response (backwards compatibility)
  static fromApiResponse(data: any): Message {
    // Generate ID if not provided by server
    const messageId = data.id || Math.floor(Date.now() / 1000) + Math.floor(Math.random() * 1000);
    
    const metadata: MessageMetadata = {
      id: messageId,
      conversationId: data.conversationId,
      roleName: data.roleName,
      time: new Date(data.time * 1000),
      version: data.version || 1,
      lastModified: data.lastModified || data.time
    };

    // Determine message type based on data
    if (data.type === 'voice' && data.audioData) {
      return Message.createVoice(
        metadata,
        data.audioData,
        data.duration,
        data.mimeType,
        data.transcript,
        data.waveform
      );
    } else {
      // Convert attachment references from API to FilePreview objects
      let attachments: FilePreview[] | undefined;
      if (data.attachments && Array.isArray(data.attachments)) {
        attachments = data.attachments.map((ref: any) => ({
          id: ref.fileId || ref.id,
          file: new File([], ref.fileName || ref.name || 'unknown'), // Placeholder
          name: ref.fileName || ref.name || 'unknown',
          size: ref.fileSize || ref.size || 0,
          sizeFormatted: FilePreviewUtil.formatFileSize(ref.fileSize || ref.size || 0),
          type: FilePreviewUtil.getFileType(ref.mimeType || 'application/octet-stream'),
          mimeType: ref.mimeType || 'application/octet-stream',
          uploadStatus: UploadStatus.COMPLETED
        }));
      }

      // Default to text message for backwards compatibility
      return Message.createText(
        metadata,
        data.content || '',
        attachments
      );
    }
  }

  // Convert to API send format
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
        // For API, we only send the attachment references, not the full FilePreview objects
        // Only include files that have completed uploading
        const attachmentRefs = this.content.attachments
          ?.filter(a => a.uploadStatus === UploadStatus.COMPLETED)
          .map(a => ({
            fileId: a.id,
            fileName: a.name,
            fileSize: a.size,
            mimeType: a.mimeType
          }));

        return {
          ...base,
          content: this.content.content,
          ...(attachmentRefs && attachmentRefs.length > 0 && { attachments: attachmentRefs })
        };

      case 'voice':
        return {
          ...base,
          audioData: this.content.audioData,
          duration: this.content.duration,
          mimeType: this.content.mimeType,
          ...(this.content.transcript && { transcript: this.content.transcript }),
          ...(this.content.waveform && { waveform: this.content.waveform })
        };

      default:
        // Type guard - this should never happen
        const _exhaustive: never = this.content;
        throw new Error(`Unknown message type: ${(_exhaustive as any).type}`);
    }
  }

  // Convert to API generate format
  toApiGenerate(participant: string) {
    return {
      conversationId: this.conversationId,
      roleName: participant,
      time: Math.floor(this.time.getTime() / 1000),
      type: this.content.type
    };
  }

  // Convert to API patch format (only for text messages)
  toApiPatch() {
    if (!this.id) {
      throw new Error('Cannot patch message without ID');
    }
    if (!this.conversationId) {
      throw new Error('Cannot patch message without conversation ID');
    }

    // Only text messages can be patched
    if (this.content.type !== 'text') {
      throw new Error(`Cannot patch ${this.content.type} messages`);
    }

    return {
      id: this.id,
      conversationId: this.conversationId,
      content: this.content.content
    };
  }

  // Convert to API delete format
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

  // Type guards for type-safe content access
  isText(): this is Message<TextContent> {
    return this.content.type === 'text';
  }

  isVoice(): this is Message<VoiceContent> {
    return this.content.type === 'voice';
  }

  // Get text content (for backwards compatibility)
  get textContent(): string | undefined {
    if (this.isText()) {
      return this.content.content;
    }
    return undefined;
  }

  // Check if message has attachments
  hasAttachments(): boolean {
    if (this.isText() && this.content.attachments) {
      return this.content.attachments.length > 0;
    }
    return false;
  }

  // Get attachments (for backwards compatibility)
  get attachments(): FilePreview[] | undefined {
    if (this.isText()) {
      return this.content.attachments;
    }
    return undefined;
  }

  // Utility method to get display content
  getDisplayContent(): string {
    switch (this.content.type) {
      case 'text':
        return this.content.content;
      case 'voice':
        return `🎤 Voice message (${this.formatDuration(this.content.duration)})`;
      default:
        return 'Unknown message type';
    }
  }

  // Helper to format duration
  private formatDuration(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }

  // Compute hash value for this message (kept for compatibility)
  computeHash(): number {
    const contentString = this.getDisplayContent();
    if (!contentString) return 0;

    // Use proper hash function from utility
    return this.computeNumericHash(contentString);
  }

  private computeNumericHash(data: string): number {
    let hash = 0;
    if (data.length === 0) return hash;
    
    for (let i = 0; i < data.length; i++) {
      const char = data.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    
    return Math.abs(hash);
  }

  // Serialization method for IndexedDB storage
  toJSON(): any {
    return {
      id: this.id,
      conversationId: this.conversationId,
      roleName: this.roleName,
      time: this.time.toISOString(), // Store as ISO string for consistent serialization
      version: this.version,
      lastModified: this.lastModified,
      content: this.content
    };
  }

  // Deserialization method from IndexedDB
  static fromJSON(data: any): Message {
    const metadata: MessageMetadata = {
      id: data.id,
      conversationId: data.conversationId,
      roleName: data.roleName,
      time: new Date(data.time),
      version: data.version || 1,
      lastModified: data.lastModified || Math.floor(new Date(data.time).getTime() / 1000)
    };

    // Handle different content types
    if (data.content) {
      switch (data.content.type) {
        case 'voice':
          return new Message<VoiceContent>(metadata, data.content);
        case 'text':
        default:
          // Ensure FilePreview objects are properly reconstructed
          const content: TextContent = {
            type: 'text',
            content: data.content.content || '',
            attachments: data.content.attachments
          };
          return new Message<TextContent>(metadata, content);
      }
    }

    // Fallback for legacy data without type field
    return new Message<TextContent>(metadata, {
      type: 'text',
      content: data.content || '',
      attachments: undefined
    });
  }
}

// For backwards compatibility - export a type for the old Message structure
export type LegacyMessage = Message<TextContent>;
