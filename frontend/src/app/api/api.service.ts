import { Injectable } from '@angular/core';
import { HttpClient , HttpHeaders } from '@angular/common/http';
import { DBService } from '../data/db.service';
import { lastValueFrom } from 'rxjs';
import { Message } from '../data/interfaces/message';


@Injectable({
  providedIn: 'root'
})
export class ApiService {
  // Variables 
  private baseUrl: string = 'http://localhost:8080/';
  private apiKey: string = '';
  
  // Inject the DataService and load the api key from the database
  constructor(private http: HttpClient, private dbService: DBService) {
    // Wait for the database to be ready
    this.dbService.getDatabaseReadyPromise().then(() => {
      // Fetch the OpenAI settings from the database
      this.dbService.getLLMConfig(1).then((defaultSettings: any) => {
    
        // If the settings are found initialize the component
        if (defaultSettings) {
          // Set API key
          this.apiKey = defaultSettings.apiKey;
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
  async chatComplete(message: Message): Promise<any> {
    // Set the endpoint
    const endpoint: string = `${this.baseUrl}/chat/completions`;

    // Set the headers
    const headers = new HttpHeaders({
      'Content-Type': 'application/json',
      'Authorization': this.apiKey,
      'Response-Expected': 1
    });
    
    // Set the body and add the prompt
    const body = message;
    console.log(body)

    // Send the request
    try {
      console.log('Sending message...\n');

      // Send the message and wait for the response
      // const response = this.http.post(endpoint, body, { headers: headers });
      
      // Convert the Observable to Promise and return it instead
      // const result = await lastValueFrom(response);

      // Return a dummy response for testing
      const result = body;

      return result;
    } catch (error) {
      console.error('Error while sending request to backend: ', error);
      throw error;
    }
  }
}
