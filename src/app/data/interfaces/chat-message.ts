export interface Message {
    // The unique identifier, used as the key in the database
    id?: string | null; // Optional if not used within the database
    // Surrogate Key referencing a conversation interface
    conversationID?: string; // Optional if not used within the database

    // The message contents (text, image, etc.)
    content: any;
    // Whether the message was sent by the user (important for styling and alignment)
    user: string;
    // Timestamp of the message (used for sorting and display)
    time: Date; // Date object
}
