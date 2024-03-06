export interface Message {
    // The unique identifier for the message
    id: string;
    // The message contents
    content: any;
    // Whether the message was sent by the current user (important for styling and alignment)
    isUser: boolean;
    // Timestamp of the message
    time: Date;
  }
  