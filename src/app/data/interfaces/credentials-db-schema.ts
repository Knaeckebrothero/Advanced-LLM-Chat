import { DBSchema } from 'idb';

export interface CredentialsDB extends DBSchema {
    openAI: {
      key: string;
      indexes: { 'by-time': Date };
    };
  }

export interface OpenAISettings {
  apiKey: string;
  defaultUrl: string;
  settings: {
    max_tokens: number;
    temperature: number;
    top_p: number;
    frequency_penalty: number;
    presence_penalty: number;
  };
}

export interface CredentialsDB extends DBSchema {
  openAI: {
    key: string;
    value: OpenAISettings;
    indexes: { 'by-time': Date };
  };
}