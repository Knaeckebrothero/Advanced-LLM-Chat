import { Injectable } from '@angular/core';
import { HttpClient , HttpHeaders } from '@angular/common/http';
import { DBService } from '../data/db.service';
import { OpenAIChatCompleteRequest } from '../data/interfaces/api-openai-request';
import { OpenAIMessage } from '../data/interfaces/api-openai-request';
import { lastValueFrom } from 'rxjs';


@Injectable({
  providedIn: 'root'
})
export class OpenAIService {
  // Variables 
  private baseUrl: string = 'https://api.openai.com/v1';
  private apiKey: string | undefined = undefined;
  private chatCompleteBody: OpenAIChatCompleteRequest = {};
  
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
        const { id, apiKey, name, ...rest } = defaultSettings;

        // Populate chatCompleteBody with the rest of the properties
        this.chatCompleteBody = { ...rest };
        console.log("API set up!");
      } else {
        console.error('API settings not found!');
      }
    });
  }

  // Convert a conversation to an array of messages used by the openai API
  private convertConversationToMessages(conversation: any): OpenAIMessage[] {
    const messages: OpenAIMessage[] = [];
    for (const message of conversation) {
      messages.push({
        role: message.role,
        content: message.content
      });
    }
    return messages;
  }

  // Send a chat complete request to the API
  async chatComplete(messages: OpenAIMessage[]): Promise<any> {
    // Set the endpoint
    const endpoint: string = `${this.baseUrl}/chat/completions`;
    
    // Set the headers
    const headers = new HttpHeaders({
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${this.apiKey}`
    });
    
    // Set the body and add the prompt
    const body = this.chatCompleteBody;
    body.messages = messages;

    // Send the request
    try {
      console.log('Sending request to OpenAI...\n', messages);

      // Send the request and wait for the response
      const response = this.http.post(endpoint, body, { headers: headers });
      
      // Convert the Observable to Promise and return it instead
      const result = await lastValueFrom(response);
      return result;
    } catch (error) {
      console.error('Error querying OpenAI API: ', error);
      throw error;
    }
  }
}
