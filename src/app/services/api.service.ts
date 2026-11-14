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
  ISkillCreate,
  ISkillImportResult,
  ISkillOut,
  ISkillUpdate,
  IToolStatus,
} from '../data/models/catalog.model';
import { IApiConversationCreate, IApiConversationUpdate, IConversationFile } from '../data/models/api.model';
import { IContextSize, ISystemPrompt, IConversationSummary } from '../data/models/conversation.model';
import { FilePreviewSize, IAllFiles, IChatFile } from '../data/models/file.model';
import {
  IKBFile,
  IKBMemory,
  IKBNote,
  IKBNoteList,
  IKBNoteUpdate,
  IKBNoteWrite,
  IKBReviewResult,
  IKBRevision,
  IKBSearchHit,
  IKBVault,
  NoteStatus
} from '../data/models/knowledge-base.model';
import {
  IMcpConfig,
  IMcpConnectResult,
  McpAutoAcceptScope,
  McpElicitationAction,
  IMcpServerCreate,
  IMcpServerList,
  IMcpServerOut,
  IMcpServerUpdate,
  IMcpTestResult
} from '../data/models/mcp.model';

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

  /** Insert a text message of the user, the assistant or the system before or after a message; nothing answers it. */
  async insertMessage(
    conversationId: string, messageId: number, position: 'before' | 'after', roleName: 'user' | 'Assistant' | 'system',
    content: string
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

  // Hide a conversation or unhide it
  async updateConversationHidden(id: string, name: string, hidden: boolean): Promise<Conversation> {
    const endpoint = `${this.baseUrl}/api/conversation/${id}`;
    const body: IApiConversationUpdate = { name, hidden };
    const responseData = await lastValueFrom(this.http.patch<any>(endpoint, body, this.getHttpOptions()));
    return Conversation.fromApiResponse(responseData);
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

  /** The summary the model gets instead of the conversation's oldest messages, null if it has none. */
  async getConversationSummary(id: string): Promise<IConversationSummary | null> {
    return await lastValueFrom(
      this.http.get<IConversationSummary | null>(`${this.baseUrl}/api/conversation/${id}/summary`, this.getHttpOptions())
    );
  }

  /**
   * Folds all messages of the conversation so far into its summary, now (the model writes it, which
   * takes a while). 409: no messages after the summary, 422: too short to summarize, 502: the model failed.
   */
  async summarizeConversation(conversationId: string): Promise<IConversationSummary> {
    return await lastValueFrom(
      this.http.post<IConversationSummary>(`${this.baseUrl}/api/message/summarize`, { conversationId }, this.getHttpOptions())
    );
  }

  /** About how many input tokens the next answer sends, for the conversation's model or modelId. */
  async getContextSize(conversationId: string, modelId?: number | null): Promise<IContextSize> {
    return await lastValueFrom(
      this.http.post<IContextSize>(
        `${this.baseUrl}/api/message/context-size`, { conversationId, modelId: modelId ?? null }, this.getHttpOptions())
    );
  }

  /** The system prompt the next answer gets, as its model gets it, for the conversation's model or modelId. */
  async getSystemPrompt(conversationId: string, modelId?: number | null): Promise<ISystemPrompt> {
    const params: Record<string, string> = { conversationId };
    if (modelId !== null && modelId !== undefined) params['modelId'] = String(modelId);
    return await lastValueFrom(
      this.http.get<ISystemPrompt>(`${this.baseUrl}/api/message/system-prompt`, { ...this.getHttpOptions(), params })
    );
  }

  /**
   * Sets a conversation's own system prompt, which its answers then get as it is: '' sends none,
   * null goes back to the one built from the conversation's agent. Returns what the next answer gets.
   */
  async setSystemPrompt(conversationId: string, content: string | null, modelId?: number | null): Promise<ISystemPrompt> {
    return await lastValueFrom(
      this.http.put<ISystemPrompt>(
        `${this.baseUrl}/api/message/system-prompt`, { conversationId, content, modelId: modelId ?? null }, this.getHttpOptions())
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

  /** The files of a conversation, oldest first: its messages' attachments and what tools created in it. */
  async getConversationFiles(conversationId: string): Promise<IChatFile[]> {
    return await lastValueFrom(
      this.http.get<IChatFile[]>(`${this.baseUrl}/api/files`, {
        ...this.getHttpOptions(),
        params: { conversationId }
      })
    );
  }

  /**
   * The files of all the user's conversations, a page at a time: `limit` files after `offset`,
   * of one source ("upload", "tool") or of both.
   */
  async getAllFiles(offset: number, limit: number, source?: 'upload' | 'tool'): Promise<IAllFiles> {
    return await lastValueFrom(
      this.http.get<IAllFiles>(`${this.baseUrl}/api/files/all`, {
        ...this.getHttpOptions(),
        params: { offset, limit, ...(source ? { source } : {}) }
      })
    );
  }

  /** A preview of an image file or a PDF's first page (WebP, see FilePreviewSize); 404 for any other file. */
  async getFileThumbnail(fileId: string, size: FilePreviewSize): Promise<Blob> {
    return await lastValueFrom(
      this.http.get(`${this.baseUrl}/api/files/${encodeURIComponent(fileId)}/thumbnail`, {
        ...this.getHttpOptions(),
        params: { size },
        responseType: 'blob'
      })
    );
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

  // Skills of the agents (docs/skills.md)

  async getAdminSkills(): Promise<ISkillOut[]> {
    return await lastValueFrom(this.http.get<ISkillOut[]>(`${this.baseUrl}/api/admin/skills`, this.getHttpOptions()));
  }

  async createSkill(skill: ISkillCreate): Promise<ISkillOut> {
    return await lastValueFrom(
      this.http.post<ISkillOut>(`${this.baseUrl}/api/admin/skills`, skill, this.getHttpOptions())
    );
  }

  /** A new name is also changed in the agents that have the skill. */
  async updateSkill(id: number, update: ISkillUpdate): Promise<ISkillOut> {
    return await lastValueFrom(
      this.http.put<ISkillOut>(`${this.baseUrl}/api/admin/skills/${id}`, update, this.getHttpOptions())
    );
  }

  /** Also takes the skill off the agents that have it. */
  async deleteSkill(id: number): Promise<void> {
    await lastValueFrom(this.http.delete(`${this.baseUrl}/api/admin/skills/${id}`, this.getHttpOptions()));
  }

  /** One SKILL.md file; an existing name is a 409 unless replace is set. */
  async importSkill(text: string, replace: boolean): Promise<ISkillImportResult> {
    return await lastValueFrom(
      this.http.post<ISkillImportResult>(`${this.baseUrl}/api/admin/skills/import`, { text, replace },
                                         this.getHttpOptions())
    );
  }

  /** The skill as a SKILL.md file. */
  async exportSkill(id: number): Promise<string> {
    return await lastValueFrom(
      this.http.get(`${this.baseUrl}/api/admin/skills/${id}/export`, { ...this.getHttpOptions(), responseType: 'text' })
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

  // MCP servers (docs/mcp.md): signed-in users (guests get 403 everywhere except the config)

  /** What the server's configuration allows (MCP on, users' own servers, stdio, encryption). */
  async getMcpConfig(): Promise<IMcpConfig> {
    return await lastValueFrom(this.http.get<IMcpConfig>(`${this.baseUrl}/api/mcp/config`, this.getHttpOptions()));
  }

  /** The user's own servers, and the agents' servers with OAuth sign-in. */
  async getMcpServers(): Promise<IMcpServerList> {
    return await lastValueFrom(this.http.get<IMcpServerList>(`${this.baseUrl}/api/mcp/servers`, this.getHttpOptions()));
  }

  async createMcpServer(server: IMcpServerCreate): Promise<IMcpServerOut> {
    return await lastValueFrom(
      this.http.post<IMcpServerOut>(`${this.baseUrl}/api/mcp/servers`, server, this.getHttpOptions())
    );
  }

  async updateMcpServer(id: number, update: IMcpServerUpdate): Promise<IMcpServerOut> {
    return await lastValueFrom(
      this.http.put<IMcpServerOut>(`${this.baseUrl}/api/mcp/servers/${id}`, update, this.getHttpOptions())
    );
  }

  async deleteMcpServer(id: number): Promise<void> {
    await lastValueFrom(this.http.delete(`${this.baseUrl}/api/mcp/servers/${id}`, this.getHttpOptions()));
  }

  /** Connects as the current user and lists the tools (own servers, shared OAuth servers, any admin server for admins). */
  async testMcpServer(id: number): Promise<IMcpTestResult> {
    return await lastValueFrom(
      this.http.post<IMcpTestResult>(`${this.baseUrl}/api/mcp/servers/${id}/test`, {}, this.getHttpOptions())
    );
  }

  /** Starts the OAuth sign-in; the browser then goes to the authorization URL. */
  async connectMcpServer(id: number): Promise<IMcpConnectResult> {
    return await lastValueFrom(
      this.http.post<IMcpConnectResult>(`${this.baseUrl}/api/mcp/servers/${id}/connect`, {}, this.getHttpOptions())
    );
  }

  /** Signs out of an OAuth server (deletes the user's tokens). */
  async disconnectMcpServer(id: number): Promise<void> {
    await lastValueFrom(this.http.delete(`${this.baseUrl}/api/mcp/servers/${id}/connection`, this.getHttpOptions()));
  }

  /**
   * Answers a server's question to the user (elicitation) while its tool runs: the form's values
   * with accept in form mode; `remember` with accept of a plain confirmation accepts the server's
   * confirmations without asking from now on. 404 when the question is no longer open, 400 for
   * values that don't fit.
   */
  async answerMcpElicitation(id: string, action: McpElicitationAction, content?: Record<string, unknown>,
                             remember?: McpAutoAcceptScope | null): Promise<void> {
    await lastValueFrom(this.http.post(`${this.baseUrl}/api/mcp/elicitations/${encodeURIComponent(id)}`,
      { action, content: content ?? null, remember: remember ?? null }, this.getHttpOptions()));
  }

  /** Accept a server's confirmations without asking in every conversation, or stop (own and agents' servers). */
  async setMcpAutoAccept(id: number, enabled: boolean): Promise<void> {
    await lastValueFrom(this.http.put(`${this.baseUrl}/api/mcp/servers/${id}/auto-accept`, { enabled },
      this.getHttpOptions()));
  }

  // MCP servers of the agents: admin endpoints (403 for everyone else)

  async getAdminMcpServers(): Promise<IMcpServerOut[]> {
    return await lastValueFrom(
      this.http.get<IMcpServerOut[]>(`${this.baseUrl}/api/admin/mcp-servers`, this.getHttpOptions())
    );
  }

  async createAdminMcpServer(server: IMcpServerCreate): Promise<IMcpServerOut> {
    return await lastValueFrom(
      this.http.post<IMcpServerOut>(`${this.baseUrl}/api/admin/mcp-servers`, server, this.getHttpOptions())
    );
  }

  async updateAdminMcpServer(id: number, update: IMcpServerUpdate): Promise<IMcpServerOut> {
    return await lastValueFrom(
      this.http.put<IMcpServerOut>(`${this.baseUrl}/api/admin/mcp-servers/${id}`, update, this.getHttpOptions())
    );
  }

  async deleteAdminMcpServer(id: number): Promise<void> {
    await lastValueFrom(this.http.delete(`${this.baseUrl}/api/admin/mcp-servers/${id}`, this.getHttpOptions()));
  }

  // Knowledge base (signed-in users; backend/api/knowledge_base.py)

  private kbNoteUrl(slug: string): string {
    return `${this.baseUrl}/api/kb/notes/${encodeURIComponent(slug)}`;
  }

  /** The request options of a knowledge base: vault 0 (the shared one) is the default and isn't sent. */
  private kbOptions(vault: number, params: Record<string, string> = {}) {
    return { ...this.getHttpOptions(), params: vault ? { ...params, vault: String(vault) } : params };
  }

  /** The user's knowledge bases: the shared one first, then the agents' own ones. */
  async getKBVaults(): Promise<IKBVault[]> {
    return await lastValueFrom(this.http.get<IKBVault[]>(`${this.baseUrl}/api/kb/vaults`, this.getHttpOptions()));
  }

  /** The memory of a knowledge base and how full it is. */
  async getKBMemory(vault = 0): Promise<IKBMemory> {
    return await lastValueFrom(this.http.get<IKBMemory>(`${this.baseUrl}/api/kb/memory`, this.kbOptions(vault)));
  }

  /** Review a conversation for its agent's memory now (as happens once it has been quiet for a while). */
  async reviewConversationMemory(conversationId: string): Promise<IKBReviewResult> {
    return await lastValueFrom(
      this.http.post<IKBReviewResult>(`${this.baseUrl}/api/kb/review`, { conversationId }, this.getHttpOptions())
    );
  }

  /** The notes with a status, most recently updated first, with the tags in use and the counts. */
  async getKBNotes(status: NoteStatus, tag: string | null = null, vault = 0): Promise<IKBNoteList> {
    const params: Record<string, string> = { status };
    if (tag) params['tag'] = tag;
    return await lastValueFrom(
      this.http.get<IKBNoteList>(`${this.baseUrl}/api/kb/notes`, this.kbOptions(vault, params))
    );
  }

  async searchKBNotes(query: string, status: NoteStatus, vault = 0): Promise<IKBSearchHit[]> {
    return await lastValueFrom(
      this.http.get<IKBSearchHit[]>(`${this.baseUrl}/api/kb/search`, this.kbOptions(vault, { q: query, status }))
    );
  }

  async getKBNote(slug: string, vault = 0): Promise<IKBNote> {
    return await lastValueFrom(this.http.get<IKBNote>(this.kbNoteUrl(slug), this.kbOptions(vault)));
  }

  async createKBNote(note: IKBNoteWrite, vault = 0): Promise<IKBNote> {
    return await lastValueFrom(
      this.http.post<IKBNote>(`${this.baseUrl}/api/kb/notes`, note, this.kbOptions(vault))
    );
  }

  /** Replaces all fields; 409 with code "conflict" if the note changed since baseVersion. */
  async updateKBNote(slug: string, note: IKBNoteUpdate, vault = 0): Promise<IKBNote> {
    return await lastValueFrom(this.http.put<IKBNote>(this.kbNoteUrl(slug), note, this.kbOptions(vault)));
  }

  async archiveKBNote(slug: string, vault = 0): Promise<IKBNote> {
    return await lastValueFrom(
      this.http.post<IKBNote>(`${this.kbNoteUrl(slug)}/archive`, {}, this.kbOptions(vault))
    );
  }

  async restoreKBNote(slug: string, vault = 0): Promise<IKBNote> {
    return await lastValueFrom(
      this.http.post<IKBNote>(`${this.kbNoteUrl(slug)}/restore`, {}, this.kbOptions(vault))
    );
  }

  /** Deletes a note for good, with all its versions. */
  async deleteKBNote(slug: string, vault = 0): Promise<void> {
    await lastValueFrom(this.http.delete<void>(this.kbNoteUrl(slug), this.kbOptions(vault)));
  }

  async getKBRevision(slug: string, revisionId: number, vault = 0): Promise<IKBRevision> {
    return await lastValueFrom(
      this.http.get<IKBRevision>(`${this.kbNoteUrl(slug)}/revisions/${revisionId}`, this.kbOptions(vault))
    );
  }

  /** Makes an earlier version the current one (as a new version). */
  async restoreKBRevision(slug: string, revisionId: number, baseVersion: number, vault = 0): Promise<IKBNote> {
    return await lastValueFrom(
      this.http.post<IKBNote>(`${this.kbNoteUrl(slug)}/revisions/${revisionId}/restore`, { baseVersion },
        this.kbOptions(vault))
    );
  }

  /**
   * The files of notes that the answers of a conversation can place in their text: those of the
   * knowledge base its agent uses, and of the ones its earlier messages were written with.
   */
  async getKBFilesOfConversation(conversationId: string): Promise<IKBFile[]> {
    return await lastValueFrom(
      this.http.get<IKBFile[]>(`${this.baseUrl}/api/kb/files`, { ...this.getHttpOptions(), params: { conversationId } })
    );
  }

  /** Takes a file away from the note that keeps it (deleted, unless a conversation still has it); the note as it is then. */
  async removeKBNoteFile(slug: string, name: string, vault = 0): Promise<IKBNote> {
    return await lastValueFrom(
      this.http.delete<IKBNote>(`${this.kbNoteUrl(slug)}/files/${encodeURIComponent(name)}`, this.kbOptions(vault))
    );
  }

  /** All notes as a zip that opens as an Obsidian vault, with the times in the time zone (e.g. Europe/Berlin). */
  async exportKnowledgeBase(timeZone: string | null, vault = 0): Promise<Blob> {
    const params: Record<string, string> = timeZone ? { tz: timeZone } : {};
    return await lastValueFrom(
      this.http.get(`${this.baseUrl}/api/kb/export`, { ...this.kbOptions(vault, params), responseType: 'blob' })
    );
  }

}
