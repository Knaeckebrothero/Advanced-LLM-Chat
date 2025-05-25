import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpErrorResponse } from '@angular/common/http'; // Added HttpErrorResponse for better error handling in login example
// DBService is not directly used here for token, it's passed in.
// import { DBService } from '../data/db.service';
import { lastValueFrom } from 'rxjs';
import { Message } from '../data/objects/message';
import { environment } from '../environments/environment';
import { Conversation } from '../data/objects/conversation';
import { User } from '../data/objects/user'; // Import User for loginAndFetchSessionToken

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private baseUrl: string = environment.apiUrl;

  constructor(
    private http: HttpClient,
    // private dbService: DBService // Not strictly needed here if token is passed
  ) {}

  // Modified to accept an optional accessToken
  private getHeaders(accessToken?: string): HttpHeaders {
    let headers = new HttpHeaders({
      'Content-Type': 'application/json',
    });
    if (accessToken) {
      headers = headers.set('Authorization', `Bearer ${accessToken}`);
    }
    // Add any other headers here
    return headers;
  }

  // --- Commented-out method for future session token fetching ---
  /*
  async loginAndFetchSessionToken(credentials: { email: string, password: string }): Promise<{ user: User, token: string } | null> {
    const endpoint = `${this.baseUrl}/api/auth/login`; // Example login endpoint
    try {
      console.log('Attempting to login and fetch session token...');
      const response = await lastValueFrom(
        this.http.post<{ user: User, token: string }>(
          endpoint,
          credentials,
          {
            headers: this.getHeaders(), // Initial headers, token might be set by backend in cookie or response
            observe: 'response'
          }
        )
      );

      if (response.status === 200 && response.body) {
        console.log('Login successful, session token received/user data:', response.body);
        // The backend would typically return user info and the session token.
        // This token and user info should then be stored, likely by calling a method
        // in an AuthService or DBService that handles cookie and IndexedDB storage.
        // Example:
        // await someAuthService.storeUserSession(response.body.user, response.body.token);
        return response.body;
      } else {
        console.error('Login failed:', response.status, response.statusText);
        return null;
      }
    } catch (error) {
      if (error instanceof HttpErrorResponse) {
        console.error('Error during login (HttpErrorResponse):', error.status, error.message, error.error);
      } else {
        console.error('Error during login (generic):', error);
      }
      return null;
    }
  }
  */
  // --- END: Commented-out method ---

  async getConversationsByUser(userId: number, accessToken: string): Promise<Conversation[]>{ // Added userId and accessToken parameters
    const endpoint = `${this.baseUrl}/api/conversation/byuserid/${userId}`;
    console.log('Requesting conversations for user ID:', userId, "");

    try{
      const response = await lastValueFrom(
        this.http.get<Conversation[]>(endpoint, {
          headers: this.getHeaders(accessToken), // Use accessToken
          observe: 'response'
        })
      );

      console.log('Response:', response, "");

      if (response.status === 200 && response.body) {
        return response.body;
      } else if (response.status === 204) {
        return [];
      } else {
        throw new Error(`Unexpected response: ${response.status}`);
      }
    } catch (error) {
      console.error('Error requesting conversations:', error, "");
      throw error;
    }
  }

  async getConversationMessages(conversationId: number, count: number, accessToken: string, latestTimestamp: Date | null = null): Promise<Message[]> { // Added accessToken
    if (latestTimestamp === null) {
      latestTimestamp = new Date();
    }
    const endpoint = `${this.baseUrl}/api/conversation/messages/${conversationId}/${Math.floor(latestTimestamp.getTime() / 1000)}/${count}`;

    try {
      const response = await lastValueFrom(
        this.http.get<any[]>(endpoint, {
          headers: this.getHeaders(accessToken), // Use accessToken
          observe: 'response'
        })
      );

      if (response.status === 200 && response.body) {
        return response.body.map(messageData => Message.fromApiResponse(messageData));
      } else if (response.status === 204 && !response.body) {
        return [];
      } else {
        throw new Error(`Unexpected response: ${response.status}`);
      }
    } catch (error) {
      console.error('Error refreshing conversation:', error, "");
      throw error;
    }
  }

  async sendMessage(message: Message, accessToken: string): Promise<Message> { // Added accessToken
    const endpoint = `${this.baseUrl}/api/message/send`;
    const body = message.toApiSend();

    try {
      const response = await lastValueFrom(
        this.http.post<{ id: number }>(endpoint, body, { headers: this.getHeaders(accessToken), observe: 'response' }) // Use accessToken
      );

      if (response.status === 201 && response.body) {
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
      console.error('Error sending message:', error, "");
      throw error;
    }
  }

  async generateMessage(lastMessage: Message, participant: string, accessToken: string): Promise<Message> { // Added accessToken
    const endpoint = `${this.baseUrl}/api/message/generate`;
    const body = lastMessage.toApiGenerate(participant);

    try {
      const response = await lastValueFrom(
        this.http.post<any>(endpoint, body, { headers: this.getHeaders(accessToken) }) // Use accessToken
      );
      return Message.fromApiGenerate(response);
    } catch (error) {
      console.error('Error generating message:', error, "");
      throw error;
    }
  }

  async patchMessage(conversationId: number, messageId: number, content: string, accessToken: string): Promise<Message> { // Added accessToken
    const endpoint = `${this.baseUrl}/api/message/patch`;
    const body = {
      messageId: messageId,
      conversationId: conversationId,
      content: content
    };

    try {
      const response = await lastValueFrom(
        this.http.patch<Message>(endpoint, body, { headers: this.getHeaders(accessToken) }) // Use accessToken
      );
      return response;
    } catch (error) {
      console.error('Error patching message:', error, "");
      throw error;
    }
  }

  async deleteMessage(conversationId: number, messageId: number, accessToken: string): Promise<void> { // Added accessToken
    const endpoint = `${this.baseUrl}/api/message/delete/${conversationId}/${messageId}`;

    try {
      await lastValueFrom(
        this.http.delete(endpoint, { headers: this.getHeaders(accessToken) }) // Use accessToken
      );
    } catch (error) {
      console.error('Error deleting message:', error, "");
      throw error;
    }
  }
}
