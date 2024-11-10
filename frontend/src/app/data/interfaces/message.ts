export interface Message {
    // The unique identifier, used as the key in the database
    id?: number;
    // Surrogate Key referencing a conversation
    conversationID?: number;
    // Whether the message was sent by the user (important for styling and alignment)
    role: string;
    // The message contents (text, image, etc.)
    content: any;
    // Timestamp of the message (used for sorting and display, can be a Date or a unix timestamp as a number)
    //time?: Date | number;
    time?: Date;
}
