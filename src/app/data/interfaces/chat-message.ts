export interface Message {
    // The unique identifier, used as the key in the database
    id?: string | null; // Optional if not used within the database
    // Surrogate Key referencing a conversation interface
    conversationID?: string; // Optional if not used within the database

    // Whether the message was sent by the user (important for styling and alignment)
    role: string;
    // The message contents (text, image, etc.)
    content: any;
    // Timestamp of the message (used for sorting and display)
    time?: Date; // Date object
}

export interface OpenAIMessage extends Message {
    // Whether the message was sent by the user (important for styling and alignment)
    role: string;
    // The message contents (text, image, etc.)
    content: any;
}
