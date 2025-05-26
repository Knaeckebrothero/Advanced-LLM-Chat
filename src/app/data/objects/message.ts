export interface MessageData {
  id: number;
  conversationId: number;
  roleName: string;
  content: string;
  time: number; // Typically a Unix timestamp (in seconds or milliseconds from the API)
}

export class Message {
  id: number;  // Id of the message
  conversationId: number;  // Id of the conversation the message belongs to
  roleName: string;  // Role name of the participant who sent the message
  content: string;  // Content of the message
  time: Date;  // Time the message was sent (in Date format)

  constructor(data: {
    id: number,
    // Make sure conversationId can be null here if Message objects can represent messages for a not-yet-saved conversation
    conversationId: number | null, // Allowing null to match Conversation.id potential null state
    roleName: string,
    content: string,
    time: Date | number // number here is typically a Unix timestamp
  }) {
    this.id = data.id;
    // Handle null conversationId carefully. If a message must have one, enforce it.
    // For now, assuming it can be null if the parent conversation's ID is null.
    this.conversationId = data.conversationId as number; // Casting for now, review based on logic for new convos
    this.roleName = data.roleName;
    this.content = data.content;
    // If data.time is a number, it's assumed to be seconds for consistency with toApiSend
    this.time = data.time instanceof Date ? data.time : new Date(data.time * 1000);
  }

  // Factory method to create from API response, uses MessageData type
  static fromApiResponse(data: MessageData): Message {
    return new Message({
      id: data.id,
      conversationId: data.conversationId,
      roleName: data.roleName,
      content: data.content,
      time: data.time // Constructor handles conversion from number (timestamp) to Date
    });
  }

  // Convert to API send format
  toApiSend() {
    // console.log(Math.floor(this.time.getTime() / 1000))
    return {
      // conversationId can be null if the Message object holds a null ID
      conversationId: this.conversationId,
      roleName: this.roleName,
      content: this.content,
      time: Math.floor(this.time.getTime() / 1000) // Time in seconds
    };
  }

  // Convert from API send format - This seems redundant if fromApiResponse exists
  // and backend returns a consistent MessageData structure.
  // Consider if this is truly needed or if fromApiResponse covers it.
  static fromApiSend(data: MessageData & { id: number }): Message { // Assuming id might be confirmed here
    return new Message({
      id: data.id,
      conversationId: data.conversationId,
      roleName: data.roleName,
      content: data.content,
      time: data.time
    });
  }

  // Convert to API generate format
  toApiGenerate(participant: string) {
    return {
      conversationId: this.conversationId,
      roleName: participant,
      time: Math.floor(this.time.getTime() / 1000)
    };
  }

  // Convert from API generate format - similar to fromApiSend, check redundancy
  static fromApiGenerate(data: MessageData & { id: number }): Message {
    return new Message({
      id: data.id,
      conversationId: data.conversationId,
      roleName: data.roleName,
      content: data.content,
      time: data.time
    });
  }

  // Convert to API patch format
  toApiPatch() {
    if (!this.id) {
      throw new Error('Cannot patch message without ID');
    }
    return {
      id: this.id,
      conversationId: this.conversationId,
      content: this.content
    };
  }

  // Method to update content
  updateContent(newContent: string) {
    this.content = newContent;
  }

  // Compute hash value for this message
  computeHash(): number {
    if (!this.content) return 0;

    let hashValue = 0;
    hashValue += this.content.charCodeAt(0);
    hashValue += this.content.charCodeAt(this.content.length - 1);
    hashValue += this.content.length;

    return hashValue % (2 ** 32);
  }
}
