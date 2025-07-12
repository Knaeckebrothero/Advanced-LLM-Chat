import { FilePreview } from './file-preview';


/**
 * Represents the structure of a message within a conversation.
 *
 * This interface defines the essential properties that a message object must have
 * in order to be identified and associated within a conversation context.
 * It includes metadata such as sender role, timestamp, and conversation association.
 *
 * Properties:
 * - `id`: A unique identifier for the message.
 * - `conversationId`: An identifier for the conversation that the message belongs to.
 * - `roleName`: Specifies the role of the sender (e.g., user or system).
 * - `content`: The textual content of the message.
 * - `time`: The timestamp indicating when the message was sent.
 */
interface MessageInterface {
  id: number;  // Id of the message
  conversationId: number;  // Id of the conversation the message belongs to
  roleName: string;  // Role name of the participant who sent the message
  time: Date;  // Time the message was sent (in Date format)
}


export class Message {
  private metadata: MessageInterface;
  private _content: string;  // Text content of the message
  private _attachments?: FilePreview[];  // List of ids for the uploaded documents

  constructor(metadata: MessageInterface, content: string, attachments?: FilePreview[]) {
    this.metadata = metadata;
    this._content = content;
    this._attachments = attachments;
  }

  // Getter methods
  get id() { return this.metadata.id; }
  get conversationId() { return this.metadata.conversationId; }
  get roleName() { return this.metadata.roleName; }
  get time() { return this.metadata.time; }
  get content() { return this._content; }
  get attachments() { return this._attachments; }

  // Setter methods
  set id(newId: number) { this.metadata.id = newId; }
  set conversationId(newConversationId: number) { this.metadata.conversationId = newConversationId; }
  set roleName(newRoleName: string) { this.metadata.roleName = newRoleName; }
  set time(newTime: Date) { this.metadata.time = newTime; }
  set content(newContent: string) { this._content = newContent; }
  set attachments(newAttachments: FilePreview[]) { this._attachments = newAttachments; }

  // Factory method to create from API response
  static fromApiFormat(data: {
    id: number,
    conversationId: number,
    roleName: string,
    content: string,
    time: number
  }): Message {
    return new Message({
      id: data.id,
      conversationId: data.conversationId,
      roleName: data.roleName,
      time: new Date(data.time * 1000)
    }, data.content);
  }

  // Convert to API format
  toApiFormat() {
    return {
      id: this.id,
      conversationId: this.conversationId,
      roleName: this.roleName,
      content: this.content,
      time: Math.floor(this.time.getTime() / 1000)
    };
  }

  // Convert to API send format
  toApiSend() {
    if(this.attachments){
      return {
        conversationId: this.conversationId,
        roleName: this.roleName,
        content: this.content,
        time: Math.floor(this.time.getTime() / 1000),
        attachments: this.attachments // TODO: How do we handle the attachments???
      };
    }

    return {
      conversationId: this.conversationId,
      roleName: this.roleName,
      content: this.content,
      time: Math.floor(this.time.getTime() / 1000)
    };
  }

  // Convert to API patch format
  toApiPatch() {
      if (!this.id) {
          throw new Error('Cannot patch message without ID');
      } else if (!this.conversationId) {
          throw new Error('Cannot patch message without conversation ID');
      } else if (!this.content) {
          throw new Error('Cannot patch message without content');
      }
      return {
          id: this.id,
          conversationId: this.conversationId,
          content: this.content
      };
  }

  // Convert to API action format used to perform an action (e.g. regenerating or deleting the message)
  toApiAction() {
    if (!this.metadata.id) {
      throw new Error('Cannot delete message without ID');
    } else if (!this.metadata.conversationId) {
      throw new Error('Cannot delete message without conversation ID');
    }
    return {
      id: this.id,
      conversationId: this.conversationId,
    };
  }

  // TODO: Do we still need this?
  // Compute hash value for this message
  computeHash(): number {
      if (!this.content) return 0;

      let hashValue = 0;
      hashValue += this.content.charCodeAt(0);
      hashValue += this.content.charCodeAt(this.content.length - 1);
      hashValue += this.content.length;

      return hashValue % (2**32);
  }
}


export class VoiceMessage {
  // TODO: How do we implement this one?
}
