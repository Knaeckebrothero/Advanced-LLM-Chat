import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpErrorResponse } from '@angular/common/http';
import { lastValueFrom } from 'rxjs';
import { Message } from '../data/objects/message';
import { environment } from '../environments/environment';
import { Conversation } from '../data/objects/conversation';
import { User } from '../data/objects/user';

// --- Start: Added for hardcoded session ---
// Interface for the backend response from /api/auth/session-info
interface SessionInfoResponse {
  user: {
    id: number;
    name: string;
    email: string;
  };
  token: string;
}
// --- End: Added for hardcoded session ---

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private baseUrl: string = environment.apiUrl;

  constructor(
    private http: HttpClient,
  ) {}

  private getHeaders(accessToken?: string): HttpHeaders {
    let headers = new HttpHeaders({
      'Content-Type': 'application/json',
    });
    if (accessToken) {
      headers = headers.set('Authorization', `Bearer ${accessToken}`);
    }
    return headers;
  }

  // --- Start: Method to fetch hardcoded session info ---
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
        // Construct the User object as expected by the frontend
        const user: User = {
          id: backendUser.id,
          name: backendUser.name,
          email: backendUser.email,
          accessToken: token // Store the received token as accessToken
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
  // --- End: Method to fetch hardcoded session info ---


  async getConversationsByUser(userId: number, accessToken: string): Promise<Conversation[]>{
    const endpoint = `${this.baseUrl}/api/conversation/byuserid/${userId}`;
    console.log('Requesting conversations for user ID:', userId, "with token:", accessToken);

    try{
      const response = await lastValueFrom(
        this.http.get<any[]>(endpoint, { // Expecting any[] because backend might return non-standard Conversation objects
          headers: this.getHeaders(accessToken),
          observe: 'response'
        })
      );

      console.log('GetConversationsByUser Response:', response);

      if (response.status === 200 && response.body) {
        // Manually construct Conversation objects if necessary, or ensure backend sends compatible structure
        return response.body.map(convData => new Conversation(
          convData.id,
          convData.userId || userId, // Fallback to passed userId if not in response
          convData.name || `Conversation ${convData.id}`,
          convData.participants || ['user', 'Assistant']
          // Add hashsum if backend provides it directly and it's needed here
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
        return []; // Handle 204 specifically if it comes as an error
      }
      throw error;
    }
  }

  async getConversationMessages(conversationId: number, count: number, accessToken: string, latestTimestamp: Date | null = null): Promise<Message[]> {
    if (latestTimestamp === null) {
      latestTimestamp = new Date(); // Default to now if not provided
    }
    // Ensure timestamp is in seconds for the API
    const timestampInSeconds = Math.floor(latestTimestamp.getTime() / 1000);
    const endpoint = `${this.baseUrl}/api/conversation/messages/${conversationId}/${timestampInSeconds}/${count}`;
    console.log('Requesting messages for conv ID:', conversationId, "count:", count, "token:", accessToken, "timestamp:", timestampInSeconds);

    try {
      const response = await lastValueFrom(
        this.http.get<any[]>(endpoint, {
          headers: this.getHeaders(accessToken),
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
        return []; // Handle 204 specifically if it comes as an error
      }
      throw error;
    }
  }

  async sendMessage(message: Message, accessToken: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/send`;
    const body = message.toApiSend();
    console.log('Sending message:', body, "with token:", accessToken);

    try {
      // Backend currently returns the full message object on successful send, not just {id: number}
      const response = await lastValueFrom(
        this.http.post<any>(endpoint, body, { headers: this.getHeaders(accessToken), observe: 'response' })
      );
      console.log('SendMessage Response:', response);


      if (response.status === 201 && response.body) {
        // Assuming backend returns the full message object including the new ID
        return Message.fromApiResponse(response.body);
      } else {
        console.error(`Unexpected response status: ${response.status}`);
        // Try to parse error from body if available
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

  async generateMessage(lastMessage: Message, participant: string, accessToken: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/generate`;
    const body = lastMessage.toApiGenerate(participant);
    console.log('Generating message based on:', body, "for participant:", participant, "with token:", accessToken);

    try {
      const response = await lastValueFrom(
        this.http.post<any>(endpoint, body, { headers: this.getHeaders(accessToken), observe: 'response' })
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

  async patchMessage(conversationId: number, messageId: number, content: string, accessToken: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/patch`;
    // The backend patch request body in backend_mockup.py is {id: int, conversationId: int, content: str}
    // The frontend api.service.ts was sending {messageId: number, conversationId: number, content: string}
    // Aligning frontend to send what backend expects:
    const body = {
      id: messageId, // Changed from messageId
      conversationId: conversationId,
      content: content
    };
    console.log('Patching message:', body, "with token:", accessToken);


    try {
      // Backend returns the patched message object or similar
      const response = await lastValueFrom(
        this.http.patch<any>(endpoint, body, { headers: this.getHeaders(accessToken), observe: 'response' })
      );
      console.log('PatchMessage Response:', response);

      if (response.status === 200 && response.body) {
        // Assuming backend returns the updated message data that can be converted to a Message object
        return Message.fromApiResponse(response.body); // Or handle as appropriate
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

  async deleteMessage(conversationId: number, messageId: number, accessToken: string): Promise<void> {
    const endpoint = `${this.baseUrl}/api/message/delete/${conversationId}/${messageId}`;
    console.log('Deleting message ID:', messageId, "from conv ID:", conversationId, "with token:", accessToken);

    try {
      const response = await lastValueFrom(
        this.http.delete(endpoint, { headers: this.getHeaders(accessToken), observe: 'response' })
      );
      console.log('DeleteMessage Response:', response);


      if (response.status === 204) { // Backend confirms deletion with 204 No Content
        return;
      } else {
        // This case should ideally not be reached if backend correctly returns 204 or an error status.
        console.error(`Unexpected response status for delete: ${response.status}`);
        const errorBody = response.body ? JSON.stringify(response.body) : `Unexpected response: ${response.status}`;
        throw new Error(errorBody);
      }
    } catch (error) {
      console.error('Error deleting message:', error);
      if (error instanceof HttpErrorResponse && error.status !== 204) { // Allow 204 to pass as success
        if (error.error?.error) {
          throw new Error(error.error.error);
        }
        throw error; // Rethrow original HttpErrorResponse if no specific error message in body
      } else if (!(error instanceof HttpErrorResponse)) {
        throw error; // Rethrow non-HTTP errors
      }
      // If it's an HttpErrorResponse with status 204, it's a success, so do nothing here.
    }
  }
}
