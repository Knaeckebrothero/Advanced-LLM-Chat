import {Injectable} from '@angular/core';
import {HttpClient, HttpErrorResponse, HttpHeaders} from '@angular/common/http';
import {lastValueFrom} from 'rxjs';
import {Message, MessageData} from '../data/objects/message';
import {environment} from '../environments/environment';
import {Conversation} from '../data/objects/conversation';
import {User} from '../data/objects/user';
import {AuthService} from '../auth/auth.service';

// Interface for the backend response from /api/auth/session-info
interface SessionInfoResponse {
  user: {
    id: number;
    name: string;
    email: string;
  };
  token: string;
}

// Interface for the backend response from /api/message/send
interface SendMessageApiResponse {
  message: MessageData;
  conversation?: ConversationData;
}

// Interface for raw conversation data from backend
interface ConversationData {
  id: number;
  hashsum: number;
  userId: number;
  name: string;
  participants: string[];
}


@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private baseUrl: string = environment.apiUrl;

  constructor(
    private http: HttpClient,
    private authService: AuthService
  ) {
  }

  private getHeaders(includeAuth: boolean = true): HttpHeaders {
    let headers = new HttpHeaders({
      'Content-Type': 'application/json',
    });

    if (includeAuth) {
      const token = this.authService.getToken();
      if (token) {
        headers = headers.set('Authorization', `Bearer ${token}`);
      }
    }

    return headers;
  }

  async fetchSessionInfo(): Promise<{ user: User, token: string } | null> {
    const endpoint = `${this.baseUrl}/api/auth/session-info`;
    try {
      console.log('ApiService: Attempting to fetch session info...');
      const response = await lastValueFrom(
        this.http.get<SessionInfoResponse>(endpoint, {headers: this.getHeaders(), observe: 'response'})
      );

      if (response.status === 200 && response.body) {
        console.log('ApiService: Session info received:', response.body);
        const backendUser = response.body.user;
        const token = this.authService.getToken() || ''; // Use stored token
        const user: User = {
          id: backendUser.id,
          name: backendUser.name,
          email: backendUser.email,
          accessToken: token
        };
        return {user, token};
      } else {
        console.error('ApiService: Failed to fetch session info:', response.status, response.statusText);
        return null;
      }
    } catch (error) {
      this.handleApiError('fetching session info', error);
      return null;
    }
  }

  async getConversationsByUser(userId: number): Promise<Conversation[]> {
    const endpoint = `${this.baseUrl}/api/conversation/byuserid/${userId}`;
    console.log(`ApiService: Requesting conversations for user ID: ${userId}`);
    try {
      const response = await lastValueFrom(
        this.http.get<ConversationData[]>(endpoint, {headers: this.getHeaders(), observe: 'response'})
      );
      console.log('ApiService: GetConversationsByUser Response:', response);
      if (response.status === 200 && response.body) {
        return response.body.map(convData => new Conversation(
          convData.id,
          convData.userId,
          convData.name,
          convData.participants
        ));
      } else if (response.status === 204) {
        console.log('ApiService: No conversations found for user (204).');
        return [];
      } else {
        throw new Error(`Unexpected response: ${response.status}`);
      }
    } catch (error) {
      this.handleApiError(`getting conversations for user ${userId}`, error);
      if (error instanceof HttpErrorResponse && error.status === 204) {
        return [];
      }
      throw error;
    }
  }

  async getConversationMessages(conversationId: number, count: number, latestTimestamp: Date | null = null): Promise<Message[]> {
    const effectiveTimestamp = latestTimestamp || new Date();
    const timestampInSeconds = Math.floor(effectiveTimestamp.getTime() / 1000);
    const endpoint = `${this.baseUrl}/api/conversation/messages/${conversationId}/${timestampInSeconds}/${count}`;
    console.log(`ApiService: Requesting messages for conv ID: ${conversationId}, count: ${count}, before_time: ${timestampInSeconds}`);
    try {
      const response = await lastValueFrom(
        this.http.get<MessageData[]>(endpoint, {headers: this.getHeaders(), observe: 'response'})
      );
      console.log('ApiService: GetConversationMessages Response:', response);
      if (response.status === 200 && response.body) {
        return response.body.map(messageData => Message.fromApiResponse(messageData));
      } else if (response.status === 204 || (response.status === 200 && !response.body)) {
        console.log('ApiService: No messages found (204 or empty 200).');
        return [];
      } else {
        throw new Error(`Unexpected response: ${response.status}`);
      }
    } catch (error) {
      this.handleApiError(`getting messages for conversation ${conversationId}`, error);
      if (error instanceof HttpErrorResponse && error.status === 204) {
        return [];
      }
      throw error;
    }
  }

  async sendMessage(
    message: Message,
    currentConversation: Conversation
  ): Promise<{ confirmedMessage: Message, newConversation?: Conversation }> {
    const endpoint = `${this.baseUrl}/api/message/send`;

    const payload: any = {
      conversationId: message.conversationId,
      roleName: message.roleName,
      content: message.content,
      time: Math.floor((message.time || new Date()).getTime() / 1000),
    };

    if (message.conversationId === null) {
      payload.newConversationData = {
        userId: currentConversation.userId,
        name: currentConversation.name,
        participants: currentConversation.participants,
      };
    }

    console.log('ApiService: Sending message with payload:', JSON.stringify(payload, null, 2));

    try {
      const response = await lastValueFrom(
        this.http.post<SendMessageApiResponse>(endpoint, payload, {
          headers: this.getHeaders(),
          observe: 'response'
        })
      );
      console.log('ApiService: SendMessage API Response:', response);

      if (response.status === 201 && response.body) {
        const confirmedMessage = Message.fromApiResponse(response.body.message);
        let newConversation: Conversation | undefined = undefined;

        if (response.body.conversation) {
          const convData = response.body.conversation;
          newConversation = new Conversation(
            convData.id,
            convData.userId,
            convData.name,
            convData.participants
          );
          newConversation.hashsum = convData.hashsum;
          console.log('ApiService: New conversation created by backend:', newConversation);
        }
        return {confirmedMessage, newConversation};
      } else {
        throw new Error(`Unexpected response: ${response.status}`);
      }
    } catch (error) {
      this.handleApiError('sending message', error);
      throw error;
    }
  }

  async generateMessage(lastMessage: Message, participant: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/generate`;
    const payload = {
      conversationId: lastMessage.conversationId,
      roleName: participant,
      time: Math.floor(new Date().getTime() / 1000)
    };
    console.log(`ApiService: Generating message for participant ${participant} in conv ${lastMessage.conversationId}`);
    try {
      const response = await lastValueFrom(
        this.http.post<MessageData>(endpoint, payload, {headers: this.getHeaders(), observe: 'response'})
      );
      console.log('ApiService: GenerateMessage API Response:', response);
      if (response.status === 201 && response.body) {
        return Message.fromApiResponse(response.body);
      } else {
        throw new Error(`Unexpected response: ${response.status}`);
      }
    } catch (error) {
      this.handleApiError('generating message', error);
      throw error;
    }
  }

  async patchMessage(conversationId: number, messageId: number, content: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/patch`;
    const body = {id: messageId, conversationId: conversationId, content: content};
    console.log(`ApiService: Patching message ID ${messageId} in conv ${conversationId}`);
    try {
      const response = await lastValueFrom(
        this.http.patch<MessageData>(endpoint, body, {headers: this.getHeaders(), observe: 'response'})
      );
      console.log('ApiService: PatchMessage API Response:', response);
      if (response.status === 200 && response.body) {
        return Message.fromApiResponse(response.body);
      } else {
        throw new Error(`Unexpected response: ${response.status}`);
      }
    } catch (error) {
      this.handleApiError(`patching message ${messageId}`, error);
      throw error;
    }
  }

  async deleteMessage(conversationId: number, messageId: number): Promise<void> {
    const endpoint = `${this.baseUrl}/api/message/delete/${conversationId}/${messageId}`;
    console.log(`ApiService: Deleting message ID ${messageId} from conv ${conversationId}`);
    try {
      const response = await lastValueFrom(
        this.http.delete(endpoint, {headers: this.getHeaders(), observe: 'response'})
      );
      console.log('ApiService: DeleteMessage API Response:', response);
      if (response.status === 204) {
        return;
      } else {
        throw new Error(`Unexpected response: ${response.status}`);
      }
    } catch (error) {
      this.handleApiError(`deleting message ${messageId}`, error);
      if (error instanceof HttpErrorResponse && error.status === 404) {
        console.warn(`ApiService: Message ${messageId} not found on server for deletion (404).`);
        return;
      }
      throw error;
    }
  }

  private handleApiError(action: string, error: any): void {
    let errorMessage = `Error ${action}`;
    if (error instanceof HttpErrorResponse) {
      errorMessage += `: ${error.status} - ${error.message}. `;
      if (error.error && typeof error.error === 'object' && error.error.error) {
        errorMessage += `Backend Error: ${error.error.error}`;
      } else if (typeof error.error === 'string') {
        errorMessage += `Backend Error: ${error.error}`;
      }

      // Handle authentication errors
      if (error.status === 401) {
        console.error('Authentication error - redirecting to login');
        this.authService.logout().subscribe();
      }
    } else if (error instanceof Error) {
      errorMessage += `: ${error.message}`;
    } else {
      errorMessage += `: Unknown error occurred.`;
    }
    console.error(`ApiService: ${errorMessage}`, error);
  }
}
