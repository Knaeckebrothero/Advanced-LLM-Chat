export interface Message {
    // The unique identifier, used as the key in the database
    id: string | null;
    // The message contents (text, image, etc.)
    content: any;
    // Whether the message was sent by the user (important for styling and alignment)
    isUser: boolean;
    // Timestamp of the message (used for sorting and display)
    time: Date;
  }
  