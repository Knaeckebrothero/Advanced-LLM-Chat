import { HttpClient , HttpHeaders } from '@angular/common/http';
import { lastValueFrom } from 'rxjs';
import { Message } from '../data/interfaces/message';
import { ApiInterface } from './api-interface';


export class ApiOpenAi implements ApiInterface{
  // Variables 
  url: string = 'https://api.openai.com/v1/chat/completions'
  headers: HttpHeaders;
  body: any = {};
  
  // Inject the DataService and load the api key from the database
  constructor(apiKey: string, body: any, private http: HttpClient) {
    this.headers = new HttpHeaders({
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${apiKey}`
    });
    this.body = body;
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
      console.log([`Total characters of message body: ${jsonString.length}`, messages]);
      return messages;
    }
  }

  // Send a chat complete request to the API
  async chatComplete(messages: Message[]): Promise<any> {
    // Set the body and add the prompt
    const body = this.body;
    body.messages = this.checkTokens(body.messages.concat(messages));

    // Send the request
    try {
      // Send the request and wait for the response
      const response = this.http.post(this.url, body, { headers: this.headers });
      
      // Convert the Observable to a Promise and return it instead
      const result = await lastValueFrom(response);
      return result;
    } catch (error) {
      console.error('Error querying OpenAI API: ', error);
      throw error;
    }
  }
}
