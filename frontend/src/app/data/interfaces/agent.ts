export interface Agent {
    // The ID used by the database
    id?: number;
    // Name of the Agent
    role: string;
    // Agent prompt
    prompt: string;
}
