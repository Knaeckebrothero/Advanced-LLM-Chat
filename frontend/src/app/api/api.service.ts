import { Injectable } from '@angular/core';
import { HttpClient , HttpHeaders } from '@angular/common/http';
import { DBService } from '../data/db.service';
import { lastValueFrom } from 'rxjs';
import { Message } from '../data/interfaces/message';
import { environment } from '../environments/environment';


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

  // Generate a new message
  async sendMessage(conversationId: number, role: string, content: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/message/send`;
    const body = {
      conversationId: conversationId,
      role: role,
      content: content
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

  // Generate a new message
  async generateMessage(conversationId: number, participant?: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/message/generate`;
    const body = {
      conversationId: conversationId,
      participant: participant
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

  // Patch/edit an existing message
  async patchMessage(conversationId: number, messageId: number, content: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/message/patch`;
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
    const endpoint = `${this.baseUrl}/message/delete/${conversationId}/${messageId}`;

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
