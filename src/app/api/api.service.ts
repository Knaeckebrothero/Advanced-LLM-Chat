import {Injectable} from '@angular/core';
import {HttpClient, HttpErrorResponse, HttpHeaders} from '@angular/common/http';
import {lastValueFrom} from 'rxjs';
import {Message, MessageData} from '../data/objects/message'; // Assuming MessageData for constructor
import {environment} from '../environments/environment';
import {Conversation} from '../data/objects/conversation'; // Import ConversationDTO
import {User} from '../data/objects/user';

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
  message: MessageData; // Assuming MessageData is what Message.fromApiResponse expects
  conversation?: ConversationData; // Optional: for newly created conversations
}

// Interface for raw conversation data from backend (matching ConversationResponse in Python)
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
  ) {
  }

  private getHeaders(accessToken?: string): HttpHeaders {
    let headers = new HttpHeaders({
      'Content-Type': 'application/json',
    });
    if (accessToken) {
      headers = headers.set('Authorization', `Bearer ${accessToken}`);
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
        const token = response.body.token;
        const user: User = { // Assuming User interface matches this structure
          id: backendUser.id,
          name: backendUser.name,
          email: backendUser.email,
          accessToken: token // Storing token with the user object
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

  async getConversationsByUser(userId: number, accessToken: string): Promise<Conversation[]> {
    const endpoint = `${this.baseUrl}/api/conversation/byuserid/${userId}`;
    console.log(`ApiService: Requesting conversations for user ID: ${userId}`);
    try {
      const response = await lastValueFrom(
        this.http.get<ConversationData[]>(endpoint, {headers: this.getHeaders(accessToken), observe: 'response'})
      );
      console.log('ApiService: GetConversationsByUser Response:', response);
      if (response.status === 200 && response.body) {
        return response.body.map(convData => new Conversation(
          convData.id,
          convData.userId,
          convData.name,
          convData.participants
          // convData.hashsum will be set if needed, or calculated client-side
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
        return []; // Still return empty array on 204 after logging
      }
      throw error; // Re-throw other errors
    }
  }

  async getConversationMessages(conversationId: number, count: number, accessToken: string, latestTimestamp: Date | null = null): Promise<Message[]> {
    const effectiveTimestamp = latestTimestamp || new Date(); // Use current time if null
    const timestampInSeconds = Math.floor(effectiveTimestamp.getTime() / 1000);
    const endpoint = `${this.baseUrl}/api/conversation/messages/${conversationId}/${timestampInSeconds}/${count}`;
    console.log(`ApiService: Requesting messages for conv ID: ${conversationId}, count: ${count}, before_time: ${timestampInSeconds}`);
    try {
      const response = await lastValueFrom(
        this.http.get<MessageData[]>(endpoint, {headers: this.getHeaders(accessToken), observe: 'response'})
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

  /**
   * Sends a message. If the message's conversationId is null, it signals the backend
   * to create a new conversation using details from the provided currentConversation object.
   * @param message The message to send.
   * @param currentConversation The current conversation object, used if creating a new one.
   * @param accessToken The user's access token.
   * @returns A promise that resolves to an object containing the confirmed message and,
   * if a new conversation was created, the new conversation object.
   */
  async sendMessage(
    message: Message,
    currentConversation: Conversation, // Pass the full current conversation object
    accessToken: string
  ): Promise<{ confirmedMessage: Message, newConversation?: Conversation }> {
    const endpoint = `${this.baseUrl}/api/message/send`;

    // Prepare payload for the backend's ApiMessageSend model
    const payload: any = { // Using 'any' for flexibility in constructing the payload
      conversationId: message.conversationId, // This can be null
      roleName: message.roleName,
      content: message.content,
      time: Math.floor((message.time || new Date()).getTime() / 1000), // Ensure time is in seconds
    };

    if (message.conversationId === null) {
      // If conversationId is null, backend expects newConversationData
      payload.newConversationData = {
        userId: currentConversation.userId, // Get userId from the current Conversation object
        name: currentConversation.name,
        participants: currentConversation.participants,
      };
    }

    console.log('ApiService: Sending message with payload:', JSON.stringify(payload, null, 2));

    try {
      const response = await lastValueFrom(
        this.http.post<SendMessageApiResponse>(endpoint, payload, {
          headers: this.getHeaders(accessToken),
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
          newConversation.hashsum = convData.hashsum; // Set hashsum if provided
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

  async generateMessage(lastMessage: Message, participant: string, accessToken: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/generate`;
    // Backend's ApiMessageGenerate expects conversationId, roleName (of AI), time (optional for backend)
    const payload = {
      conversationId: lastMessage.conversationId,
      roleName: participant, // The AI participant's name/role
      time: Math.floor(new Date().getTime() / 1000) // Current time for generation request
    };
    console.log(`ApiService: Generating message for participant ${participant} in conv ${lastMessage.conversationId}`);
    try {
      const response = await lastValueFrom(
        this.http.post<MessageData>(endpoint, payload, {headers: this.getHeaders(accessToken), observe: 'response'})
      );
      console.log('ApiService: GenerateMessage API Response:', response);
      if (response.status === 201 && response.body) {
        // Assuming backend returns full MessageData, use fromApiResponse
        return Message.fromApiResponse(response.body);
      } else {
        throw new Error(`Unexpected response: ${response.status}`);
      }
    } catch (error) {
      this.handleApiError('generating message', error);
      throw error;
    }
  }

  async patchMessage(conversationId: number, messageId: number, content: string, accessToken: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/patch`;
    const body = {id: messageId, conversationId: conversationId, content: content};
    console.log(`ApiService: Patching message ID ${messageId} in conv ${conversationId}`);
    try {
      const response = await lastValueFrom(
        this.http.patch<MessageData>(endpoint, body, {headers: this.getHeaders(accessToken), observe: 'response'})
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

  async deleteMessage(conversationId: number, messageId: number, accessToken: string): Promise<void> {
    const endpoint = `${this.baseUrl}/api/message/delete/${conversationId}/${messageId}`;
    console.log(`ApiService: Deleting message ID ${messageId} from conv ${conversationId}`);
    try {
      const response = await lastValueFrom(
        this.http.delete(endpoint, {headers: this.getHeaders(accessToken), observe: 'response'})
      );
      console.log('ApiService: DeleteMessage API Response:', response);
      if (response.status === 204) {
        return; // Success
      } else {
        // Even for non-204, if it's an error status, it will be caught by catch block
        throw new Error(`Unexpected response: ${response.status}`);
      }
    } catch (error) {
      this.handleApiError(`deleting message ${messageId}`, error);
      // Do not re-throw if it's a 404, as the message might already be deleted.
      // The service calling this can decide how to handle it.
      // For now, we let HttpErrorResponse be thrown for other errors.
      if (error instanceof HttpErrorResponse && error.status === 404) {
        console.warn(`ApiService: Message ${messageId} not found on server for deletion (404).`);
        return; // Treat as success from client's perspective if it's already gone.
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
    } else if (error instanceof Error) {
      errorMessage += `: ${error.message}`;
    } else {
      errorMessage += `: Unknown error occurred.`;
    }
    console.error(`ApiService: ${errorMessage}`, error);
  }
}
