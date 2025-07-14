import { Injectable, OnDestroy } from '@angular/core';
import { BehaviorSubject, firstValueFrom, lastValueFrom, Observable } from 'rxjs';
import { Message } from '../data/objects/message';
import { DBService } from '../data/db.service';
import { ApiService } from '../api/api.service';
import { Conversation } from '../data/objects/conversation';
import { SettingsService } from '../settings/settings.service';
import { DisplayService } from '../sidebar/service/display.service';
import { AuthService } from "../auth/auth.service";
import { HttpClient } from '@angular/common/http';
import { environment } from '../environments/environment';
import { FilePreview, UploadStatus } from '../data/objects/file-preview';


@Injectable({
  providedIn: 'root'
})
export class ChatService implements OnDestroy {
  // The conversation this service is managing
  private conversation!: Conversation;
  // TODO: Start with conversation null, only create new conversation once the first message is sent!
  //  (e.g. we don't wanna have empty conversations with no messages)

  // The ChatService is responsible for managing and exposing the messages.
  private messagesSubject: BehaviorSubject<Message[]> = new BehaviorSubject<Message[]>([]);
  public messages: Observable<Message[]> = this.messagesSubject.asObservable();

  private conversationsSubject = new BehaviorSubject<Conversation[]>([]);
  public conversations$: Observable<Conversation[]> = this.conversationsSubject.asObservable();

  private isNewConversationSubject = new BehaviorSubject<boolean>(false);
  public isNewConversation$ = this.isNewConversationSubject.asObservable();

  // Add loading state for sync operations
  private isSyncingSubject = new BehaviorSubject<boolean>(false);
  public isSyncing$ = this.isSyncingSubject.asObservable();

  private syncPromise: Promise<void> | null = null;

  // Connection monitoring
  private connectionCheckInterval: any;
  private lastConnectionState: boolean = true;

  // Constructor
  constructor(
    private dbService: DBService,
    private apiService: ApiService,
    private settingsService: SettingsService,
    private displayService: DisplayService,
    private authService: AuthService,
    private http: HttpClient
  ) {
    this.initializeService();
  }

  private async initializeService() {
    await this.dbService.getDatabaseReadyPromise();

    // Load local data first (fast)
    await this.loadAllConversations();
    const localConversations = this.conversationsSubject.getValue();

    // Display local data immediately
    if (localConversations.length > 0) {
      const latest = localConversations[0]; // Already sorted by loadAllConversations
      await this.loadConversation(latest);
      this.displayService.setActiveConversation(latest.id);
    } else {
      this.loadConversation(new Conversation(0, 0, 'New Chat', ['user']));
      this.displayService.setActiveConversation(0);
    }

    // Sync with server in background (don't await)
    this.syncInBackground();
    
    // Set up connection monitoring for pending file uploads
    this.setupConnectionMonitoring();
  }

  private async isBackendAvailable(): Promise<boolean> {
    try {
      const response = await lastValueFrom(
        this.http.get(`${environment.apiUrl}/api/llms`, { withCredentials: true })
      );
      return true;
    } catch (error) {
      console.warn('Backend not available:', error);
      return false;
    }
  }

  private async syncInBackground() {
    // Check if backend is available first
    const backendAvailable = await this.isBackendAvailable();
    if (!backendAvailable) {
      console.log('Backend not available, skipping sync');
      return;
    }

    if (this.authService.isGuest) {
      return;
    }
    // Prevent multiple simultaneous syncs
    if (this.syncPromise) {
      return this.syncPromise;
    }

    this.syncPromise = this.performSync();
    try {
      await this.syncPromise;
    } finally {
      this.syncPromise = null;
    }
  }

  // TODO: Move sync logic to a separate sync service!
  private async performSync() {
    this.isSyncingSubject.next(true);

    try {
      const serverConversationsData = await this.apiService.getConversations();

      // Convert plain objects to Conversation instances
      const serverConversations = serverConversationsData.map(data =>
        Conversation.fromApiResponse(data)
      );

      if (serverConversations.length === 0) {
        console.log('No conversations on server');
        return;
      }

      // Update conversation list if different
      await this.mergeServerConversations(serverConversations);

      // Only sync current conversation's messages
      const currentConvId = this.conversation?.id;
      if (currentConvId && currentConvId !== 0) {
        const serverConv = serverConversations.find(c => c.id === currentConvId);
        if (serverConv) {
          await this.syncConversationIfNeeded(serverConv);
        }
      }
    } catch (error) {
      console.error('Background sync failed:', error);
      // Don't throw - we have local data
    } finally {
      this.isSyncingSubject.next(false);
    }
  }

  private async mergeServerConversations(serverConversations: Conversation[]) {
    // Get local conversations
    const localConversations = await this.dbService.getAllConversations();
    const localConvMap = new Map(localConversations.map(c => [c.id, c]));

    let hasChanges = false;

    // Check for new conversations from server
    for (const serverConv of serverConversations) {
      if (!localConvMap.has(serverConv.id)) {
        // This is a new conversation from server - we need to fetch its details
        // For now, we'll create a placeholder. In a real app, you'd fetch full details
        const newConv = new Conversation(
          serverConv.id,
          this.displayService.activeConversationId$.value || 1, // Use current user ID
          `Conversation ${serverConv.id}`,
          ['user', 'Assistant']
        );
        await this.dbService.addConversation(newConv);
        hasChanges = true;
      }
    }

    if (hasChanges) {
      await this.loadAllConversations();
    }
  }

  private async syncConversationIfNeeded(serverConv: any) {
    // TODO: Why is the received conversation object not converted to conversation already?
    //const test123 = Conversation.fromApiResponse(this.conversation)
    //console.log("Conversation hash: ", test123.computeHash(this.dbService))
    //console.log(this.conversation)
    //console.log("Conversation: ", this.conversation)
    const localHash = await this.conversation.computeHash(this.dbService);
    // TODO: The issue is that this.conversation is null by default

    if (localHash !== serverConv.hashsum) {
      console.log('Syncing messages for conversation:', serverConv.id);

      // Get server messages
      const serverMessages = await this.apiService.getConversationMessages(
        serverConv.id,
        50 // Get more messages during sync
      );

      // Update local database
      await this.dbService.deleteMessagesByConversationId(serverConv.id);
      for (const msg of serverMessages) {
        await this.dbService.addMessage(msg);
      }

      // Only update UI if still viewing this conversation
      if (this.conversation.id === serverConv.id) {
        serverMessages.sort((a, b) => a.time!.getTime()! - b.time!.getTime());
        this.messagesSubject.next(serverMessages);
      }
    }
  }

  // Refresh the conversation - now just calls sync
  private async refreshConversation() {
    await this.syncInBackground();
  }

  // Public method for manual sync
  public async syncCurrentConversation() {
    if (this.conversation?.id && this.conversation.id !== 0) {
      await this.syncInBackground();
    }
  }

  // TODO: Implement a way to call the refreshConversation method at regular intervals (e.g. every minute and when the app is opened)

  // Add one or more messages to the conversation
  private addMessage(message: Message | Message[]) {
    // Check if the message is an array
    if (Array.isArray(message)) {
      // Sort the messages by time
      message.sort((a, b) => a.time!.getTime()! - b.time!.getTime())

      // Add each message to the messages array
      this.messagesSubject.next([...this.messagesSubject.getValue(), ...message]);

      // Add the messages to the database
      message.forEach((message) => {
        this.dbService.addMessage(message);
      });
    } else {
      // Add the message to the database
      this.dbService.addMessage(message);

      // Add the message to the messages array
      this.messagesSubject.next([...this.messagesSubject.getValue(), message]);
    }
  }

  // Send a message
  public async sendMessage(content: string, roleName: string = 'user'): Promise<void> {
    if (this.isNewConversationSubject.getValue()) {
      // Check if backend is available before creating conversation
      const backendAvailable = await this.isBackendAvailable();

      if (!backendAvailable) {
        // Create local-only conversation
        const localConv = new Conversation(
          Math.floor(Date.now() / 1000), // Use timestamp as temporary ID
          0, // Guest user ID
          content.length > 30 ? content.substring(0, 27) + '...' : content,
          ['user', 'Assistant']
        );
        this.conversation = localConv;
        await this.dbService.addConversation(this.conversation);
        this.isNewConversationSubject.next(false);
        await this.loadAllConversations();
        this.displayService.setActiveConversation(this.conversation.id);
      } else {
        // Original code for online mode
        const title = content.length > 30 ? content.substring(0, 27) + '...' : content;
        const newConvData = new Conversation(0, 0, title, ['user', 'Assistant']);

        try {
          const createdConv = await this.apiService.createConversation(newConvData);
          this.conversation = createdConv;
          await this.dbService.addConversation(this.conversation);
          this.isNewConversationSubject.next(false);
          await this.loadAllConversations();
          this.displayService.setActiveConversation(this.conversation.id);
        } catch (error) {
          console.error('Failed to create conversation:', error);
          // Create local conversation as fallback
          const localConv = new Conversation(
            Math.floor(Date.now() / 1000),
            0,
            title,
            ['user', 'Assistant']
          );
          this.conversation = localConv;
          await this.dbService.addConversation(this.conversation);
          this.isNewConversationSubject.next(false);
          await this.loadAllConversations();
          this.displayService.setActiveConversation(this.conversation.id);
        }
      }
    }

    // Use the new factory method to create a text message
    const message = Message.createText(
      {
        id: Math.floor(new Date().getTime() / 1000),
        conversationId: this.conversation.id,
        roleName: roleName,
        time: new Date()
      },
      content
    );

    // Add the message to the conversation
    this.addMessage(message);

    // Try to send the message to the backend if available
    const backendAvailable = await this.isBackendAvailable();
    if (backendAvailable) {
      try {
        const response = await this.apiService.sendMessage(message);
        const responseMessage = Message.createText({
          id: response,
          conversationId: this.conversation.id,
          roleName: roleName,
          time: message.time
        }, content);

        if(message.id !== response){
          console.log('Message ID mismatch, updating local state:', message.id, response);
          await this.dbService.addMessage(responseMessage);
          await this.dbService.deleteMessage(message.id);

          const messages = this.messagesSubject.getValue();
          const index = messages.findIndex(m => m.id === message.id);
          if(index !== -1) {
            messages[index] = responseMessage;
            this.messagesSubject.next([...messages]);
          }
        } else {
          console.log('Message sent and ID matched:', response);
        }
      } catch(error) {
        console.error('Error sending message:', error);
        // Message is already saved locally, so we can continue
      }
    } else {
      console.log('Backend not available, message saved locally only');
    }

    // Update conversation timestamp
    this.conversation.updatedAt = new Date();
    await this.dbService.updateConversation(this.conversation);

    // This will trigger re-grouping in sidebar
    await this.loadAllConversations();

    // Trigger a sync after sending the message (especially important for new conversations)
    this.syncInBackground();
  }

  // Send a file inside a message
  public async sendMessageWithFiles(
    content: string,
    files: FilePreview[],
    roleName: string = 'user'
  ): Promise<void> {
    // Handle new conversation creation if needed
    if (this.isNewConversationSubject.getValue()) {
      const title = content.length > 30 ? content.substring(0, 27) + '...' : content || 'New conversation with files';
      await this.createNewConversation(title);
    }

    // Files should already be uploaded by the input component when selected
    // Just verify that uploaded files have proper status
    const backendAvailable = await this.isBackendAvailable();
    if (backendAvailable && files.length > 0) {
      // Check if any files still need to be uploaded (fallback)
      const pendingFiles = files.filter(f => f.uploadStatus === UploadStatus.PENDING);
      
      if (pendingFiles.length > 0) {
        console.log('Some files still pending upload, uploading now as fallback');
        try {
          const uploadedFileIds = await this.apiService.uploadFiles(pendingFiles);
          
          // Update file IDs with server-assigned IDs
          pendingFiles.forEach((f, index) => {
            f.uploadStatus = UploadStatus.COMPLETED;
            f.id = uploadedFileIds[index] || `file-${Date.now()}-${Math.random()}`;
          });
        } catch (error) {
          console.error('Error uploading pending files:', error);
          // Continue anyway - files will be marked as failed
          pendingFiles.forEach(f => {
            f.uploadStatus = UploadStatus.FAILED;
            f.error = 'Upload failed';
          });
        }
      }
    } else if (!backendAvailable && files.length > 0) {
      // Offline mode: Mark files as pending upload if not already done
      console.log('Backend not available, ensuring files are marked for offline storage');
      files.forEach(f => {
        if (f.uploadStatus !== UploadStatus.PENDING) {
          f.uploadStatus = UploadStatus.PENDING;
          f.id = f.id || `offline-${Date.now()}-${Math.random()}`;
          f.error = 'Waiting for connection';
        }
      });
      
      // Store file data in IndexedDB for later upload
      await this.storeOfflineFiles(files);
    }

    // Create message with file attachments
    const message = Message.createText(
      {
        id: Math.floor(new Date().getTime() / 1000),
        conversationId: this.conversation.id,
        roleName: roleName,
        time: new Date()
      },
      content,
      files
    );

    // Add the message to the conversation
    this.addMessage(message);

    // Send to backend if available
    if (backendAvailable) {
      try {
        const response = await this.apiService.sendMessage(message);

        // Handle ID mismatch same as regular messages
        if(message.id !== response){
          // Create a new message object with the server-assigned ID
          const responseMessage = Message.createText({
            id: response,
            conversationId: this.conversation.id,
            roleName: message.roleName,
            time: message.time
          }, message.textContent ? message.textContent : "", message.attachments);

          // Update the message in the database
          await this.updateMessageId(message.id, responseMessage);
        }
      } catch(error) {
        console.error('Error sending message with files:', error);
      }
    }

    // Update conversation and trigger sync
    this.conversation.updatedAt = new Date();
    await this.dbService.updateConversation(this.conversation);
    await this.loadAllConversations();
    this.syncInBackground();
  }

  // Send a voice message
  public async sendVoiceMessage(
    audioBlob: Blob,
    duration: number,
    mimeType: string = 'audio/webm',
    roleName: string = 'user'
  ): Promise<void> {
    // Handle new conversation creation if needed
    if (this.isNewConversationSubject.getValue()) {
      await this.createNewConversation('Voice conversation');
    }

    // Convert blob to base64
    const base64Audio = await this.blobToBase64(audioBlob);

    // Create voice message using factory method
    const message = Message.createVoice(
      {
        id: Math.floor(new Date().getTime() / 1000),
        conversationId: this.conversation.id,
        roleName: roleName,
        time: new Date()
      },
      base64Audio,
      duration,
      mimeType
    );

    // Add the message to the conversation
    this.addMessage(message);

    // Send to backend if available
    const backendAvailable = await this.isBackendAvailable();
    if (backendAvailable) {
      try {
        const response = await this.apiService.sendMessage(message);
        if(message.id !== response){
          // Create a new message object with the server-assigned ID
          const responseMessage = Message.createText({
            id: response,
            conversationId: this.conversation.id,
            roleName: message.roleName,
            time: message.time
          }, message.textContent ? message.textContent : "", message.attachments);

          // Update the message in the database
          await this.updateMessageId(message.id, responseMessage);
        }
      } catch(error) {
        console.error('Error sending voice message:', error);
      }
    }

    // Update conversation and trigger sync
    this.conversation.updatedAt = new Date();
    await this.dbService.updateConversation(this.conversation);
    await this.loadAllConversations();
    this.syncInBackground();
  }

  // Helper method to convert blob to base64
  private blobToBase64(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const base64String = reader.result as string;
        // Remove the data URL prefix (e.g., "data:audio/webm;base64,")
        const base64Data = base64String.split(',')[1];
        resolve(base64Data);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }

  // Helper method to create a new conversation
  private async createNewConversation(title: string): Promise<void> {
    const backendAvailable = await this.isBackendAvailable();

    if (!backendAvailable) {
      // Create local-only conversation
      const localConv = new Conversation(
        Math.floor(Date.now() / 1000),
        0,
        title,
        ['user', 'Assistant']
      );
      this.conversation = localConv;
      await this.dbService.addConversation(this.conversation);
    } else {
      // Create on server
      const newConvData = new Conversation(0, 0, title, ['user', 'Assistant']);
      try {
        const createdConv = await this.apiService.createConversation(newConvData);
        this.conversation = createdConv;
        await this.dbService.addConversation(this.conversation);
      } catch (error) {
        console.error('Failed to create conversation:', error);
        // Fallback to local
        const localConv = new Conversation(
          Math.floor(Date.now() / 1000),
          0,
          title,
          ['user', 'Assistant']
        );
        this.conversation = localConv;
        await this.dbService.addConversation(this.conversation);
      }
    }

    this.isNewConversationSubject.next(false);
    await this.loadAllConversations();
    this.displayService.setActiveConversation(this.conversation.id);
  }

  // Helper method to update message ID after server response
  private async updateMessageId(oldId: number, newMessage: Message): Promise<void> {
    console.log('Message ID mismatch, updating local state:', oldId, newMessage.id);
    await this.dbService.addMessage(newMessage);
    await this.dbService.deleteMessage(oldId);

    const messages = this.messagesSubject.getValue();
    const index = messages.findIndex(m => m.id === oldId);
    if(index !== -1) {
      messages[index] = newMessage;
      this.messagesSubject.next([...messages]);
    }
  }

  // Generate a message
  public async generateMessage(participant: string) {
    // Check if backend is available first
    const backendAvailable = await this.isBackendAvailable();
    if (!backendAvailable) {
      // Add a placeholder message when offline
      const offlineMessage = Message.createText(
        {
          id: Math.floor(new Date().getTime() / 1000),
          conversationId: this.conversation.id,
          roleName: participant,
          time: new Date()
        },
        'Sorry, I cannot generate responses while offline. Please check your connection.'
      );
      this.addMessage(offlineMessage);
      return;
    }

    // Original code continues...
    const currentMessages = this.messagesSubject.getValue();
    // Get the last message
    const lastMessage = currentMessages[currentMessages.length - 1];

    console.log('Generating message:', lastMessage, participant);

    try {
      const settings = await firstValueFrom(this.settingsService.getSettings());
      const generatedMessage = await this.apiService.generateMessage(lastMessage, participant, settings);

      // Add to local state and database
      this.addMessage(generatedMessage);
      this.authService.setGuestLimitReached(false); // Reset on successful generation
    } catch (error: any) {
      if (error.status === 429) {
        console.error('Guest limit reached:', error);
        const detail = error.error?.detail;
        let resetTimeMessage = 'Please try again later.';
        if (detail && detail.includes('after')) {
          const resetTimeISO = detail.split('after ')[1];
          if (resetTimeISO) {
            const resetDate = new Date(resetTimeISO);
            const formattedTime = resetDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            resetTimeMessage = `You have reached your request limit. You can generate more answers after ${formattedTime}.`;
          }
        }
        this.authService.setGuestLimitReached(true, resetTimeMessage);
      } else {
        console.error('Error generating message:', error);
        // Add error message to chat
        const errorMessage = Message.createText(
          {
            id: Math.floor(new Date().getTime() / 1000),
            conversationId: this.conversation.id,
            roleName: participant,
            time: new Date()
          },
          'Sorry, I encountered an error while generating a response. Please try again.'
        );
        this.addMessage(errorMessage);
      }
      throw error;
    }
  }

  // Patch a message in the conversation
  public async patchMessage(messageId: number, content: string) {
    try {
      // Get the conversation ID
      const conversationId = this.conversation.id;

      // Call the API to patch the message
      await this.apiService.patchMessage(conversationId, messageId, content);

      // Update the message in the local state
      const currentMessages = this.messagesSubject.getValue();
      const messageIndex = currentMessages.findIndex(msg => msg.id === messageId);

      if (messageIndex !== -1) {
        const originalMessage = currentMessages[messageIndex];

        // Only text messages can be patched
        if (originalMessage.isText()) {
          // Create a new message instance with updated content
          const updatedTextMessage = Message.createText(
            {
              id: originalMessage.id,
              conversationId: originalMessage.conversationId,
              roleName: originalMessage.roleName,
              time: originalMessage.time
            },
            content,
            originalMessage.content.attachments
          );
          currentMessages[messageIndex] = updatedTextMessage;
          this.messagesSubject.next([...currentMessages]);

          // Update in database
          await this.dbService.updateMessage(updatedTextMessage);
        }
      }
    } catch (error) {
      console.error('Error patching message:', error);
      throw error;
    }
  }

  // Delete a message from the conversation
  public async deleteMessage(messageId: number) {
    try {
      await this.apiService.deleteMessage(this.conversation.id, messageId);

      // Remove from local state
      const currentMessages = this.messagesSubject.getValue();
      const updatedMessages = currentMessages.filter(msg => msg.id !== messageId);
      this.messagesSubject.next(updatedMessages);

      // Remove from database
      await this.dbService.deleteMessage(messageId);
    } catch (error) {
      console.error('Error deleting message:', error);
      throw error;
    }
  }

  // Regenerate a message in the conversation
  public async regenerateMessage(message: Message) {
    console.log('Regenerating message:', message.id);
    
    // Find all messages in the conversation
    const allMessages = this.messagesSubject.getValue();
    const messageIndex = allMessages.findIndex(m => m.id === message.id);
    
    if (messageIndex === -1) {
      console.error('Message not found for regeneration');
      return;
    }
    
    // Delete this message and all messages after it
    const messagesToDelete = allMessages.slice(messageIndex);
    
    try {
      // Delete from backend and local storage
      for (const msg of messagesToDelete) {
        await this.deleteMessage(msg.id);
      }
      
      // Generate a new response (using the role from the message being regenerated)
      await this.generateMessage(message.roleName);
    } catch (error) {
      console.error('Error regenerating message:', error);
      throw error;
    }
  }

  // Loads a specific conversation and its messages into memory.
  public async loadConversation(conversation: Conversation) {
    if (conversation.id === 0) {
      this.isNewConversationSubject.next(true);
      this.conversation = conversation;
      this.messagesSubject.next([]);
    } else {
      this.isNewConversationSubject.next(false);
      this.conversation = conversation;
      const messages = await this.dbService.getMessagesByConversationId(conversation.id);
      messages.sort((a, b) => a.time!.getTime()! - b.time!.getTime());
      this.messagesSubject.next(messages);

      // Trigger background sync for this conversation
      this.syncInBackground();
    }
  }

  // Create a new conversation
  public async createConversation(conversation: Conversation): Promise<Conversation> {
    // Set timestamps
    conversation.createdAt = new Date();
    conversation.updatedAt = new Date();

    // Save to database
    await this.dbService.addConversation(conversation);

    // Update the conversations list
    await this.loadAllConversations();

    return conversation;
  }

  // Load all conversations from database (replace getDummyConversations)
  public async loadAllConversations(): Promise<Conversation[]> {
    const conversations = await this.dbService.getAllConversations();
    this.conversationsSubject.next(conversations);
    return conversations;
  }

  // Get conversations as observable
  public getConversations(): Observable<Conversation[]> {
    return this.conversations$;
  }

  // Update conversation (e.g., rename)
  public async updateConversation(conversation: Conversation): Promise<void> {
    conversation.updatedAt = new Date();
    await this.dbService.updateConversation(conversation);
    await this.loadAllConversations();
  }

  // Delete conversation
  public async deleteConversation(conversationId: number): Promise<void> {
    // Delete all messages first
    await this.dbService.deleteMessagesByConversationId(conversationId);
    // Delete the conversation
    await this.dbService.deleteConversation(conversationId);
    // Reload conversations
    await this.loadAllConversations();

    // If we deleted the current conversation, load a new one
    if (this.conversation?.id === conversationId) {
      const remaining = this.conversationsSubject.getValue();
      if (remaining.length > 0) {
        await this.loadConversation(remaining[0]);
        this.displayService.setActiveConversation(remaining[0].id);
      } else {
        this.loadConversation(new Conversation(0, 0, 'New Chat', ['user']));
        this.displayService.setActiveConversation(0);
      }
    }
  }

  // Store files in IndexedDB for offline upload later
  private async storeOfflineFiles(files: FilePreview[]): Promise<void> {
    // Store file data in a special offline files store
    // This would be implemented in DbService
    console.log('Storing offline files for later upload:', files);
    // TODO: Implement actual offline file storage in DbService
  }

  // Check and upload any pending offline files when connection is restored
  public async uploadPendingFiles(): Promise<void> {
    const backendAvailable = await this.isBackendAvailable();
    if (!backendAvailable) {
      console.log('Backend still not available, skipping pending file uploads');
      return;
    }

    // Get all messages with pending file uploads
    const allMessages = await this.dbService.getAllMessages();
    const messagesWithPendingFiles = allMessages.filter(msg => 
      msg.isText() && 
      msg.attachments?.some(f => f.uploadStatus === UploadStatus.PENDING)
    );

    console.log(`Found ${messagesWithPendingFiles.length} messages with pending file uploads`);

    for (const message of messagesWithPendingFiles) {
      if (!message.attachments) continue;
      
      const pendingFiles = message.attachments.filter(f => f.uploadStatus === UploadStatus.PENDING);
      if (pendingFiles.length === 0) continue;

      try {
        // Try to upload the pending files
        const uploadedFileIds = await this.apiService.uploadFiles(pendingFiles);
        
        // Update the message with new file IDs and status
        pendingFiles.forEach((f, index) => {
          f.uploadStatus = UploadStatus.COMPLETED;
          f.id = uploadedFileIds[index] || f.id;
          f.error = undefined;
        });

        // Update the message in the database
        await this.dbService.updateMessage(message);
        
        // Update UI if this message is currently displayed
        const currentMessages = this.messagesSubject.getValue();
        const messageIndex = currentMessages.findIndex(m => m.id === message.id);
        if (messageIndex !== -1) {
          currentMessages[messageIndex] = message;
          this.messagesSubject.next([...currentMessages]);
        }

        console.log(`Successfully uploaded files for message ${message.id}`);
      } catch (error) {
        console.error(`Failed to upload files for message ${message.id}:`, error);
        // Mark files as failed
        pendingFiles.forEach(f => {
          f.uploadStatus = UploadStatus.FAILED;
          f.error = 'Upload failed after retry';
        });
        await this.dbService.updateMessage(message);
      }
    }
  }

  // Set up connection monitoring for automatic file uploads
  private setupConnectionMonitoring(): void {
    // Check connection every 30 seconds
    this.connectionCheckInterval = setInterval(async () => {
      const isConnected = await this.isBackendAvailable();
      
      // If connection was restored
      if (!this.lastConnectionState && isConnected) {
        console.log('Connection restored, checking for pending file uploads');
        await this.uploadPendingFiles();
        // Also trigger a sync
        this.syncInBackground();
      }
      
      this.lastConnectionState = isConnected;
    }, 30000);
    
    // Also check immediately
    this.isBackendAvailable().then(isConnected => {
      this.lastConnectionState = isConnected;
    });
  }

  // Clean up on service destroy
  ngOnDestroy(): void {
    if (this.connectionCheckInterval) {
      clearInterval(this.connectionCheckInterval);
    }
  }
}
