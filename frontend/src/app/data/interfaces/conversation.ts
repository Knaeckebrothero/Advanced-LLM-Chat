import { Message } from './message';


// Interface for conversation data
export interface Conversation {
    // ID used to identify the conversation in the database
    id?: number;
    // Conversation Name
    name: string;
    // Participants in the conversation
    participants: string[];
}


// TODO: Put this in a class
// Function to generate a hash value for a conversation based on the messages in it.
export function hashConversation(messages: Message[]): number {
    if (!messages.length) return 0;
    
    let hashValue = 0;
    for (const message of messages) {
        // Make sure the message has content
        const content = message.content || '';
        if (!content) {
            hashValue += 0;
            continue;
        }
        
        // Add the first and last character codes, and the length of the content
        hashValue += content.charCodeAt(0);
        hashValue += content.charCodeAt(content.length - 1);
        hashValue += content.length;
        
        // Use modulo to prevent overflow
        hashValue %= (2**32);
    }
    return hashValue;
}