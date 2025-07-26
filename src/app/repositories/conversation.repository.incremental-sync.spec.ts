import { TestBed } from '@angular/core/testing';
import { ConversationRepository } from './conversation.repository';
import { DBService } from '../data/db.service';
import { ApiService } from '../services/api.service';
import { MessageRepository } from './message.repository';
import { Message } from '../data/objects/message';
import { Conversation } from '../data/objects/conversation';
import { ConversationSyncMetadata } from '../data/db-schema';
import { of } from 'rxjs';

describe('ConversationRepository - Incremental Sync', () => {
  let repository: ConversationRepository;
  let dbService: jasmine.SpyObj<DBService>;
  let apiService: jasmine.SpyObj<ApiService>;
  let messageRepository: jasmine.SpyObj<MessageRepository>;

  beforeEach(() => {
    const dbSpy = jasmine.createSpyObj('DBService', [
      'getAllConversations',
      'getConversation',
      'addConversation',
      'updateConversation',
      'getMessagesByConversationId',
      'backupConversationData',
      'restoreConversationData',
      'addMessagesTransactional',
      'replaceConversationMessages',
      'getSyncMetadata',
      'saveSyncMetadata',
      'getAllSyncMetadata',
      'deleteSyncMetadata'
    ]);
    
    const apiSpy = jasmine.createSpyObj('ApiService', [
      'getConversations',
      'getConversationMessages'
    ]);
    
    const messageRepoSpy = jasmine.createSpyObj('MessageRepository', [
      'refreshConversationCache'
    ]);

    TestBed.configureTestingModule({
      providers: [
        ConversationRepository,
        { provide: DBService, useValue: dbSpy },
        { provide: ApiService, useValue: apiSpy },
        { provide: MessageRepository, useValue: messageRepoSpy }
      ]
    });

    repository = TestBed.inject(ConversationRepository);
    dbService = TestBed.inject(DBService) as jasmine.SpyObj<DBService>;
    apiService = TestBed.inject(ApiService) as jasmine.SpyObj<ApiService>;
    messageRepository = TestBed.inject(MessageRepository) as jasmine.SpyObj<MessageRepository>;
    
    // Setup default return values
    dbService.getAllConversations.and.returnValue(Promise.resolve([]));
    dbService.getAllSyncMetadata.and.returnValue(Promise.resolve([]));
    dbService.updateConversation.and.returnValue(Promise.resolve('updated'));
    messageRepository.refreshConversationCache.and.returnValue(Promise.resolve());
  });

  describe('Incremental Sync', () => {
    it('should perform incremental sync when sync metadata exists', async () => {
      const conversationId = 'test-conv-123';
      const lastSyncTimestamp = Date.now() - 3600000; // 1 hour ago
      
      // Mock existing sync metadata
      const syncMetadata: ConversationSyncMetadata = {
        id: conversationId,
        lastSynced: new Date(lastSyncTimestamp),
        messageCount: 10,
        hash: 12345,
        lastSyncedTimestamp: Math.floor(lastSyncTimestamp / 1000),
        lastSyncedMessageId: 1000
      };
      
      // Mock conversation
      const conversation = new Conversation(
        conversationId,
        1,
        'Test Conversation',
        ['user', 'assistant']
      );
      
      // Mock existing messages
      const existingMessages = [
        Message.createText(
          { id: 1000, conversationId, roleName: 'user', time: new Date(lastSyncTimestamp - 1000) },
          'Old message'
        )
      ];
      
      // Mock new messages from server
      const newMessages = [
        Message.createText(
          { id: 1001, conversationId, roleName: 'assistant', time: new Date(lastSyncTimestamp + 1000) },
          'New message 1'
        ),
        Message.createText(
          { id: 1002, conversationId, roleName: 'user', time: new Date(lastSyncTimestamp + 2000) },
          'New message 2'
        )
      ];
      
      // Setup mocks
      dbService.backupConversationData.and.returnValue(Promise.resolve({
        conversation,
        messages: existingMessages
      }));
      dbService.getConversation.and.returnValue(Promise.resolve(conversation));
      dbService.getMessagesByConversationId.and.returnValue(Promise.resolve(existingMessages));
      dbService.getSyncMetadata.and.returnValue(Promise.resolve(syncMetadata));
      dbService.saveSyncMetadata.and.returnValue(Promise.resolve());
      dbService.addMessagesTransactional.and.returnValue(Promise.resolve());
      dbService.updateConversation.and.returnValue(Promise.resolve('updated'));
      
      apiService.getConversations.and.returnValue(Promise.resolve([
        Conversation.fromApiResponse({
          id: conversationId,
          userId: 1,
          name: 'Test Conversation',
          participants: ['user', 'assistant'],
          hashsum: 54321, // Different hash to trigger sync
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          version: 1,
          lastModified: Math.floor(Date.now() / 1000)
        })
      ]));
      
      apiService.getConversationMessages.and.returnValue(Promise.resolve({
        messages: newMessages,
        hasMoreMessages: false
      }));
      
      messageRepository.refreshConversationCache.and.returnValue(Promise.resolve());
      
      // Load sync metadata
      await (repository as any).loadSyncMetadata();
      (repository as any).syncMetadata.set(conversationId, syncMetadata);
      
      // Perform sync
      const result = await repository.syncConversation(conversationId);
      
      // Verify incremental sync was performed
      expect(result).toBe(true);
      expect(apiService.getConversationMessages).toHaveBeenCalledWith(
        conversationId,
        20,
        jasmine.any(Date),
        new Date(lastSyncTimestamp)
      );
      
      // Verify only new messages were added
      expect(dbService.addMessagesTransactional).toHaveBeenCalledWith(newMessages);
      expect(dbService.replaceConversationMessages).not.toHaveBeenCalled();
      
      // Verify sync metadata was updated
      expect(dbService.saveSyncMetadata).toHaveBeenCalledWith(jasmine.objectContaining({
        id: conversationId,
        lastSyncedMessageId: 1002,
        lastSyncedTimestamp: Math.floor(newMessages[1].time.getTime() / 1000)
      }));
    });

    it('should fall back to full sync when incremental sync fails', async () => {
      const conversationId = 'test-conv-123';
      const lastSyncTimestamp = Date.now() - 3600000;
      
      // Mock sync metadata
      const syncMetadata: ConversationSyncMetadata = {
        id: conversationId,
        lastSynced: new Date(lastSyncTimestamp),
        messageCount: 10,
        hash: 12345,
        lastSyncedTimestamp: Math.floor(lastSyncTimestamp / 1000),
        lastSyncedMessageId: 1000
      };
      
      // Mock conversation and messages
      const conversation = new Conversation(
        conversationId,
        1,
        'Test Conversation',
        ['user', 'assistant']
      );
      
      const existingMessages: Message[] = [];
      const serverMessages = [
        Message.createText(
          { id: 2000, conversationId, roleName: 'user', time: new Date() },
          'Server message'
        )
      ];
      
      // Setup mocks
      dbService.backupConversationData.and.returnValue(Promise.resolve({
        conversation,
        messages: existingMessages
      }));
      dbService.getConversation.and.returnValue(Promise.resolve(conversation));
      dbService.getMessagesByConversationId.and.returnValue(Promise.resolve(existingMessages));
      dbService.replaceConversationMessages.and.returnValue(Promise.resolve());
      dbService.updateConversation.and.returnValue(Promise.resolve('updated'));
      dbService.saveSyncMetadata.and.returnValue(Promise.resolve());
      
      apiService.getConversations.and.returnValue(Promise.resolve([
        Conversation.fromApiResponse({
          id: conversationId,
          userId: 1,
          name: 'Test Conversation',
          participants: ['user', 'assistant'],
          hashsum: 54321,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          version: 1,
          lastModified: Math.floor(Date.now() / 1000)
        })
      ]));
      
      // First call (incremental) fails, second call (full sync) succeeds
      apiService.getConversationMessages.and.returnValues(
        Promise.reject(new Error('Network error')),
        Promise.resolve({ messages: serverMessages, hasMoreMessages: false })
      );
      
      messageRepository.refreshConversationCache.and.returnValue(Promise.resolve());
      
      // Load sync metadata
      (repository as any).syncMetadata.set(conversationId, syncMetadata);
      
      // Perform sync
      const result = await repository.syncConversation(conversationId);
      
      // Verify fallback to full sync
      expect(result).toBe(true);
      expect(apiService.getConversationMessages).toHaveBeenCalledTimes(2);
      
      // First call was incremental
      expect(apiService.getConversationMessages.calls.argsFor(0)).toEqual([
        conversationId,
        20,
        jasmine.any(Date),
        new Date(lastSyncTimestamp)
      ]);
      
      // Second call was full sync (no afterTimestamp)
      expect(apiService.getConversationMessages.calls.argsFor(1)).toEqual([
        conversationId,
        20
      ]);
      
      // Verify full sync merge was used
      expect(dbService.replaceConversationMessages).toHaveBeenCalled();
    });

    it('should perform full sync when no sync metadata exists', async () => {
      const conversationId = 'new-conv-123';
      
      // Mock conversation and messages
      const conversation = new Conversation(
        conversationId,
        1,
        'New Conversation',
        ['user', 'assistant']
      );
      
      const serverMessages = [
        Message.createText(
          { id: 3000, conversationId, roleName: 'user', time: new Date() },
          'Message 1'
        ),
        Message.createText(
          { id: 3001, conversationId, roleName: 'assistant', time: new Date() },
          'Message 2'
        )
      ];
      
      // Setup mocks
      dbService.backupConversationData.and.returnValue(Promise.resolve({
        conversation,
        messages: []
      }));
      dbService.getConversation.and.returnValue(Promise.resolve(conversation));
      dbService.getMessagesByConversationId.and.returnValue(Promise.resolve([]));
      dbService.replaceConversationMessages.and.returnValue(Promise.resolve());
      dbService.updateConversation.and.returnValue(Promise.resolve('updated'));
      dbService.saveSyncMetadata.and.returnValue(Promise.resolve());
      dbService.saveSyncMetadata.and.returnValue(Promise.resolve());
      
      apiService.getConversations.and.returnValue(Promise.resolve([
        Conversation.fromApiResponse({
          id: conversationId,
          userId: 1,
          name: 'New Conversation',
          participants: ['user', 'assistant'],
          hashsum: 11111,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          version: 1,
          lastModified: Math.floor(Date.now() / 1000)
        })
      ]));
      
      apiService.getConversationMessages.and.returnValue(Promise.resolve({
        messages: serverMessages,
        hasMoreMessages: false
      }));
      
      messageRepository.refreshConversationCache.and.returnValue(Promise.resolve());
      
      // Perform sync
      const result = await repository.syncConversation(conversationId);
      
      // Verify full sync was performed
      expect(result).toBe(true);
      expect(apiService.getConversationMessages).toHaveBeenCalledWith(
        conversationId,
        20
      );
      
      // Verify full message replacement
      expect(dbService.replaceConversationMessages).toHaveBeenCalled();
      
      // Verify sync metadata was created
      expect(dbService.saveSyncMetadata).toHaveBeenCalledWith(jasmine.objectContaining({
        id: conversationId,
        lastSyncedMessageId: 3001,
        lastSyncedTimestamp: Math.floor(serverMessages[1].time.getTime() / 1000)
      }));
    });
  });
});