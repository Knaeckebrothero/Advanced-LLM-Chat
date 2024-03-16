/*
Defines the interface for the OpenAI chat request.

Documentation:
https://platform.openai.com/docs/api-reference/chat/create?lang=node.js
*/
import { Message } from './message';


// Interface for OpenAI chat request
export interface OpenAIChatCompleteRequest {
    // The unique identifier, used as the key in the database
    id?: string | null;
    // API key used for these settings (do not include in the body of the request)
    apiKey?: string;
    // Config name set by the user to identify/describe the settings
    name?: string;

    // Temperature for setting model creativity
    temperature?: number | null;
    // Top P for setting model creativity
    top_p?: number | null;
    // Frequency penalty for setting model creativity
    frequency_penalty?: number | null;
    // Presence penalty for setting model creativity
    presence_penalty?: number | null;
    
    // The model designation
    model?: string;
    // Sequence that indecate the model to stop generating tokens (in case it occurs in the response)
    stop?: string | string[] | null;
    // Maximum number of tokens to be generated
    max_tokens?: number | null;
    // Seed for generating a response (The same seed + prompt will always produce the same result)
    seed?: number | null;
    // Number of completions to generate
    n?: number | null;

    logit_bias?: { [token: string]: number } | null;
    logprobs?: boolean | null;
    top_logprobs?: number | null;
    
    // Whether to return a webhook to stream the response or not
    stream?: boolean | null;
    // Identifier for open ai to spot sneaky horse porn
    user?: string | null;

    response_format?: OpenAIResponseFormat | null;
    tools?: OpenAITool[] | null;
    tool_choice?: ToolChoice | string | null;

    // List of messages for the model to do the chat completion for (aka the prompt)
    messages?: Message[];
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
