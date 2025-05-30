import {Injectable} from '@angular/core';
import {BehaviorSubject, Observable} from 'rxjs';
import {Message, MessageData} from '../data/objects/message';
import {DBService} from '../data/db.service';
import {ApiService} from '../api/api.service';
import {Conversation} from '../data/objects/conversation';
import {User} from '../data/objects/user';
import {AuthService} from '../auth/auth.service';

@Injectable({
  providedIn: 'root'
})
export class ChatService {
  private conversation!: Conversation;
  private currentUser: User | null = null;

  private messagesSubject = new BehaviorSubject<Message[]>([]);
  public messages$: Observable<Message[]> = this.messagesSubject.asObservable();

  private currentConversationSubject = new BehaviorSubject<Conversation | null>(null);
  public currentConversation$: Observable<Conversation | null> = this.currentConversationSubject.asObservable();

  constructor(
    private dbService: DBService,
    private apiService: ApiService,
    private authService: AuthService
  ) {
    // Subscribe to auth changes
    this.authService.currentUser$.subscribe(user => {
      if (user) {
        this.initializeChat();
      } else {
        // Clear chat when user logs out
        this.clearChat();
      }
    });
  }

  private clearChat(): void {
    this.currentUser = null;
    this.messagesSubject.next([]);
    this.currentConversationSubject.next(null);
  }

  private async initializeChat(): Promise<void> {
    console.log("ChatService: Initializing...");
    await this.dbService.getDatabaseReadyPromise();

    // Get current user from auth service
    const authUser = this.authService.getCurrentUser();
    if (!authUser) {
      console.error("ChatService: No authenticated user found");
      this.clearChat();
      return;
    }

    // Create User object with the session token
    this.currentUser = {
      id: authUser.id,
      name: authUser.name,
      email: authUser.email,
      accessToken: this.authService.getToken() || ''
    };

    if (this.currentUser) {
      console.log("ChatService: Current user loaded -", this.currentUser.name, `(ID: ${this.currentUser.id})`);
      await this.loadOrCreateConversationForUser(this.currentUser);
    } else {
      console.error("ChatService: CRITICAL - No current user found after DB init. Chat functionality will be limited.");
      this.currentConversationSubject.next(null);
    }
  }

  private async loadOrCreateConversationForUser(user: User): Promise<void> {
    const userConversations = await this.dbService.getConversationsByUserId(user.id);
    if (userConversations && userConversations.length > 0) {
      this.conversation = userConversations[0];
      console.log("ChatService: Loaded existing conversation:", this.conversation.name, `(ID: ${this.conversation.id})`);
    } else {
      this.conversation = new Conversation(
        null,
        user.id,
        `Chat with ${user.name}`,
        ["user", "Assistant"]
      );
      console.log("ChatService: Initialized new in-memory conversation (not yet saved to DB/Backend):", this.conversation.name);
    }
    this.currentConversationSubject.next(this.conversation);

    if (this.conversation && this.conversation.id !== null) {
      await this.loadMessagesForCurrentConversation();
      this.refreshConversationFromServer();
    } else if (this.conversation && this.conversation.id === null) {
      this.messagesSubject.next([]);
      console.log("ChatService: New conversation instance created. Messages will load/populate after the first successful send.");
    }
  }

  private async loadMessagesForCurrentConversation(): Promise<void> {
    if (!this.conversation || this.conversation.id === null) {
      console.warn("ChatService: Attempted to load messages for a conversation with a null ID.");
      this.messagesSubject.next([]);
      return;
    }
    const messages = await this.dbService.getMessagesByConversationId(this.conversation.id);
    const sortedMessages = (messages || []).sort((a, b) => (a.time?.getTime() || 0) - (b.time?.getTime() || 0));
    this.messagesSubject.next([...sortedMessages]);
    console.log(`ChatService: Messages loaded for conversation ID ${this.conversation.id}: ${sortedMessages.length} messages.`);
  }

  private async refreshConversationFromServer() {
    if (!this.currentUser || !this.conversation || this.conversation.id === null) {
      console.log('ChatService: Refresh aborted. User or conversation (with a valid server ID) not properly initialized.');
      return;
    }

    try {
      const remoteConversations = await this.apiService.getConversationsByUser(this.currentUser.id);
      const remoteCurrentConversationData = remoteConversations.find(c => c.id === this.conversation.id);

      if (!remoteCurrentConversationData) {
        console.log('ChatService: Current local conversation (ID:', this.conversation.id, ') not found on server during refresh.');
        return;
      }

      const remoteCurrentConversation = remoteCurrentConversationData;
      const localHashsum = await this.conversation.computeHash(this.dbService);

      if (remoteCurrentConversation.hashsum !== undefined && localHashsum !== remoteCurrentConversation.hashsum) {
        console.log('ChatService: Conversation hashes mismatch! Local:', localHashsum, 'Remote:', remoteCurrentConversation.hashsum, ". Refreshing messages.");

        const messagesFromServer = await this.apiService.getConversationMessages(remoteCurrentConversation.id!, 50);

        await this.dbService.deleteMessagesByConversationId(this.conversation.id!);
        this.messagesSubject.next([]);

        this.addMessagesToLocalStoreAndSubject(messagesFromServer, this.conversation.id!);

        this.conversation.hashsum = remoteCurrentConversation.hashsum;
        await this.dbService.updateConversation(this.conversation);
      } else if (remoteCurrentConversation.hashsum === undefined) {
        console.warn("ChatService: Remote conversation hashsum is undefined. Cannot compare for refresh. ID:", this.conversation.id);
      } else {
        console.log('ChatService: Conversation hashes match for conversation ID:', this.conversation.id);
      }
    } catch (error) {
      console.error('ChatService: Error refreshing conversation from server:', error);
    }
  }

  private addMessagesToLocalStoreAndSubject(
    messageOrMessages: Message | MessageData | (Message | MessageData)[],
    targetConversationId: number
  ): void {
    const messagesToAddArray = Array.isArray(messageOrMessages) ? messageOrMessages : [messageOrMessages];
    if (messagesToAddArray.length === 0) return;

    const processedMessages: Message[] = messagesToAddArray.map(msgDataOrInstance => {
      const msg = msgDataOrInstance instanceof Message ? msgDataOrInstance : Message.fromApiResponse(msgDataOrInstance as MessageData);
      msg.conversationId = targetConversationId;
      return msg;
    });

    const currentMessages = this.messagesSubject.getValue();
    const uniqueNewMessages = processedMessages.filter(nm => !currentMessages.some(cm => cm.id === nm.id && cm.conversationId === nm.conversationId));

    if (uniqueNewMessages.length > 0) {
      const updatedMessages = [...currentMessages, ...uniqueNewMessages].sort((a, b) => (a.time?.getTime() || 0) - (b.time?.getTime() || 0));
      this.messagesSubject.next(updatedMessages);
      uniqueNewMessages.forEach(async (msg) => {
        try {
          await this.dbService.addMessage(msg);
        } catch (error) {
          console.error(`ChatService: Error adding message to DB (ID: ${msg.id}, ConvID: ${msg.conversationId}):`, error);
        }
      });
    }
  }

  public async sendMessage(content: string, roleName: string = 'user'): Promise<void> {
    if (!this.currentUser || !this.conversation) {
      console.error("ChatService: Cannot send message. User or conversation not initialized.");
      return;
    }

    const tempMessageId = Date.now();
    const messageTime = new Date();

    const message = new Message({
      id: tempMessageId,
      conversationId: this.conversation.id,
      roleName: roleName === 'user' ? this.currentUser.name : roleName,
      content: content,
      time: messageTime
    });

    const currentUIMessages = this.messagesSubject.getValue();
    this.messagesSubject.next([...currentUIMessages, message].sort((a, b) => (a.time?.getTime() || 0) - (b.time?.getTime() || 0)));

    try {
      const {confirmedMessage, newConversation} = await this.apiService.sendMessage(
        message,
        this.conversation
      );
      console.log('ChatService: Message sent. Confirmed Msg ID:', confirmedMessage.id, "New Conv ID:", confirmedMessage.conversationId);

      if (newConversation && this.conversation.id === null) {
        console.log('ChatService: New conversation confirmed by backend. Updating local conversation ID from null to', newConversation.id);

        this.conversation.id = newConversation.id;
        this.conversation.name = newConversation.name;
        this.conversation.participants = newConversation.participants;
        this.conversation.hashsum = newConversation.hashsum;

        await this.dbService.addConversation(this.conversation);
        this.currentConversationSubject.next(this.conversation);
      }

      const finalMessagesAfterTempRemoval = this.messagesSubject.getValue().filter(m => m.id !== tempMessageId);
      this.messagesSubject.next(finalMessagesAfterTempRemoval);

      try {
        await this.dbService.deleteMessage(tempMessageId);
      } catch (dbError) {
        console.warn("ChatService: Could not delete temporary message from DB; it might not have been added or already processed:", dbError);
      }

      this.addMessagesToLocalStoreAndSubject(confirmedMessage, confirmedMessage.conversationId!);

    } catch (error) {
      console.error('ChatService: Error sending message via API:', error);
      const revertedMessages = this.messagesSubject.getValue().filter(m => m.id !== tempMessageId);
      this.messagesSubject.next(revertedMessages);
    }
  }

  public async generateAiResponseMessage(participantName: string = 'Assistant'): Promise<void> {
    if (!this.currentUser || !this.conversation || this.conversation.id === null) {
      console.error("ChatService: Cannot generate AI message. Conversation not fully initialized with a server-assigned ID.");
      return;
    }

    const currentMessages = this.messagesSubject.getValue();
    if (currentMessages.length === 0) {
      console.warn("ChatService: Cannot generate AI message. No previous messages in conversation to provide context.");
      return;
    }

    const lastMessage = currentMessages[currentMessages.length - 1];
    console.log(`ChatService: Generating AI message for ${participantName} based on last message: "${lastMessage.content}"`);

    try {
      const generatedMessage = await this.apiService.generateMessage(lastMessage, participantName);
      this.addMessagesToLocalStoreAndSubject(generatedMessage, this.conversation.id!);
      console.log("ChatService: Generated AI message added:", generatedMessage.content);
    } catch (error) {
      console.error('ChatService: Error generating AI message via API:', error);
    }
  }

  public async patchMessage(messageId: number, newContent: string): Promise<void> {
    if (!this.currentUser || !this.conversation || this.conversation.id === null) {
      console.error("ChatService: Cannot patch message. Conversation not fully initialized with a server-assigned ID.");
      return;
    }
    try {
      const updatedMessage = await this.apiService.patchMessage(this.conversation.id!, messageId, newContent);

      const currentMessages = this.messagesSubject.getValue();
      const messageIndex = currentMessages.findIndex(msg => msg.id === messageId && msg.conversationId === this.conversation.id);

      if (messageIndex !== -1) {
        currentMessages[messageIndex] = updatedMessage;
        this.messagesSubject.next([...currentMessages]);
        await this.dbService.updateMessage(updatedMessage);
        console.log("ChatService: Message patched successfully:", updatedMessage.content);
      } else {
        console.warn("ChatService: Message to patch not found in local store or conversation ID mismatch.");
      }
    } catch (error) {
      console.error('ChatService: Error patching message via API:', error);
    }
  }

  public async deleteMessage(messageId: number): Promise<void> {
    if (!this.currentUser || !this.conversation || this.conversation.id === null) {
      console.error("ChatService: Cannot delete message. Conversation not fully initialized with a server-assigned ID.");
      return;
    }
    try {
      await this.apiService.deleteMessage(this.conversation.id!, messageId);

      const updatedMessages = this.messagesSubject.getValue().filter(msg => !(msg.id === messageId && msg.conversationId === this.conversation.id));
      this.messagesSubject.next(updatedMessages);
      await this.dbService.deleteMessage(messageId);
      console.log("ChatService: Message deleted successfully, ID:", messageId);
    } catch (error) {
      console.error('ChatService: Error deleting message via API:', error);
    }
  }

  public regenerateMessage(messageToRegenerate: Message): void {
    if (!this.currentUser || !this.conversation || this.conversation.id === null) {
      console.error("ChatService: Cannot regenerate message. Conversation not fully initialized with a server-assigned ID.");
      return;
    }
    console.log('ChatService: Regenerating message (placeholder) - ID:', messageToRegenerate.id);
  }
}
