// Interface for conversation data
export interface Conversation {
    // ID used to identify the conversation in the database
    id?: number;
    // Conversation Name
    name: string;
    // Participants in the conversation
    participants: string[];
}
