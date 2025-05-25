import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpErrorResponse } from '@angular/common/http';
import { lastValueFrom } from 'rxjs';
import { Message } from '../data/objects/message';
import { environment } from '../environments/environment';
import { Conversation } from '../data/objects/conversation';
import { User } from '../data/objects/user';

// Interface for the backend response from /api/auth/session-info (from your current code)
interface SessionInfoResponse {
  user: {
    id: number;
    name: string;
    email: string;
  };
  token: string;
}

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private baseUrl: string = environment.apiUrl;

  constructor(
    private http: HttpClient,
  ) {
    // Development only - handle self-signed certificates (from develope version)
    //if (!environment.production) {
    //  process.env['NODE_TLS_REJECT_UNAUTHORIZED'] = '0';
    //}
    // TODO: Either enable or remove this (from develope version)
  }

  // Headers setup method - Accepts accessToken (from your current code)
  private getHeaders(accessToken?: string): HttpHeaders {
    let headers = new HttpHeaders({
      'Content-Type': 'application/json',
    });
    if (accessToken) {
      headers = headers.set('Authorization', `Bearer ${accessToken}`);
    }
    return headers;
  }

  // Method to fetch hardcoded session info (from your current code)
  async fetchSessionInfo(): Promise<{ user: User, token: string } | null> {
    const endpoint = `${this.baseUrl}/api/auth/session-info`;
    try {
      console.log('Attempting to fetch session info from backend...');
      const response = await lastValueFrom(
        this.http.get<SessionInfoResponse>(
          endpoint,
          {
            headers: this.getHeaders(), // No token needed for this specific call
            observe: 'response'
          }
        )
      );

      if (response.status === 200 && response.body) {
        console.log('Session info received from backend:', response.body);
        const backendUser = response.body.user;
        const token = response.body.token;
        const user: User = {
          id: backendUser.id,
          name: backendUser.name,
          email: backendUser.email,
          accessToken: token
        };
        return { user, token };
      } else {
        console.error('Failed to fetch session info:', response.status, response.statusText);
        return null;
      }
    } catch (error) {
      if (error instanceof HttpErrorResponse) {
        console.error('Error fetching session info (HttpErrorResponse):', error.status, error.message, error.error);
      } else {
        console.error('Error fetching session info (generic):', error);
      }
      return null;
    }
  }

  // Takes userId and accessToken (from your current code)
  async getConversationsByUser(userId: number, accessToken: string): Promise<Conversation[]>{
    const endpoint = `${this.baseUrl}/api/conversation/byuserid/${userId}`;
    console.log('Requesting conversations for user ID:', userId, "with token:", accessToken);

    try{
      const response = await lastValueFrom(
        this.http.get<any[]>(endpoint, { // Using any[] from your current code for flexibility
          headers: this.getHeaders(accessToken), // Pass accessToken
          observe: 'response'
        })
      );

      console.log('GetConversationsByUser Response:', response);

      if (response.status === 200 && response.body) {
        return response.body.map(convData => new Conversation(
          convData.id,
          convData.userId || userId,
          convData.name || `Conversation ${convData.id}`,
          convData.participants || ['user', 'Assistant']
        ));
      } else if (response.status === 204) {
        console.log('No conversations found (204)');
        return [];
      } else {
        console.error(`Unexpected response status: ${response.status}`);
        throw new Error(`Unexpected response: ${response.status}`);
      }
    } catch (error) {
      console.error('Error requesting conversations:', error);
      if (error instanceof HttpErrorResponse && error.status === 204) {
        return [];
      }
      throw error;
    }
  }

  // Takes accessToken, uses more robust response handling (from your current code)
  async getConversationMessages(conversationId: number, count: number, accessToken: string, latestTimestamp: Date | null = null): Promise<Message[]> {
    if (latestTimestamp === null) {
      latestTimestamp = new Date();
    }
    const timestampInSeconds = Math.floor(latestTimestamp.getTime() / 1000);
    const endpoint = `${this.baseUrl}/api/conversation/messages/${conversationId}/${timestampInSeconds}/${count}`;
    console.log('Requesting messages for conv ID:', conversationId, "count:", count, "token:", accessToken, "timestamp:", timestampInSeconds);

    try {
      const response = await lastValueFrom(
        this.http.get<any[]>(endpoint, {
          headers: this.getHeaders(accessToken), // Pass accessToken
          observe: 'response'
        })
      );
      console.log('GetConversationMessages Response:', response);

      if (response.status === 200 && response.body) {
        return response.body.map(messageData => Message.fromApiResponse(messageData));
      } else if (response.status === 204 || (response.status === 200 && !response.body)) {
        console.log('No messages found (204 or empty 200)');
        return [];
      } else {
        console.error(`Unexpected response status: ${response.status}`);
        throw new Error(`Unexpected response: ${response.status}`);
      }
    } catch (error) {
      console.error('Error refreshing conversation messages:', error);
      if (error instanceof HttpErrorResponse && error.status === 204) {
        return [];
      }
      throw error;
    }
  }

  // Takes accessToken, uses more robust response handling (from your current code)
  async sendMessage(message: Message, accessToken: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/send`;
    const body = message.toApiSend();
    console.log('Sending message:', body, "with token:", accessToken);

    try {
      const response = await lastValueFrom(
        this.http.post<any>(endpoint, body, { headers: this.getHeaders(accessToken), observe: 'response' }) // Pass accessToken
      );
      console.log('SendMessage Response:', response);

      if (response.status === 201 && response.body) {
        return Message.fromApiResponse(response.body);
      } else {
        console.error(`Unexpected response status: ${response.status}`);
        const errorBody = response.body?.error || `Unexpected response: ${response.status}`;
        throw new Error(errorBody);
      }
    } catch (error) {
      console.error('Error sending message:', error);
      if (error instanceof HttpErrorResponse && error.error?.error) {
        throw new Error(error.error.error);
      }
      throw error;
    }
  }

  // Takes accessToken, uses more robust response handling (from your current code)
  async generateMessage(lastMessage: Message, participant: string, accessToken: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/generate`;
    const body = lastMessage.toApiGenerate(participant);
    console.log('Generating message based on:', body, "for participant:", participant, "with token:", accessToken);

    try {
      const response = await lastValueFrom(
        this.http.post<any>(endpoint, body, { headers: this.getHeaders(accessToken), observe: 'response' }) // Pass accessToken
      );
      console.log('GenerateMessage Response:', response);

      if (response.status === 201 && response.body) {
        return Message.fromApiGenerate(response.body);
      } else {
        console.error(`Unexpected response status: ${response.status}`);
        const errorBody = response.body?.error || `Unexpected response: ${response.status}`;
        throw new Error(errorBody);
      }
    } catch (error) {
      console.error('Error generating message:', error);
      if (error instanceof HttpErrorResponse && error.error?.error) {
        throw new Error(error.error.error);
      }
      throw error;
    }
  }

  // Takes accessToken, uses corrected request body for patch, and more robust response handling (from your current code)
  async patchMessage(conversationId: number, messageId: number, content: string, accessToken: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/patch`;
    const body = { // Corrected body from your current code
      id: messageId,
      conversationId: conversationId,
      content: content
    };
    console.log('Patching message:', body, "with token:", accessToken);

    try {
      const response = await lastValueFrom(
        this.http.patch<any>(endpoint, body, { headers: this.getHeaders(accessToken), observe: 'response' }) // Pass accessToken
      );
      console.log('PatchMessage Response:', response);

      if (response.status === 200 && response.body) {
        return Message.fromApiResponse(response.body);
      } else {
        console.error(`Unexpected response status: ${response.status}`);
        const errorBody = response.body?.error || `Unexpected response: ${response.status}`;
        throw new Error(errorBody);
      }
    } catch (error) {
      console.error('Error patching message:', error);
      if (error instanceof HttpErrorResponse && error.error?.error) {
        throw new Error(error.error.error);
      }
      throw error;
    }
  }

  // Takes accessToken, uses more robust response handling (from your current code)
  async deleteMessage(conversationId: number, messageId: number, accessToken: string): Promise<void> {
    const endpoint = `${this.baseUrl}/api/message/delete/${conversationId}/${messageId}`;
    console.log('Deleting message ID:', messageId, "from conv ID:", conversationId, "with token:", accessToken);

    try {
      const response = await lastValueFrom(
        this.http.delete(endpoint, { headers: this.getHeaders(accessToken), observe: 'response' }) // Pass accessToken
      );
      console.log('DeleteMessage Response:', response);

      if (response.status === 204) {
        return;
      } else {
        console.error(`Unexpected response status for delete: ${response.status}`);
        const errorBody = response.body ? JSON.stringify(response.body) : `Unexpected response: ${response.status}`;
        throw new Error(errorBody);
      }
    } catch (error) {
      console.error('Error deleting message:', error);
      if (error instanceof HttpErrorResponse && error.status !== 204) {
        if (error.error?.error) {
          throw new Error(error.error.error);
        }
        throw error;
      } else if (!(error instanceof HttpErrorResponse)) {
        throw error;
      }
    }
  }
}
