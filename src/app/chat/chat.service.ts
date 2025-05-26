import {Injectable} from '@angular/core';
import {BehaviorSubject, Observable} from 'rxjs';
import {Message, MessageData} from '../data/objects/message';
import {DBService} from '../data/db.service';
import {ApiService} from '../api/api.service';
import {Conversation} from '../data/objects/conversation'; // Assuming ConversationDTO is not used directly here but Conversation class itself
import {User} from '../data/objects/user';

@Injectable({
  providedIn: 'root'
})
export class ChatService {
  private conversation!: Conversation; // Definite assignment assertion
  private currentUser: User | null = null;

  private messagesSubject = new BehaviorSubject<Message[]>([]);
  public messages$: Observable<Message[]> = this.messagesSubject.asObservable();

  private currentConversationSubject = new BehaviorSubject<Conversation | null>(null);
  public currentConversation$: Observable<Conversation | null> = this.currentConversationSubject.asObservable();

  constructor(
    private dbService: DBService,
    private apiService: ApiService
  ) {
    this.initializeChat();
  }

  private async initializeChat(): Promise<void> {
    console.log("ChatService: Initializing...");
    await this.dbService.getDatabaseReadyPromise(); // Ensure DB is ready
    this.currentUser = await this.dbService.getCurrentUser();

    if (this.currentUser) {
      console.log("ChatService: Current user loaded -", this.currentUser.name, `(ID: ${this.currentUser.id})`);
      await this.loadOrCreateConversationForUser(this.currentUser);
    } else {
      console.error("ChatService: CRITICAL - No current user found after DB init. Chat functionality will be limited.");
      this.currentConversationSubject.next(null); // No active conversation
      // Fallback for guest/default user if necessary:
      // this.conversation = new Conversation(SOME_DEFAULT_ID, 0, "Guest Chat", ["user", "Assistant"]);
      // await this.dbService.addConversation(this.conversation); // If guest convos are persisted
      // this.currentConversationSubject.next(this.conversation);
      // await this.loadMessagesForCurrentConversation(); // Load messages for guest
    }
  }

  private async loadOrCreateConversationForUser(user: User): Promise<void> {
    const userConversations = await this.dbService.getConversationsByUserId(user.id);
    if (userConversations && userConversations.length > 0) {
      this.conversation = userConversations[0]; // Load the first available conversation
      console.log("ChatService: Loaded existing conversation:", this.conversation.name, `(ID: ${this.conversation.id})`);
    } else {
      // Create a new Conversation object in memory. ID is null.
      // It will be saved to DBService only after the backend confirms its creation (via the first sendMessage).
      this.conversation = new Conversation(
        null, // ID is null for a new, unsaved conversation
        user.id,
        `Chat with ${user.name}`, // Default name
        ["user", "Assistant"]    // Default participants
      );
      console.log("ChatService: Initialized new in-memory conversation (not yet saved to DB/Backend):", this.conversation.name);
      // DO NOT add to dbService here. It will be added after the first message send and backend confirmation.
    }
    this.currentConversationSubject.next(this.conversation);

    if (this.conversation && this.conversation.id !== null) {
      await this.loadMessagesForCurrentConversation();
      this.refreshConversationFromServer(); // Check for updates from server
    } else if (this.conversation && this.conversation.id === null) {
      // For a new conversation (id is null), there are no messages to load yet.
      this.messagesSubject.next([]);
      console.log("ChatService: New conversation instance created. Messages will load/populate after the first successful send.");
    }
  }

  private async loadMessagesForCurrentConversation(): Promise<void> {
    // This method should only be called if conversation.id is NOT null.
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
      const remoteConversations = await this.apiService.getConversationsByUser(this.currentUser.id, this.currentUser.accessToken);
      const remoteCurrentConversationData = remoteConversations.find(c => c.id === this.conversation.id);

      if (!remoteCurrentConversationData) {
        console.log('ChatService: Current local conversation (ID:', this.conversation.id, ') not found on server during refresh.');
        return;
      }

      // remoteCurrentConversationData is already a Conversation instance if ApiService.getConversationsByUser maps it.
      // If it returns plain objects, then instantiation is needed here. Assuming it's Conversation instance.
      const remoteCurrentConversation = remoteCurrentConversationData;

      const localHashsum = await this.conversation.computeHash(this.dbService);

      // Ensure remoteCurrentConversation.hashsum is available (it should be if API provides it)
      if (remoteCurrentConversation.hashsum !== undefined && localHashsum !== remoteCurrentConversation.hashsum) {
        console.log('ChatService: Conversation hashes mismatch! Local:', localHashsum, 'Remote:', remoteCurrentConversation.hashsum, ". Refreshing messages.");

        const messagesFromServer = await this.apiService.getConversationMessages(remoteCurrentConversation.id!, 50, this.currentUser.accessToken);

        await this.dbService.deleteMessagesByConversationId(this.conversation.id!); // id is not null here
        this.messagesSubject.next([]); // Clear UI

        this.addMessagesToLocalStoreAndSubject(messagesFromServer, this.conversation.id!); // id is not null

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
    targetConversationId: number // Expecting a non-null ID once messages are being formally added
  ): void {
    // Note: targetConversationId is now number, implying it's for an existing/confirmed conversation.
    const messagesToAddArray = Array.isArray(messageOrMessages) ? messageOrMessages : [messageOrMessages];
    if (messagesToAddArray.length === 0) return;

    const processedMessages: Message[] = messagesToAddArray.map(msgDataOrInstance => {
      const msg = msgDataOrInstance instanceof Message ? msgDataOrInstance : Message.fromApiResponse(msgDataOrInstance as MessageData);
      msg.conversationId = targetConversationId; // Explicitly set/confirm conversationId
      return msg;
    });

    const currentMessages = this.messagesSubject.getValue();
    // Filter out duplicates more reliably
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

    // Message.conversationId will be null if this.conversation.id is null (new conversation)
    const message = new Message({
      id: tempMessageId,
      conversationId: this.conversation.id, // Can be null for a new conversation
      roleName: roleName === 'user' ? this.currentUser.name : roleName,
      content: content,
      time: messageTime
    });

    // Optimistic UI update
    const currentUIMessages = this.messagesSubject.getValue();
    this.messagesSubject.next([...currentUIMessages, message].sort((a, b) => (a.time?.getTime() || 0) - (b.time?.getTime() || 0)));

    try {
      const {confirmedMessage, newConversation} = await this.apiService.sendMessage(
        message,
        this.conversation, // Pass the current conversation object (which might have id: null)
        this.currentUser.accessToken
      );
      console.log('ChatService: Message sent. Confirmed Msg ID:', confirmedMessage.id, "New Conv ID:", confirmedMessage.conversationId);

      // If a new conversation was created by the backend
      if (newConversation && this.conversation.id === null) {
        console.log('ChatService: New conversation confirmed by backend. Updating local conversation ID from null to', newConversation.id);

        this.conversation.id = newConversation.id;
        this.conversation.name = newConversation.name;
        this.conversation.participants = newConversation.participants;
        this.conversation.hashsum = newConversation.hashsum;

        // IMPORTANT: Save the newly confirmed conversation to local DB
        await this.dbService.addConversation(this.conversation);
        this.currentConversationSubject.next(this.conversation); // Notify observers

        // The confirmedMessage from API will have the correct new conversationId.
        // The temporary message had `conversationId: null` if it was a new convo.
      }

      // Remove the temporary message from UI
      const finalMessagesAfterTempRemoval = this.messagesSubject.getValue().filter(m => m.id !== tempMessageId);
      this.messagesSubject.next(finalMessagesAfterTempRemoval);

      // Attempt to delete temporary message from DB if it was saved under a different (temporary) ID context
      // This delete is mainly for client-side only temp messages that should not persist.
      // Given our flow, the temp message with null conversationId wouldn't have a specific DB entry
      // to delete by its tempMessageId if DB constraints prevent messages with null convId.
      // If it *was* added optimistically to DB with a temp convId, then delete.
      // For now, assume it was UI only or DB handled its temporary nature.
      // If dbService.addMessage handles null conversationId by not saving, this delete is fine.
      // If Message.id is unique, this is okay.
      try {
        await this.dbService.deleteMessage(tempMessageId);
      } catch (dbError) {
        console.warn("ChatService: Could not delete temporary message from DB; it might not have been added or already processed:", dbError);
      }

      // Add the server-confirmed message which has the correct ID and conversationId
      this.addMessagesToLocalStoreAndSubject(confirmedMessage, confirmedMessage.conversationId!); // confirmedMessage.conversationId should not be null here

    } catch (error) {
      console.error('ChatService: Error sending message via API:', error);
      // Revert optimistic UI update on failure
      const revertedMessages = this.messagesSubject.getValue().filter(m => m.id !== tempMessageId);
      this.messagesSubject.next(revertedMessages);
      // TODO: Provide more specific UI feedback for the failed message (e.g., mark as "failed to send")
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
      // You could potentially allow AI to send the first message if logic supports it.
      // For example, by sending a different request to ApiService or a default initial prompt.
      return;
    }

    const lastMessage = currentMessages[currentMessages.length - 1];
    console.log(`ChatService: Generating AI message for ${participantName} based on last message: "${lastMessage.content}"`);

    try {
      const generatedMessage = await this.apiService.generateMessage(lastMessage, participantName, this.currentUser.accessToken);
      // generatedMessage.conversationId should match this.conversation.id!
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
      // Pass conversation.id! as it's confirmed not null by the guard
      const updatedMessage = await this.apiService.patchMessage(this.conversation.id!, messageId, newContent, this.currentUser.accessToken);

      const currentMessages = this.messagesSubject.getValue();
      const messageIndex = currentMessages.findIndex(msg => msg.id === messageId && msg.conversationId === this.conversation.id);

      if (messageIndex !== -1) {
        currentMessages[messageIndex] = updatedMessage; // ApiService should return a Message instance
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
      // Pass conversation.id! as it's confirmed not null
      await this.apiService.deleteMessage(this.conversation.id!, messageId, this.currentUser.accessToken);

      const updatedMessages = this.messagesSubject.getValue().filter(msg => !(msg.id === messageId && msg.conversationId === this.conversation.id));
      this.messagesSubject.next(updatedMessages);
      await this.dbService.deleteMessage(messageId); // Assuming messageId is globally unique or DBService handles context
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
    // Placeholder: Actual implementation would involve:
    // 1. Identifying context (messages before messageToRegenerate).
    // 2. Calling an API endpoint (potentially a modified generateMessage or a specific regenerate endpoint).
    // 3. Handling the response: replacing messageToRegenerate or appending a new AI message.
    console.log('ChatService: Regenerating message (placeholder) - ID:', messageToRegenerate.id);
    // Example:
    // const messages = this.messagesSubject.getValue();
    // const index = messages.findIndex(m => m.id === messageToRegenerate.id);
    // if (index > 0) {
    //   const contextMessage = messages[index -1];
    //   // await this.apiService.regenerateBasedOn(contextMessage, messageToRegenerate, this.currentUser.accessToken);
    // } else if (index === 0) {
    //   // Regenerate first message - special handling or disallow
    // }
  }
}
