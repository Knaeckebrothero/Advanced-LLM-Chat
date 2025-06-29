import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { lastValueFrom } from 'rxjs';
import { Message } from '../data/objects/message';
import { environment } from '../environments/environment';
import { Conversation } from '../data/objects/conversation';
import { Settings } from '../settings/settings.service';
import { FilePreview } from '../data/objects/file-preview';


@Injectable({
  providedIn: 'root'
})
export class ApiService {
  // Use the environment configuration to get
  private baseUrl: string = environment.apiUrl;

  constructor(private http: HttpClient) {
    // Development only - handle self-signed certificates
    //if (!environment.production) {
    //  process.env['NODE_TLS_REJECT_UNAUTHORIZED'] = '0';
    //}
    // TODO: Either enable or remove this
  }

  // Headers setup method
  private getHeaders(): HttpHeaders {
    return new HttpHeaders({
      'Content-Type': 'application/json',
      // 'Authorization': `Bearer ${this.user.accessToken}`
      // TODO: Implement a access token
    });
  }

  private getHttpOptions() {
    return {
      headers: this.getHeaders(),  // Headers
      // TODO: Do we still need this now that we have the auth.guard?
      withCredentials: true  // Cookies
    };
  }

  async getLLMs(): Promise<string[]> {
    const endpoint = `${this.baseUrl}/api/llms`;
    try {
      const response = await lastValueFrom(
        this.http.get<string[]>(endpoint, this.getHttpOptions())
      );
      return response;
    } catch (error) {
      console.error('Error requesting LLMs:', error);
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

  async getConversationMessages(conversationId: number, count: number, latestTimestamp: Date | null = null): Promise<Message[]> {
    // Use the current time if no timestamp is provided
    if (latestTimestamp === null) {
      latestTimestamp = new Date();
    }
    const endpoint = `${this.baseUrl}/api/conversation/messages/${conversationId}/${Math.floor(latestTimestamp.getTime() / 1000)}/${count}`;

    try {
      const response = await lastValueFrom(
        this.http.get<any[]>(endpoint, {
          headers: this.getHeaders(),
          observe: 'response'
        })
      );

      if (response.status === 200 && response.body) {
        // Convert all messages using map for efficiency
        return response.body.map(messageData => Message.fromApiResponse(messageData));
      } else if (response.status === 204 && !response.body) {
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
        this.http.post<{ id: number }>(endpoint, body, {
          ...this.getHttpOptions(),
          observe: 'response' }
        )
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

  async generateMessage(lastMessage: Message, participant: string, settings: Settings): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/generate`;
    const body = {
      ...lastMessage.toApiGenerate(participant),
      temperature: settings.temperature,
      top_p: settings.top_p,
      systemPrompt: settings.systemPrompt
    };

    try {
      const response = await lastValueFrom(
        this.http.post<any>(endpoint, body, { ...this.getHttpOptions() })
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
        this.http.patch<Message>(endpoint, body, { ...this.getHttpOptions() })
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
        this.http.delete(endpoint, { ...this.getHttpOptions() })
      );
    } catch (error) {
      console.error('Error deleting message:', error);
      throw error;
    }
  }

  // TODO: Implement get all conversations
  async getAllConversations(userId: number): Promise<Conversation[]> {
    const endpoint = `${this.baseUrl}/api/conversations/user/${userId}`;
    // ... implement API call
    return [];
  }

  // Method for file upload
  async uploadFiles(files: FilePreview[]): Promise<string[]> {
    // Convert FilePreview to FormData and upload
    const formData = new FormData();
    files.forEach(fp => {
      formData.append('files', fp.file);
    });

    // TODO: Implement upload logic
    // For now, return an empty array as a placeholder
    // In a real implementation, this would call an API endpoint and return file URLs
    const endpoint = `${this.baseUrl}/api/files/upload`;

    try {
      // This is a placeholder. In a real implementation, you would:
      // const response = await lastValueFrom(
      //   this.http.post<string[]>(endpoint, formData, { ...this.getHttpOptions() })
      // );
      // return response;

      console.log('File upload requested (not yet implemented)');
      return [];
    } catch (error) {
      console.error('Error uploading files:', error);
      throw error;
    }
  }

  // TODO: Implement create conversation
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

  // TODO: Implement update conversation
  async updateConversation(conversation: Conversation): Promise<void> {
    const endpoint = `${this.baseUrl}/api/conversation/update`;
    // ... implement API call
  }

  // TODO: Implement delete conversation
  async deleteConversation(conversationId: number): Promise<void> {
    const endpoint = `${this.baseUrl}/api/conversation/delete/${conversationId}`;
    // ... implement API call
  }
}
