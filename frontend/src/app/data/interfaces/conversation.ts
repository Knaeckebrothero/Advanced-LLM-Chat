import { Message } from './message';


// Interface for conversation data
export interface Conversation {
    id: number;  // ID used to identify the conversation in the database
    userId: number;  // ID of the user the conversation belongs to
    name: string;  // Conversation title
    participants: string[];  // Participants in the conversation
}

interface ApiConversationBase {
    id: number; // ID used to identify the conversation in the database
}

export interface ApiConversationCheck extends ApiConversationBase {
    hashsum: number;  // Hash based on the messages in the conversation
}

export interface ApiConversationCheckResponse extends ApiConversationBase {
    messages: Message[];  // List of the current Messages from the backend.
}

/*
// Function to generate a hash value for a conversation based on the messages in it.
function hashConversation(messages: Message[]): number {
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
*/

// Class to convert between frontend and API message formats
export class ConversationConverter {
  static toApiConversationCheck(conversation: Conversation, messages: Message[]): ApiConversationCheck {
    if (conversation.id === undefined) {
        throw new Error('Cannot convert conversation without ID');
    }
    let hashValue = 0;
    
    // Check for empty conversations
    if (messages.length){
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
    }

    // Return the conversation
    return {
      id: conversation.id,
      hashsum: hashValue
    };
  }
}
