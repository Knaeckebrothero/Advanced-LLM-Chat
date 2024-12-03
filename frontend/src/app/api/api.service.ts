import { Injectable } from '@angular/core';
import { HttpClient , HttpHeaders } from '@angular/common/http';
import { DBService } from '../data/db.service';
import { lastValueFrom } from 'rxjs';
import { Message } from '../data/interfaces/message';
import { environment } from '../environments/environment';
import { MessageConverter } from '../data/interfaces/message';
import { Conversation } from '../data/interfaces/conversation';
import { ConversationConverter } from '../data/interfaces/conversation';
import { ApiConversationCheckResponse } from '../data/interfaces/conversation';
import { ApiConversationCheck } from '../data/interfaces/conversation';


@Injectable({
  providedIn: 'root'
})
export class ApiService {
  // Use the environment configuration
  private baseUrl: string = environment.apiUrl;

  constructor(private http: HttpClient) {
    // Development only - handle self-signed certificates
    //if (!environment.production) {
    //  process.env['NODE_TLS_REJECT_UNAUTHORIZED'] = '0';
    //}
  }

  // Headers setup method
  private getHeaders(): HttpHeaders {
    return new HttpHeaders({
      'Content-Type': 'application/json',
      // Add any other headers here
    });
  }

  async getConversationsByUser(userId: number): Promise<ApiConversationCheck[]>{
    const endpoint = `${this.baseUrl}/api/conversation/byuserid/${userId}`;
    console.log('Requesting conversations...');

    try{
      const response = await lastValueFrom(
        this.http.get<ApiConversationCheck[]>(endpoint, { 
          headers: this.getHeaders(), 
          observe: 'response' 
        })
      );

      if (response.status === 200) {
        return response.body!;
      } else if (response.status === 204) {
        if (response.body) {
          return [];
        } else {
          throw new Error('Unexpected response: No body');
        }
      } else {
        throw new Error(`Unexpected response: ${response.status}`);
      }

    } catch (error) {
      console.error('Error requesting conversations:', error);
      throw error;
    }
  }

  async checkConversation(conversation: Conversation, messages: Message[]): Promise<Message[]> {
    const endpoint = `${this.baseUrl}/api/conversation/check`;
    const body = {conversations: [ConversationConverter.toApiConversationCheck(conversation, messages)]};

    console.log('Checking conversation:', body);

    try {
      const response = await lastValueFrom(
        this.http.post<ApiConversationCheckResponse>(endpoint, body, { 
          headers: this.getHeaders(), 
          observe: 'response' 
        })
      );

      if (response.status === 204) {
        return [];
      } else if (response.status === 200) {
        if (response.body) {
          return response.body.messages ?? [];
        } else {
          throw new Error('Unexpected response: No body');
        }
      } else {
        throw new Error(`Unexpected response: ${response.status}`);
      }
    } catch (error) {
      console.error('Error refreshing conversation:', error);
      throw error;
    }
  }

  async refreshConversation(conversationId: number, latestTimestamp: Date): Promise<Message[]> {
    const endpoint = `${this.baseUrl}/api/conversation/refresh/${conversationId}/${Math.floor(latestTimestamp.getTime() / 1000)}`;

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
    const body = MessageConverter.toApiSend(message);
  
    try {
      const response = await lastValueFrom(
        this.http.post<{ messageId: number }>(endpoint, body, { headers: this.getHeaders(), observe: 'response' })
      );
  
      if (response.status === 201) {
        message.id = response.body!.messageId;
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
    const body = {
      conversationId: lastMessage.conversationId,
      participant: participant,
      lastTimestamp: lastMessage.time
    };

    try {
      const response = await lastValueFrom(
        this.http.post<Message>(endpoint, body, { headers: this.getHeaders() })
      );
      return response;
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
