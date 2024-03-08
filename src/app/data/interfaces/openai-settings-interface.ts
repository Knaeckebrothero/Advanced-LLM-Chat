export interface OpenAi {
  // The unique identifier, used as the key in the database
  id: string | null;
  // OpenAI API key
  apiKey: string;
  // OpenAI API settings
  settings: {
    max_tokens: number;
    temperature: number;
    top_p: number;
    frequency_penalty: number;
    presence_penalty: number;
  };
}
