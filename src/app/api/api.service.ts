import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { DataService } from '../data/db.service';


@Injectable({
  providedIn: 'root'
})
export class ApiService {
  // Variables
  private baseUrl: string = 'https://api.openai.com/v1';
  private settings: {} = {};

  // Inject the DataService and load the api key from the database
  constructor(private http: HttpClient, private dataService: DataService) {
    // Wait for the database to be ready
    this.dataService.getDatabaseReadyPromise().then(() => {
      // Load the api key from the database
      this.settings = this.dataService.getLLMConfig('openai-default');
      });
      console.log("API set up!");
  }

  // Send a request to the OpenAI API
  public async queryLLM(prompt: string): Promise<any> {
    const endpoint: string = `${this.baseUrl}/engines/davinci-codex/completions`; // You can change the engine as needed
    const headers = new HttpHeaders({
      'Content-Type': 'application/json',
      //'Authorization': `Bearer ${this.apiKey}`,
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
