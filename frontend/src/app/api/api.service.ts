import { Injectable } from '@angular/core';
import { HttpClient , HttpHeaders } from '@angular/common/http';
import { DBService } from '../data/db.service';
import { lastValueFrom } from 'rxjs';
import { Message } from '../data/interfaces/message';


@Injectable({
  providedIn: 'root'
})
export class ApiService {
  // Base URL for the backend API
  private baseUrl: string = 'http://localhost:8080/api';
  
  constructor(private http: HttpClient) {}

  // Headers setup method
  private getHeaders(): HttpHeaders {
    return new HttpHeaders({
      'Content-Type': 'application/json',
      // We can add authentication headers here later
    });
  }

  // Generate a new message
  async generateMessage(conversationId: number, participant?: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/message/generate`;
    const body = {
      conversation_id: conversationId,
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
  async patchMessage(messageId: number, content: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/message/${messageId}`;
    const body = {
      message_id: messageId,
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
  async deleteMessage(messageId: number): Promise<void> {
    const endpoint = `${this.baseUrl}/message/${messageId}`;

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
