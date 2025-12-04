import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { lastValueFrom } from 'rxjs';
import { Message } from '../data/objects/message';
import { environment } from '../environments/environment';
import { Conversation } from '../data/objects/conversation';
import { AppSettings } from '../models/settings.model';
import { FilePreview } from '../data/objects/file-preview';


@Injectable({
  providedIn: 'root'
})
export class ApiService {
  // Use the environment configuration to get
  private baseUrl: string = environment.apiUrl;
  public csrfToken: string | null = null;

  constructor(private http: HttpClient) {
    // Development only - handle self-signed certificates
    //if (!environment.production) {
    //  process.env['NODE_TLS_REJECT_UNAUTHORIZED'] = '0';
    //}
    // TODO: Either enable or remove this

    // Try to read CSRF token from cookie on initialization
    this.readCsrfTokenFromCookie();
  }

  // Read CSRF token from cookie
  private readCsrfTokenFromCookie(): void {
    // Simple cookie parser
    const cookies = document.cookie.split(';');
    for (const cookie of cookies) {
      const [name, value] = cookie.trim().split('=');
      if (name === 'csrf_token') {
        this.csrfToken = decodeURIComponent(value);
        console.log('CSRF token loaded from cookie:', this.csrfToken);
        return;
      }
    }
    console.warn('No CSRF token found in cookies');
  }

  // Headers setup method
  private getHeaders(): HttpHeaders {
    const headers: any = {
      'Content-Type': 'application/json',
    };

    // Try to read from cookie if not already set
    if (!this.csrfToken) {
      this.readCsrfTokenFromCookie();
    }

    // Add CSRF token if available
    if (this.csrfToken) {
      headers['X-CSRF-Token'] = this.csrfToken;
    } else {
      console.warn('No CSRF token available when building headers');
    }

    return new HttpHeaders(headers);
  }

  private getHttpOptions() {
    return {
      headers: this.getHeaders(),  // Headers
      // TODO: Do we still need this now that we have the auth.guard?
      withCredentials: true  // Cookies
    };
  }

  // Extract CSRF token from response headers
  public extractCsrfToken(response: any): void {
    console.log('Extracting CSRF token from response:', response);

    // First try to read from cookie (primary method now)
    this.readCsrfTokenFromCookie();

    // Also check headers for backward compatibility
    if (response && response.headers) {
      // Debug: Log all available headers
      console.log('Available headers:');
      response.headers.keys().forEach((key: string) => {
        console.log(`  ${key}: ${response.headers.get(key)}`);
      });

      // Try different case variations
      const token = response.headers.get('X-CSRF-Token') ||
        response.headers.get('x-csrf-token') ||
        response.headers.get('X-Csrf-Token');

      console.log('CSRF token from headers:', token);
      if (token && !this.csrfToken) {
        // Only use header token if cookie wasn't found
        this.csrfToken = token;
        console.log('CSRF token updated from headers:', this.csrfToken);
      }
    }

    if (!this.csrfToken) {
      console.warn('No CSRF token found in cookies or headers');
    }
  }

  async getSettings(): Promise<AppSettings> {
    const endpoint = `${this.baseUrl}/api/settings`;
    try {
      return await lastValueFrom(
        this.http.get<AppSettings>(endpoint, this.getHttpOptions())
      );
    } catch (error) {
      console.error('Error fetching settings:', error);
      throw error;
    }
  }

  async saveSettings(settings: AppSettings): Promise<void> {
    const endpoint = `${this.baseUrl}/api/settings`;
    try {
      await lastValueFrom(
        this.http.put<void>(endpoint, settings, this.getHttpOptions())
      );
    } catch (error) {
      console.error('Error saving settings:', error);
      throw error;
    }
  }

  async getConversations(): Promise<Conversation[]> {
    // Use the access token via session cookie instead of passing userId
    const endpoint = `${this.baseUrl}/api/conversations`;
    console.log('Requesting conversations for current user...');

    try {
      const response = await lastValueFrom(
        this.http.get<any[]>(endpoint, {
          ...this.getHttpOptions(),
          observe: 'response'
        })
      );

      console.log('Response:', response);

      // Extract CSRF token from response headers
      this.extractCsrfToken(response);

      if (response.status === 200 && response.body) {
        // Convert plain objects to Conversation instances using the static method
        return response.body.map(data => Conversation.fromApiResponse(data));
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

  // TODO: Fix this one!
  async getConversationMessages(
    conversationId: string | number,
    count: number,
    latestTimestamp: Date | null = null,
    afterTimestamp?: Date
  ): Promise<{ messages: Message[], hasMoreMessages?: boolean }> {
    // Use the current time if no timestamp is provided
    if (latestTimestamp === null) {
      latestTimestamp = new Date();
    }

    let endpoint = `${this.baseUrl}/api/conversation/messages/${conversationId}/${Math.floor(latestTimestamp.getTime() / 1000)}/${count}`;

    // Add after_timestamp query parameter for incremental sync
    if (afterTimestamp) {
      endpoint += `?after_timestamp=${Math.floor(afterTimestamp.getTime() / 1000)}`;
    }

    try {
      const response = await lastValueFrom(
        this.http.get<any[]>(endpoint, {
          ...this.getHttpOptions(),
          observe: 'response'
        })
      );

      if ((response.status === 200 || response.status === 206) && response.body) {
        // Convert all messages using the new factory method
        const messages = response.body.map(messageData => Message.fromApiResponse(messageData));

        // Check if server indicated more messages exist
        const hasMoreMessages = response.headers.get('X-Has-More-Messages') === 'true';

        return { messages, hasMoreMessages };
      } else if (response.status === 204 && !response.body) {
        return { messages: [], hasMoreMessages: false };
      } else {
        // Handle unexpected response statuses
        console.warn(`Unexpected response status: ${response.status}`);
        return { messages: [], hasMoreMessages: false };
      }
    } catch (error) {
      console.error('Error refreshing conversation:', error);
      throw error;
    }
  }

  async sendMessage(message: Message): Promise<number> {
    const endpoint = `${this.baseUrl}/api/message/send`;

    // Use the new toApiSend method which handles all message types
    const body = message.toApiSend();

    try {
      const response = await lastValueFrom(
        this.http.post<{ id: number }>(endpoint, body, {
          ...this.getHttpOptions(),
          observe: 'response'
        })
      );

      if (response.status === 201) {
        // Update the message ID with the server-assigned ID
        return response.body!.id;
      } else if (response.status === 400) {
        throw new Error('Bad Request: Please check the input data');
      } else if (response.status === 500) {
        throw new Error('Server Error: Please try again later');
      } else {
        throw new Error(`Unexpected response: ${response.status}`);
      }  // TODO: How do we want to handle errors?
    } catch (error) {
      console.error('Error sending message:', error);
      throw error;
    }
  }

  async generateMessage(lastMessage: Message, participant: string, settings: AppSettings): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/generate`;
    const body = { ...lastMessage.toApiGenerate(participant) };
    try {
      const response = await lastValueFrom(
        this.http.post<any>(endpoint, body, { ...this.getHttpOptions() })
      );

      // Use the new fromApiResponse method which handles all message types
      return Message.fromApiResponse(response);
    } catch (error) {
      console.error('Error generating message:', error);
      throw error;
    }
  }

  async sendAndGenerateMessage(
    message: Message,
    generateResponse: boolean = true
  ): Promise<{ userMessageId: number; aiMessage?: Message }> {
    const endpoint = `${this.baseUrl}/api/message/send-and-generate`;

    // Build request body combining message and generation settings
    const body: any = {
      ...message.toApiSend(),
      generateResponse: generateResponse,
      aiParticipant: 'Assistant'
    };
    try {
      const response = await lastValueFrom(
        this.http.post<any>(endpoint, body, { ...this.getHttpOptions() })
      );

      // Response contains both user message ID and optional AI message
      const result: { userMessageId: number; aiMessage?: Message } = {
        userMessageId: response.userMessage.id
      };

      if (response.aiMessage) {
        result.aiMessage = Message.fromApiResponse(response.aiMessage);
      }

      return result;
    } catch (error) {
      console.error('Error in sendAndGenerateMessage:', error);
      throw error;
    }
  }

  // Patch an existing message
  async patchMessage(conversationId: string | number, messageId: number, content: string, version: number): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/patch`;
    const body = {
      id: messageId,
      conversationId: conversationId,
      content: content,
      version: version
    };

    try {
      const response = await lastValueFrom(
        this.http.patch<any>(endpoint, body, { ...this.getHttpOptions() })
      );
      return Message.fromApiResponse({ id: messageId, conversationId, content, ...response });
    } catch (error) {
      console.error('Error patching message:', error);
      throw error;
    }
  }

  // Delete a message
  async deleteMessage(conversationId: string | number, messageId: number): Promise<void> {
    const endpoint = `${this.baseUrl}/api/message/delete/${conversationId}/${messageId}`;

    try {
      await lastValueFrom(
        this.http.delete(endpoint, { ...this.getHttpOptions() })
      );
    } catch (error) {
      console.error('Error deleting message:', error);
      throw error;
    }
  }

  // Rate a message (thumbs up or thumbs down)
  async rateMessage(messageId: number, conversationId: string, rating: number | null): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/rate`;
    const body = {
      id: messageId,
      conversationId: conversationId,
      rating: rating
    };

    try {
      const response = await lastValueFrom(
        this.http.post<any>(endpoint, body, { ...this.getHttpOptions() })
      );

      return Message.fromApiResponse(response);
    } catch (error) {
      console.error('Error rating message:', error);
      throw error;
    }
  }

  // Regenerate an AI message
  async regenerateMessage(messageId: number, conversationId: string): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/regenerate`;
    const body = {
      id: messageId,
      conversationId: conversationId
    };

    try {
      const response = await lastValueFrom(
        this.http.post<any>(endpoint, body, { ...this.getHttpOptions() })
      );

      return Message.fromApiResponse(response);
    } catch (error) {
      console.error('Error regenerating message:', error);
      throw error;
    }
  }

  // Method for file upload
  async uploadFiles(files: FilePreview[]): Promise<string[]> {
    const endpoint = `${this.baseUrl}/api/files/upload`;

    // Convert FilePreview to FormData and upload
    const formData = new FormData();
    files.forEach(fp => {
      formData.append('files', fp.file, fp.name);
    });

    try {
      // Upload files and return their server IDs
      // Get existing headers with CSRF token
      const baseHeaders = this.getHeaders();

      // For multipart/form-data, we need to let the browser set Content-Type with boundary
      // So we create new headers without Content-Type but keep other headers like CSRF
      let uploadHeaders = new HttpHeaders();
      baseHeaders.keys().forEach(key => {
        if (key.toLowerCase() !== 'content-type') {
          const value = baseHeaders.get(key);
          if (value) {
            uploadHeaders = uploadHeaders.set(key, value);
          }
        }
      });

      const response = await lastValueFrom(
        this.http.post<string[]>(endpoint, formData, {
          headers: uploadHeaders,
          withCredentials: true,
          reportProgress: true
        })
      );

      return response;
    } catch (error) {
      console.error('Error uploading files:', error);
      throw error;
    }
  }

  // Create a new conversation
  async createConversation(conversation: Conversation): Promise<Conversation> {
    const endpoint = `${this.baseUrl}/api/conversation/create`;
    const body = { name: conversation.name, participants: conversation.participants };
    try {
      const responseData = await lastValueFrom(
        this.http.post<any>(endpoint, body, this.getHttpOptions())
      );
      return Conversation.fromApiResponse(responseData);
    } catch (error) {
      console.error('Error creating conversation:', error);
      throw error;
    }
  }

  // Update conversation name
  async updateConversationName(id: string, name: string): Promise<Conversation> {
    const endpoint = `${this.baseUrl}/api/conversation/${id}`;
    const body = { name };
    try {
      const responseData = await lastValueFrom(
        this.http.patch<any>(endpoint, body, this.getHttpOptions())
      );
      return Conversation.fromApiResponse(responseData);
    } catch (error) {
      console.error('Error updating conversation:', error);
      throw error;
    }
  }

  // Delete conversation
  async deleteConversation(id: string): Promise<void> {
    const endpoint = `${this.baseUrl}/api/conversation/${id}`;
    try {
      await lastValueFrom(
        this.http.delete(endpoint, this.getHttpOptions())
      );
    } catch (error) {
      console.error('Error deleting conversation:', error);
      throw error;
    }
  }

  // Fetch a file by its ID
  async getFile(fileId: string): Promise<Blob> {
    const endpoint = `${this.baseUrl}/api/files/${fileId}`;
    try {
      return await lastValueFrom(
        this.http.get(endpoint, {
          ...this.getHttpOptions(),
          responseType: 'blob'
        })
      );
    } catch (error) {
      console.error('Error fetching file:', error);
      throw error;
    }
  }

}
