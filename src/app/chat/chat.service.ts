import { Injectable } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { Message } from '../data/objects/message';
import { DBService } from '../data/db.service';
import { ApiService } from '../api/api.service';
import { Conversation } from '../data/objects/conversation';
import { User } from '../data/objects/user'; // Import User

@Injectable({
  providedIn: 'root'
})
export class ChatService {
  // The conversation this service is managing. Will be initialized after user context.
  private conversation!: Conversation; // Using definite assignment assertion
  private currentUser: User | null = null; // To store the current user from DBService

  private messagesSubject: BehaviorSubject<Message[]> = new BehaviorSubject<Message[]>([]);
  public messages: Observable<Message[]> = this.messagesSubject.asObservable();

  constructor(
    private dbService: DBService,
    private apiService: ApiService
  ) {
    this.dbService.getDatabaseReadyPromise().then(async () => {
      this.currentUser = await this.dbService.getCurrentUser();

      if (this.currentUser) {
        console.log("ChatService: Current user loaded -", this.currentUser.name, `(ID: ${this.currentUser.id}, Token: ${this.currentUser.accessToken})`, "");
        // Attempt to load or create conversation based on the current user
        let userConversations = await this.dbService.getConversationsByUserId(this.currentUser.id);
        if (userConversations && userConversations.length > 0) {
          this.conversation = userConversations[0]; // Load the first conversation for this user
          console.log("ChatService: Loaded existing conversation for user:", this.conversation.name, `(ID: ${this.conversation.id})`, "");
        } else {
          // Create a new default conversation for this user
          // Ensure conversation ID is unique; using Date.now() or a proper UUID generator is better for production
          // For now, let's make it related to user ID if it's for a new conversation
          const newConversationId = Date.now(); // Example for a new conversation ID
          this.conversation = new Conversation(
            newConversationId,
            this.currentUser.id,
            `Chat for ${this.currentUser.name}`,
            ["user", "Assistant"] // Default participants
          );
          await this.dbService.addConversation(this.conversation);
          console.log("ChatService: Created new conversation for user:", this.conversation.name, `(ID: ${this.conversation.id})`, "");
        }
      } else {
        // This case should ideally not happen if DBService.initializeDefaultState ensures a user.
        console.error("ChatService: CRITICAL - No current user found after DB init. Defaulting to a guest setup.");
        // Fallback to a predefined guest/default conversation if no user from DBService
        // This ensures `this.conversation` is always initialized.
        this.conversation = new Conversation(
          1, // Default/Guest conversation ID
          0, // Default/Guest user ID
          "Default Chat", // Name
          ["user", "Assistant"]
        );
        // Optionally add this to DB if guest conversations should be persisted
        // const existingGuestConv = await this.dbService.getConversation(this.conversation.id);
        // if (!existingGuestConv) await this.dbService.addConversation(this.conversation);
      }

      // Load messages for the determined conversation
      if (this.conversation && typeof this.conversation.id !== 'undefined') {
        const messages = await this.dbService.getMessagesByConversationId(this.conversation.id);
        if (messages && messages.length > 0) {
          messages.sort((a, b) => a.time!.getTime()! - b.time!.getTime());
          this.messagesSubject.next([...messages]);
        }
        console.log("ChatService: Conversation messages loaded/initialized for:", this.conversation.name, "");

        // Initial refresh if user and conversation are set
        if (this.currentUser && this.conversation) {
          this.refreshConversation();
        }
      } else {
        console.error("ChatService: Conversation object is not properly initialized. Cannot load messages.");
      }
    });
  }

  private async refreshConversation() {
    if (!this.currentUser || !this.conversation || typeof this.conversation.id === 'undefined') {
      console.log('Refresh aborted: User or conversation not properly initialized for refresh.', "");
      return;
    }

    try {
      // Pass current user's ID and accessToken
      const remoteConversations = await this.apiService.getConversationsByUser(this.currentUser.id, this.currentUser.accessToken);

      const remoteCurrentConversation = remoteConversations.find(c => c.id === this.conversation.id);

      if (!remoteCurrentConversation) {
        console.log('Current local conversation not found on server during refresh.', "");
        // Potentially create/sync this conversation on the server if it's new.
        return;
      }

      // Ensure local this.conversation is up-to-date before hash computation if necessary
      // For example, if participants can change and are part of the hash.
      // Here, we assume this.conversation reflects the state needed for a valid local hash.
      const localHashsum = await this.conversation.computeHash(this.dbService);

      if (localHashsum !== remoteCurrentConversation.hashsum) {
        console.log('Conversation hashes mismatch! Local:', localHashsum, 'Remote:', remoteCurrentConversation.hashsum, ". Refreshing messages.", "");

        // Pass accessToken for getting messages
        const messagesFromServer = await this.apiService.getConversationMessages(remoteCurrentConversation.id, 20, this.currentUser.accessToken);

        console.log('Deleting old local messages for conversation ID:', this.conversation.id, "");
        await this.dbService.deleteMessagesByConversationId(this.conversation.id);
        this.messagesSubject.next([]); // Clear UI

        console.log('Adding messages from server to conversation:', messagesFromServer.length, "messages.", "");
        this.addMessage(messagesFromServer); // This adds to DB and updates BehaviorSubject

        this.conversation.hashsum = remoteCurrentConversation.hashsum; // Update local hashsum
        await this.dbService.updateConversation(this.conversation);
      } else {
        console.log('Conversation hashes match. No server message refresh needed for conversation ID:', this.conversation.id, "");
      }
    } catch (error) {
      console.error('Error refreshing conversation:', error, "");
    }
  }


  private addMessage(messageOrMessages: Message | Message[]) {
    if (!this.conversation || typeof this.conversation.id === 'undefined') {
      console.error("Cannot add message: Conversation not initialized properly.");
      return;
    }

    const messagesToAddArray = Array.isArray(messageOrMessages) ? messageOrMessages : [messageOrMessages];

    const processedMessages = messagesToAddArray.map(msgData => {
      const msg = msgData instanceof Message ? msgData : new Message(msgData);
      msg.conversationId = this.conversation.id; // Ensure conversationId is set
      return msg;
    });

    processedMessages.sort((a, b) => a.time!.getTime()! - b.time!.getTime());

    const currentMessages = this.messagesSubject.getValue();
    // Filter out duplicates by ID before adding to BehaviorSubject
    const uniqueNewMessages = processedMessages.filter(nm => !currentMessages.some(cm => cm.id === nm.id));

    if (uniqueNewMessages.length > 0) {
      this.messagesSubject.next([...currentMessages, ...uniqueNewMessages]);
      uniqueNewMessages.forEach(async (msg) => {
        try {
          await this.dbService.addMessage(msg);
        } catch (error) {
          console.error("Error adding message to DB (ID: " + msg.id + "):", error, "");
          // Optionally, if it's a constraint error (already exists), try updating
          // if (error.name === 'ConstraintError') { await this.dbService.updateMessage(msg); }
        }
      });
    }
  }

  public async sendMessage(content: string, roleName: string = 'user') {
    if (!this.currentUser || !this.conversation || typeof this.conversation.id === 'undefined') {
      console.error("Cannot send message: User or conversation not properly initialized.");
      return;
    }

    const message = new Message({
      id: Math.floor(Date.now() / 1000), // Temporary client-side ID
      conversationId: this.conversation.id,
      roleName: roleName === 'user' ? this.currentUser.name : roleName, // Use current user's name for 'user' role
      content: content,
      time: new Date()
    });

    this.addMessage(message); // Optimistic update

    try {
      // Pass accessToken
      const sentMessageConfirmation = await this.apiService.sendMessage(message, this.currentUser.accessToken);
      console.log('Message sent to API, confirmation:', sentMessageConfirmation, "");

      if (message.id !== sentMessageConfirmation.id) {
        console.log('Message ID mismatch from API, updating local message ID:', message.id, '->', sentMessageConfirmation.id, "");

        const currentLocalMessages = this.messagesSubject.getValue();
        const msgIndex = currentLocalMessages.findIndex(m => m.id === message.id);

        await this.dbService.deleteMessage(message.id); // Remove old temp message from DB

        // Replace message in BehaviorSubject or add new one and remove old
        if (msgIndex > -1) {
          currentLocalMessages.splice(msgIndex, 1); // Remove old message
        }
        this.messagesSubject.next([...currentLocalMessages]); // Update subject without old message
        this.addMessage(sentMessageConfirmation); // Add confirmed message which also saves to DB

      } else {
        // If ID is the same, message in DB might need an update if API returns more fields
        await this.dbService.updateMessage(sentMessageConfirmation); // Ensure DB has the server-confirmed version
        // Update in behaviorsubject as well
        const currentLocalMessages = this.messagesSubject.getValue();
        const msgIndex = currentLocalMessages.findIndex(m => m.id === sentMessageConfirmation.id);
        if (msgIndex > -1) {
          currentLocalMessages[msgIndex] = sentMessageConfirmation;
          this.messagesSubject.next([...currentLocalMessages]);
        }
      }
    } catch (error) {
      console.error('Error sending message via API:', error, "");
      // TODO: Implement UI feedback for failed send (e.g., mark message, offer retry)
    }
  }

  public async generateMessage(participant: string) {
    if (!this.currentUser || !this.conversation || typeof this.conversation.id === 'undefined') {
      console.error("Cannot generate message: User or conversation not properly initialized.");
      return;
    }

    const currentMessages = this.messagesSubject.getValue();
    if (currentMessages.length === 0) {
      console.warn("Cannot generate message: No previous messages in conversation.", "");
      return;
    }

    const lastMessageData = currentMessages[currentMessages.length - 1];
    const lastMessage = lastMessageData instanceof Message ? lastMessageData : new Message(lastMessageData);

    console.log('Generating message based on:', lastMessage, "for participant:", participant, "");

    try {
      // Pass accessToken
      const generatedMessage = await this.apiService.generateMessage(lastMessage, participant, this.currentUser.accessToken);
      this.addMessage(generatedMessage);
      console.log("Generated message added:", generatedMessage, "");
    } catch (error) {
      console.error('Error generating message via API:', error, "");
    }
  }

  public async patchMessage(messageId: number, content: string) {
    if (!this.currentUser || !this.conversation || typeof this.conversation.id === 'undefined') {
      console.error("Cannot patch message: User or conversation not properly initialized.");
      return;
    }
    try {
      const conversationId = this.conversation.id;
      // Pass accessToken
      const updatedMessageFromServer = await this.apiService.patchMessage(conversationId, messageId, content, this.currentUser.accessToken);

      const currentMessages = this.messagesSubject.getValue();
      const messageIndex = currentMessages.findIndex(msg => msg.id === messageId);

      if (messageIndex !== -1) {
        const fullyUpdatedMessage = Message.fromApiResponse(updatedMessageFromServer as any);
        currentMessages[messageIndex] = fullyUpdatedMessage;
        this.messagesSubject.next([...currentMessages]);
        await this.dbService.updateMessage(fullyUpdatedMessage);
        console.log("Message patched successfully:", fullyUpdatedMessage, "");
      }
    } catch (error) {
      console.error('Error patching message via API:', error, "");
    }
  }

  public async deleteMessage(messageId: number) {
    if (!this.currentUser || !this.conversation || typeof this.conversation.id === 'undefined') {
      console.error("Cannot delete message: User or conversation not properly initialized.");
      return;
    }
    try {
      // Pass accessToken
      await this.apiService.deleteMessage(this.conversation.id, messageId, this.currentUser.accessToken);

      const currentMessages = this.messagesSubject.getValue();
      const updatedMessages = currentMessages.filter(msg => msg.id !== messageId);
      this.messagesSubject.next(updatedMessages);
      await this.dbService.deleteMessage(messageId);
      console.log("Message deleted successfully, ID:", messageId, "");
    } catch (error) {
      console.error('Error deleting message via API:', error, "");
    }
  }

  public regenerateMessage(message: Message) {
    // Implementation depends on how regeneration is handled by the backend or logic
    console.log('Regenerating message - placeholder. ID:', message.id, "");
    // Example: You might delete the message and call generateMessage based on the context before it.
    // Or, if an API endpoint exists:
    // if (this.currentUser) {
    //   this.apiService.regenerateApiMessage(message.id, this.currentUser.accessToken).then(...);
    // }
  }
}
