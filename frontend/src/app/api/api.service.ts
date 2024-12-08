import { Injectable } from '@angular/core';
import { HttpClient , HttpHeaders } from '@angular/common/http';
import { DBService } from '../data/db.service';
import { lastValueFrom } from 'rxjs';
import { Message } from '../data/objects/message';
import { environment } from '../environments/environment';
import { Conversation } from '../data/objects/conversation';


@Injectable({
  providedIn: 'root'
})
export class ApiService {
  // Use the environment configuration
  private baseUrl: string = environment.apiUrl;

  constructor(private http: HttpClient, private dbService: DBService) {
    // Development only - handle self-signed certificates
    //if (!environment.production) {
    //  process.env['NODE_TLS_REJECT_UNAUTHORIZED'] = '0';
    //}
  }

  // Headers setup method
  private getHeaders(): HttpHeaders {
    return new HttpHeaders({
      'Content-Type': 'application/json',
      // 'Authorization': `Bearer ${this.user.accessToken}`  // Add any kind of authorization here
      // Add any other headers here
    });
  }

  async getConversationsByUser(): Promise<Conversation[]>{
    // TODO: Use the authorization token from the headers instead of the userId
    const userId = 1;
    const endpoint = `${this.baseUrl}/api/conversation/byuserid/${userId}`;
    console.log('Requesting conversations...');

    try{
      const response = await lastValueFrom(
        this.http.get<Conversation[]>(endpoint, { 
          headers: this.getHeaders(), 
          observe: 'response' 
        })
      );

      console.log('Response:', response);

      if (response.status === 200 && response.body) {
        return response.body;
      } else if (response.status === 204) {
        return [];
      } else {
        throw new Error(`Unexpected response: ${response.status}`);
      }
    } catch (error) {
      console.error('Error requesting conversations:', error);
      throw error;
    }
  }

  async getConversationMessages(conversationId: number, count: number, latestTimestamp: Date | null = null): Promise<Message[]> {
    // Use the current time if no timestamp is provided
    if (latestTimestamp === null) {
      latestTimestamp = new Date();
    }
    const endpoint = `${this.baseUrl}/api/conversation/messages/${conversationId}/${Math.floor(latestTimestamp.getTime() / 1000)}/${count}`;

    try {
      const response = await lastValueFrom(
        this.http.get<Message[]>(endpoint, { 
          headers: this.getHeaders(), 
          observe: 'response' 
        })
      );

      if (response.status === 200) {
        return response.body ?? [];
      } else if (response.status === 204) {
        return [];
      } else {
        throw new Error(`Unexpected response: ${response.status}`);
      }
    } catch (error) {
      console.error('Error refreshing conversation:', error);
      throw error;
    }
  }

  async sendMessage(message: Message): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/send`;
    const body = message.toApiSend();
  
    try {
      const response = await lastValueFrom(
        this.http.post<{ id: number }>(endpoint, body, { headers: this.getHeaders(), observe: 'response' })
      );
  
      if (response.status === 201) {
        message.id = response.body!.id;
        return message;
      } else if (response.status === 400) {
        throw new Error('Bad Request: Please check the input data');
      } else if (response.status === 500) {
        throw new Error('Server Error: Please try again later');
      } else {
        throw new Error(`Unexpected response: ${response.status}`);
      }
    } catch (error) {
      console.error('Error sending message:', error);
      throw error;
    }
  }

  async generateMessage(lastMessage: Message, participant: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/generate`;
    const body = lastMessage.toApiGenerate(participant);

    try {
      const response = await lastValueFrom(
        this.http.post<any>(endpoint, body, { headers: this.getHeaders() })
      );
      return Message.fromApiGenerate(response);
    } catch (error) {
      console.error('Error generating message:', error);
      throw error;
    }
  }

  // Patch an existing message
  async patchMessage(conversationId: number, messageId: number, content: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/patch`;
    const body = {
      messageId: messageId,
      conversationId: conversationId,
      content: content
    };

    try {
      const response = await lastValueFrom(
        this.http.patch<Message>(endpoint, body, { headers: this.getHeaders() })
      );
      return response;
    } catch (error) {
      console.error('Error patching message:', error);
      throw error;
    }
  }

  // Delete a message
  async deleteMessage(conversationId: number, messageId: number): Promise<void> {
    const endpoint = `${this.baseUrl}/api/message/delete/${conversationId}/${messageId}`;

    try {
      await lastValueFrom(
        this.http.delete(endpoint, { headers: this.getHeaders() })
      );
    } catch (error) {
      console.error('Error deleting message:', error);
      throw error;
    }
  }
}
