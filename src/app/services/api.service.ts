import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { lastValueFrom } from 'rxjs';
import { Message } from '../data/objects/message';
import { environment } from '../environments/environment';
import { Conversation } from '../data/objects/conversation';
import { AppSettings } from '../models/settings.model';
import { FilePreview } from '../data/objects/file-preview';
import {
  ICatalogFile,
  IConversationSelection,
  IFetchModelsResponse,
  IImportResult,
  IModelCreate,
  IModelOut,
  IModelTestResult,
  IModelUpdate,
  IPersonaCreate,
  IPersonaOut,
  IPersonaUpdate,
  IProviderOut,
  IPublicModel,
  IPublicPersona,
  IToolStatus,
} from '../data/models/catalog.model';
import { IApiConversationCreate, IApiConversationUpdate, IConversationFile } from '../data/models/api.model';

/**
 * Response from file upload endpoint
 */
export interface UploadedFileResponse {
  fileId: string;
  transcript?: string;  // Present only for audio files
}


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

  /** Store a message on the server. Returns the id and time (seconds) the server gave it. */
  async sendMessage(message: Message): Promise<{ id: number, time: number }> {
    const endpoint = `${this.baseUrl}/api/message/send`;

    // Use the new toApiSend method which handles all message types
    const body = message.toApiSend();

    try {
      const response = await lastValueFrom(
        this.http.post<{ id: number, time: number }>(endpoint, body, {
          ...this.getHttpOptions(),
          observe: 'response'
        })
      );

      if (response.status === 201) {
        return response.body!;
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
  ): Promise<{ userMessageId: number; userMessageTime: number; aiMessage?: Message }> {
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
      const result: { userMessageId: number; userMessageTime: number; aiMessage?: Message } = {
        userMessageId: response.userMessage.id,
        userMessageTime: response.userMessage.time
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

  // Patch an existing message (its text; an agent message keeps its steps), with deleteFollowing
  // also deleting the messages after it, so it can be answered again
  async patchMessage(
    conversationId: string | number, messageId: number, content: string, version: number, deleteFollowing = false
  ): Promise<Message> {
    const endpoint = `${this.baseUrl}/api/message/patch`;
    const body = {
      id: messageId,
      conversationId: conversationId,
      content: content,
      version: version,
      ...(deleteFollowing && { deleteFollowing })
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

  /** Insert a text message of the user or the assistant before or after a message; nothing answers it. */
  async insertMessage(
    conversationId: string, messageId: number, position: 'before' | 'after', roleName: 'user' | 'Assistant', content: string
  ): Promise<Message> {
    const response = await lastValueFrom(
      this.http.post<any>(
        `${this.baseUrl}/api/message/insert`,
        { conversationId, messageId, position, roleName, content },
        this.getHttpOptions()
      )
    );
    return Message.fromApiResponse(response);
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
  async uploadFiles(files: FilePreview[]): Promise<UploadedFileResponse[]> {
    const endpoint = `${this.baseUrl}/api/files/upload`;

    // Convert FilePreview to FormData and upload
    const formData = new FormData();
    files.forEach(fp => {
      if (fp.file) {
        formData.append('files', fp.file, fp.name);
      }
    });

    try {
      // Upload files and return their server IDs (and transcripts for audio)
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
        this.http.post<UploadedFileResponse[]>(endpoint, formData, {
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

  // Create a new conversation (with its model and persona, if picked)
  async createConversation(conversation: Conversation): Promise<Conversation> {
    const endpoint = `${this.baseUrl}/api/conversation/create`;
    const body: IApiConversationCreate = { name: conversation.name, participants: conversation.participants };
    if (conversation.modelId !== undefined) body.modelId = conversation.modelId;
    if (conversation.personaId !== undefined) body.personaId = conversation.personaId;
    if (conversation.personaValues !== undefined) body.personaValues = conversation.personaValues;
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

  // Generate AI title for a conversation (async, fire-and-forget friendly)
  async generateConversationTitle(conversationId: string, firstMessage: string): Promise<Conversation> {
    const endpoint = `${this.baseUrl}/api/conversation/${conversationId}/generate-title`;
    const body = { firstMessage };
    try {
      const responseData = await lastValueFrom(
        this.http.post<any>(endpoint, body, this.getHttpOptions())
      );
      return Conversation.fromApiResponse(responseData);
    } catch (error) {
      console.error('Error generating conversation title:', error);
      throw error;
    }
  }

  // Update conversation name. The current selection is sent along when known, so a backend
  // that treats missing fields as null doesn't reset the model and persona.
  async updateConversationName(id: string, name: string, selection?: IConversationSelection): Promise<Conversation> {
    const endpoint = `${this.baseUrl}/api/conversation/${id}`;
    const body: IApiConversationUpdate = { name, ...selection };
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

  // Update a conversation's model and persona. The name is sent too, since older
  // backends require it in the PATCH body.
  async updateConversationSelection(
    id: string,
    name: string,
    selection: IConversationSelection
  ): Promise<Conversation> {
    const endpoint = `${this.baseUrl}/api/conversation/${id}`;
    const body: IApiConversationUpdate = {
      name,
      modelId: selection.modelId,
      personaId: selection.personaId,
      personaValues: selection.personaValues
    };
    try {
      const responseData = await lastValueFrom(
        this.http.patch<any>(endpoint, body, this.getHttpOptions())
      );
      return Conversation.fromApiResponse(responseData);
    } catch (error) {
      console.error('Error updating conversation selection:', error);
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

  /** A conversation with all its messages, as a conversation file. */
  async exportConversation(id: string): Promise<IConversationFile> {
    return await lastValueFrom(
      this.http.get<IConversationFile>(`${this.baseUrl}/api/conversation/${id}/export`, this.getHttpOptions())
    );
  }

  /** Creates a new conversation from a conversation file (not for guests). */
  async importConversation(file: IConversationFile): Promise<Conversation> {
    const responseData = await lastValueFrom(
      this.http.post<any>(`${this.baseUrl}/api/conversation/import`, file, this.getHttpOptions())
    );
    return Conversation.fromApiResponse(responseData);
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

  // Fetch extracted text content for a document
  async getFileText(fileId: string): Promise<string> {
    const endpoint = `${this.baseUrl}/api/files/${fileId}/text`;
    try {
      return await lastValueFrom(
        this.http.get(endpoint, {
          ...this.getHttpOptions(),
          responseType: 'text'
        })
      );
    } catch (error) {
      console.error('Error fetching file text:', error);
      throw error;
    }
  }

  /**
   * Generate text-to-speech audio for a message.
   * Returns cached audio if available, otherwise generates new.
   * @param conversationId The conversation ID
   * @param messageId The message ID
   * @param language Language code for voice selection ('en' or 'de')
   * @returns Audio blob (MP3 format)
   */
  async generateTTS(conversationId: string, messageId: number, language: string): Promise<Blob> {
    const endpoint = `${this.baseUrl}/api/message/tts/${conversationId}/${messageId}?language=${language}`;

    try {
      return await lastValueFrom(
        this.http.post(endpoint, {}, {
          ...this.getHttpOptions(),
          responseType: 'blob'
        })
      );
    } catch (error) {
      console.error('Error generating TTS:', error);
      throw error;
    }
  }


  // =========================================================================
  // Model catalog: public endpoints (guests get a filtered list)
  // =========================================================================

  /** Enabled models for the picker. Empty when the catalog is empty (the environment model answers). */
  async getModels(): Promise<IPublicModel[]> {
    return await lastValueFrom(
      this.http.get<IPublicModel[]>(`${this.baseUrl}/api/models`, this.getHttpOptions())
    ) || [];
  }

  async getPersonas(): Promise<IPublicPersona[]> {
    return await lastValueFrom(
      this.http.get<IPublicPersona[]>(`${this.baseUrl}/api/personas`, this.getHttpOptions())
    ) || [];
  }

  // =========================================================================
  // Model catalog: admin endpoints (403 for everyone else)
  // =========================================================================

  /** Providers are configured on the server (catalog file and environment variables) and read-only here. */
  async getAdminProviders(): Promise<IProviderOut[]> {
    return await lastValueFrom(
      this.http.get<IProviderOut[]>(`${this.baseUrl}/api/admin/providers`, this.getHttpOptions())
    );
  }

  /** The provider's own model list (GET /models), with the ones already in the catalog marked. */
  async fetchProviderModels(id: number): Promise<IFetchModelsResponse> {
    return await lastValueFrom(
      this.http.post<IFetchModelsResponse>(
        `${this.baseUrl}/api/admin/providers/${id}/fetch-models`, {}, this.getHttpOptions()
      )
    );
  }

  async getAdminModels(): Promise<IModelOut[]> {
    return await lastValueFrom(
      this.http.get<IModelOut[]>(`${this.baseUrl}/api/admin/models`, this.getHttpOptions())
    );
  }

  async createModel(model: IModelCreate): Promise<IModelOut> {
    return await lastValueFrom(
      this.http.post<IModelOut>(`${this.baseUrl}/api/admin/models`, model, this.getHttpOptions())
    );
  }

  async updateModel(id: number, update: IModelUpdate): Promise<IModelOut> {
    return await lastValueFrom(
      this.http.put<IModelOut>(`${this.baseUrl}/api/admin/models/${id}`, update, this.getHttpOptions())
    );
  }

  async deleteModel(id: number): Promise<void> {
    await lastValueFrom(
      this.http.delete(`${this.baseUrl}/api/admin/models/${id}`, this.getHttpOptions())
    );
  }

  /** Sends a short prompt to the model and reports whether it answered. */
  async testModel(id: number): Promise<IModelTestResult> {
    return await lastValueFrom(
      this.http.post<IModelTestResult>(`${this.baseUrl}/api/admin/models/${id}/test`, {}, this.getHttpOptions())
    );
  }

  async getAdminPersonas(): Promise<IPersonaOut[]> {
    return await lastValueFrom(
      this.http.get<IPersonaOut[]>(`${this.baseUrl}/api/admin/personas`, this.getHttpOptions())
    );
  }

  async createPersona(persona: IPersonaCreate): Promise<IPersonaOut> {
    return await lastValueFrom(
      this.http.post<IPersonaOut>(`${this.baseUrl}/api/admin/personas`, persona, this.getHttpOptions())
    );
  }

  async updatePersona(id: number, update: IPersonaUpdate): Promise<IPersonaOut> {
    return await lastValueFrom(
      this.http.put<IPersonaOut>(`${this.baseUrl}/api/admin/personas/${id}`, update, this.getHttpOptions())
    );
  }

  async deletePersona(id: number): Promise<void> {
    await lastValueFrom(
      this.http.delete(`${this.baseUrl}/api/admin/personas/${id}`, this.getHttpOptions())
    );
  }

  /** The tool groups agents can use, and whether the server offers them. */
  async getAdminTools(): Promise<IToolStatus[]> {
    return await lastValueFrom(
      this.http.get<IToolStatus[]>(`${this.baseUrl}/api/admin/tools`, this.getHttpOptions())
    );
  }

  /** The catalog file. */
  async exportCatalog(): Promise<ICatalogFile> {
    return await lastValueFrom(
      this.http.get<ICatalogFile>(`${this.baseUrl}/api/admin/catalog/export`, this.getHttpOptions())
    );
  }

  /** Upserts models and personas by name; never deletes. Provider entries are skipped. */
  async importCatalog(file: ICatalogFile): Promise<IImportResult> {
    return await lastValueFrom(
      this.http.post<IImportResult>(`${this.baseUrl}/api/admin/catalog/import`, file, this.getHttpOptions())
    );
  }

}
