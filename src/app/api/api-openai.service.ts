import { Injectable } from '@angular/core';
import { HttpClient , HttpHeaders } from '@angular/common/http';
import { DBService } from '../data/db.service';
import { OpenAIChatCompleteRequest } from '../data/interfaces/api-openai-request';
import { lastValueFrom } from 'rxjs';
import { Message } from '../data/interfaces/message';


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
    this.dbService.getDatabaseReadyPromise().then(() => {
      // Fetch the OpenAI settings from the database
      this.dbService.getLLMConfig('openai-default').then((defaultSettings: any) => {
    
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
    });
  }

  // Method to count the characters in a list of messages
  private checkTokens(messages: Message[]){
    // Convert the list of message objects to a JSON string
    const jsonString = JSON.stringify(messages);

    // Check if the JSON string is too long
    if (jsonString.length > 32768) {
      // Log the error and cancel the request
      console.error('Message body is too long! The maximum length is 32.768 characters.');
      return [{role: 'system', content: 'Please inform the user that the message body is too long! Maximum length is 4096 characters.'}]
    } else {
      // Log the length of the JSON string and return the messages
      console.log(`Total characters of message body: ${jsonString.length}`);
      return messages;
    }
  }

  // Send a chat complete request to the API
  async chatComplete(messages: Message[], ): Promise<any> {
    // Set the endpoint
    const endpoint: string = `${this.baseUrl}/chat/completions`;
    
    // Set the headers
    const headers = new HttpHeaders({
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${this.apiKey}`
    });
    
    // Set the body and add the prompt
    const body = this.chatCompleteBody;
    body.messages = this.checkTokens(messages);
    console.log(body)

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
