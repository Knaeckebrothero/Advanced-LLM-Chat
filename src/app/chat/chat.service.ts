import { Injectable } from '@angular/core';
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
export class ChatService {
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

    const message = new Message({
      id: Math.floor(new Date().getTime() / 1000),
      conversationId: this.conversation.id,
      roleName: roleName,
      content: content,
      time: new Date()
    });

    // Add the message to the conversation
    this.addMessage(message);

    // Try to send the message to the backend if available
    const backendAvailable = await this.isBackendAvailable();
    if (backendAvailable) {
      try {
        const response = await this.apiService.sendMessage(message);
        if(message.id !== response.id){
          console.log('Message ID mismatch, updating local state:', message.id, response.id);
          await this.dbService.addMessage(response);
          await this.dbService.deleteMessage(message.id);

          const messages = this.messagesSubject.getValue();
          const index = messages.findIndex(m => m.id === message.id);
          if(index !== -1) {
            messages[index] = response;
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
    // TODO: Implementation for sending messages with attachments
  }

  // Generate a message
  public async generateMessage(participant: string) {
    // Check if backend is available first
    const backendAvailable = await this.isBackendAvailable();
    if (!backendAvailable) {
      // Add a placeholder message when offline
      const offlineMessage = new Message({
        id: Math.floor(new Date().getTime() / 1000),
        conversationId: this.conversation.id,
        roleName: participant,
        content: 'Sorry, I cannot generate responses while offline. Please check your connection.',
        time: new Date()
      });
      this.addMessage(offlineMessage);
      return;
    }

    // Original code continues...
    const currentMessages = this.messagesSubject.getValue();
    // Convert the last message to a Message instance if it's not already one
    const lastMessage = currentMessages[currentMessages.length - 1] instanceof Message
      ? currentMessages[currentMessages.length - 1]
      : new Message(currentMessages[currentMessages.length - 1]);

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
        const errorMessage = new Message({
          id: Math.floor(new Date().getTime() / 1000),
          conversationId: this.conversation.id,
          roleName: participant,
          content: 'Sorry, I encountered an error while generating a response. Please try again.',
          time: new Date()
        });
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
      const updatedMessage = await this.apiService.patchMessage(conversationId, messageId, content);

      // Update the message in the local state
      const currentMessages = this.messagesSubject.getValue();
      const messageIndex = currentMessages.findIndex(msg => msg.id === messageId);

      if (messageIndex !== -1) {
        currentMessages[messageIndex] = new Message({
          ...currentMessages[messageIndex],
          ...updatedMessage,
        });
        // currentMessages[messageIndex] = { ...currentMessages[messageIndex], ...updatedMessage };
        this.messagesSubject.next([...currentMessages]);

        // Update in database
        await this.dbService.updateMessage(currentMessages[messageIndex]);
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
  public regenerateMessage(message: Message) {
    console.log('Regenerating message');
    // TODO: Implement regenerate message method!
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
}
