export interface OpenAi {
  // The unique identifier, used as the key in the database
  id: string | null;
  // API http endpoint
  url: string;
  // API key
  apiKey: string;
  // Surrogate Key referencing a settings interface
  settingsID: string;
}
