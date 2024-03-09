import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { DBService } from '../data/db.service';
import { OpenAIChatCompleteRequest } from '../data/interfaces/api-openai-request';


@Injectable({
  providedIn: 'root'
})
export class OpenAIService {
  // Variables 
  private baseUrl: string = 'https://api.openai.com/v1'; // https://api.openai.com/v1/chat/completions
  private apiKey: string | undefined = undefined;
  private chatCompleteBody: OpenAIChatCompleteRequest = {
    model: 'gpt-3.5-turbo',
    messages: [],
    max_tokens: 256,
    temperature: 0.7,
  };
  
  // Inject the DataService and load the api key from the database
  constructor(private http: HttpClient, private dbService: DBService) {
    // Wait for the database to be ready
    this.dbService.getDatabaseReadyPromise().then(async () => {
      // Fetch the OpenAI settings from the database
      const defaultSettings = await this.dbService.getLLMConfig('openai-default');
  
      // If the settings are found initialize the component
      if (defaultSettings) {
        // Set API key
        this.apiKey = defaultSettings.apiKey;

        // Remove id and apiKey from the the body
        const { id, apiKey, ...rest } = defaultSettings;

        // Populate chatCompleteBody with the rest of the properties
        this.chatCompleteBody = { ...rest };
        console.log("API set up!");
      } else {
        console.error('API settings not found!');
      }
    });
  }

  // Send a request to the OpenAI API
  public async queryLLM(prompt: string): Promise<any> {
    const endpoint: string = `${this.baseUrl}/engines/davinci-codex/completions`; // You can change the engine as needed
    const headers = new HttpHeaders({
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${this.apiKey}`,
    });

    const body = {
      prompt: prompt,
      max_tokens: 150, // You can adjust the number of tokens
      temperature: 0.7, // Adjust for creativity. Lower values make responses more deterministic.
      top_p: 1.0, // Sampling probability
      frequency_penalty: 0.0, // Discourages repetition
      presence_penalty: 0.0, // Encourages new concepts
    };

    try {
      const response = await this.http.post(endpoint, body, { headers: headers }).toPromise();
      return response;
    } catch (error) {
      console.error('Error querying OpenAI:', error);
      throw error;
    }
  }
}
