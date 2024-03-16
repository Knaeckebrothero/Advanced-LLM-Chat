// Interface for conversation data
export interface ConversationData {
    // ID used to identify the conversation in the database
    id?: string;
    // The number of messages part of the conversation summery
    messagesPartOfSummery: number;
    // Summary of the conversation
    summary: string;
    // List holding enviorement variables
    enviorementVariables: ConversationVariable[];
    // Characters participating in the conversation
    participants: string[];
}

// Interface for enviorement variables used in the conversation
export interface ConversationVariable {
    // Name or description of the variable
    name: string
    // Main content of the variable
    value: string
    // If the variable is optional or not
    optional: boolean
    // If the variable should be updated after every message, periodically or shoul remain static
    // renewOnUpdate: string
}