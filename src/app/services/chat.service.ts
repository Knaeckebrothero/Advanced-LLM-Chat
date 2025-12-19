// src/app/services/chat.service.ts
import { Injectable, OnDestroy } from '@angular/core';
import { Observable, firstValueFrom } from 'rxjs';
import { map } from 'rxjs/operators';
import { Message } from '../data/objects/message';
import { Conversation } from '../data/objects/conversation';
import { FilePreview } from '../data/objects/file-preview';
import { ChatStateService } from './chat-state.service';
import { UIStateService } from './ui-state.service';


@Injectable({
  providedIn: 'root'
})
export class ChatService implements OnDestroy {
  // Delegate to ChatStateService
  public messages: Observable<Message[]> = this.chatState.messages$;
  public conversations$: Observable<Conversation[]> = this.chatState.conversations$;
  public isNewConversation$ = this.chatState.state$.pipe(
    map(state => state.isNewConversation)
  );

  // Constructor
  constructor(
    private chatState: ChatStateService,
    private uiState: UIStateService
  ) {
    // ChatStateService handles initialization
  }


  // Public method for manual sync
  public async syncCurrentConversation() {
    await this.chatState.syncNow();
  }

  // Add getter to expose sync status
  public get isSyncing$(): Observable<boolean> {
    return this.chatState.isSyncing$;
  }



  // Send a message
  public async sendMessage(content: string, roleName: string = 'user'): Promise<void> {
    // ** THE FIX IS HERE **
    // Reverted to call the correct method in ChatStateService for text-only messages.
    await this.chatState.sendMessage(content, roleName);
  }

  // Send a file inside a message
  public async sendMessageWithFiles(
    content: string,
    files: FilePreview[],
    roleName: string = 'user'
  ): Promise<void> {
    await this.chatState.sendMessageWithFiles(content, files, roleName);
  }

  // Generate a message
  public async generateMessage(participant: string) {
    await this.chatState.generateMessage(participant);
  }

  // Patch a message in the conversation
  public async patchMessage(messageId: number, content: string) {
    await this.chatState.patchMessage(messageId, content);
  }

  // Delete a message from the conversation
  public async deleteMessage(messageId: number) {
    await this.chatState.deleteMessage(messageId);
  }

  // Regenerate a message in the conversation
  public async regenerateMessage(message: Message) {
    await this.chatState.regenerateMessage(message);
  }

  // Loads a specific conversation and its messages into memory.
  public async loadConversation(conversation: Conversation) {
    await this.chatState.loadConversation(conversation.id);
  }

  // Create a new conversation
  public async createConversation(conversation: Conversation): Promise<Conversation> {
    await this.chatState.createNewConversation();
    return conversation;
  }

  // Load all conversations from database
  public async loadAllConversations(): Promise<Conversation[]> {
    // Just return the current conversations from state
    return await firstValueFrom(this.conversations$) || [];
  }

  // Get conversations as observable
  public getConversations(): Observable<Conversation[]> {
    return this.chatState.conversations$;
  }

  // Update conversation (e.g., rename)
  public async updateConversation(conversation: Conversation): Promise<void> {
    await this.chatState.updateConversation(conversation);
  }

  // Delete conversation
  public async deleteConversation(conversationId: string): Promise<void> {
    await this.chatState.deleteConversation(conversationId);
  }



  // Clean up on service destroy
  ngOnDestroy(): void {
    // ChatStateService handles its own cleanup
  }
}
