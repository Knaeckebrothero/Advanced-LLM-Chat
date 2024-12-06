export class Message {
  id?: number;  // Id of the message
  conversationId: number;  // Id of the conversation the message belongs to
  roleName: string;  // Role name of the participant who sent the message
  content: string;  // Content of the message
  time: Date;  // Time the message was sent (in Date format)

  constructor(data: {
      id?: number,
      conversationId: number,
      roleName: string,
      content: string,
      time: Date | number
  }) {
      this.id = data.id;
      this.conversationId = data.conversationId;
      this.roleName = data.roleName;
      this.content = data.content;
      this.time = data.time instanceof Date ? data.time : new Date(data.time * 1000);
  }

  // Factory method to create from API response
  static fromApiResponse(data: {
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
          content: data.content,
          time: data.time
      });
  }

  // Convert to API send format
  toApiSend() {
      return {
          conversationId: this.conversationId,
          roleName: this.roleName,
          content: this.content,
          time: Math.floor(this.time.getTime() / 1000)
      };
  }

  // Convert to API generate format
  toApiGenerate(participant: string) {
      return {
          conversationId: this.conversationId,
          roleName: participant,
          time: Math.floor(this.time.getTime() / 1000)
      };
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
      
      return hashValue % (2**32);
  }
}
