export interface Agent {
    // The ID used by the database
    id?: string;
    // Name of the Agent
    role: string;
    // Agent prompt
    prompt: string;
}
