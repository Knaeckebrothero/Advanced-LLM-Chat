// Interface for OpenAI chat request
export interface OpenAIChatCompleteRequest {
    // The unique identifier, used as the key in the database
    id?: string | null;
    // API key used for these settings (do not include in the body of the request)
    apiKey?: string;

    // The prompt messages
    messages?: OpenAIMessage[];
    // The model designation
    model: string;
    frequency_penalty?: number | null;
    logit_bias?: { [token: string]: number } | null;
    logprobs?: boolean | null;
    top_logprobs?: number | null;
    max_tokens?: number | null;
    n?: number | null;
    presence_penalty?: number | null;
    response_format?: OpenAIResponseFormat | null;
    seed?: number | null;
    stop?: string | string[] | null;
    stream?: boolean | null;
    temperature?: number | null;
    top_p?: number | null;
    tools?: OpenAITool[] | null;
    tool_choice?: ToolChoice | string | null;
    user?: string | null;
}
  
// Interface for a OpenAI message (as part of the chat complete chathistory array)
export interface OpenAIMessage {
    role: 'system' | 'user' | 'assistant';
    content: string;
}

// Interface for the OpenAI response format
interface OpenAIResponseFormat {
type: string;
// Add additional properties as needed, depending on the response format options
}

// Interface for a OpenAI tool
interface OpenAITool {
// Define the tool properties according to your requirements
}

// Type for the tool choice
type ToolChoice = 'none' | 'auto' | { type: 'function', function: { name: string } };
