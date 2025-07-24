import { TestBed } from '@angular/core/testing';
import { of, throwError, firstValueFrom } from 'rxjs';
import { ChatStateService } from './chat-state.service';
import { ConversationRepository } from '../repositories/conversation.repository';
import { MessageRepository } from '../repositories/message.repository';
import { ApiService } from './api.service';
import { SyncEngineService } from '../repositories/sync-engine.service';
import { Conversation } from '../data/objects/conversation';
import { Message } from '../data/objects/message';
import { FilePreview } from '../data/objects/file-preview';

describe('ChatStateService', () => {
  let service: ChatStateService;
  let mockConversationRepo: jasmine.SpyObj<ConversationRepository>;
  let mockMessageRepo: jasmine.SpyObj<MessageRepository>;
  let mockApiService: jasmine.SpyObj<ApiService>;
  let mockSyncEngine: jasmine.SpyObj<SyncEngineService>;

  const mockConversation = new Conversation('conv-123', 1, 'Test Conversation', ['user', 'assistant']);
  const mockMessages = [
    Message.createText({ id: 1, roleName: 'user', conversationId: 'conv-123', time: new Date() }, 'Hello'),
    Message.createText({ id: 2, roleName: 'assistant', conversationId: 'conv-123', time: new Date() }, 'Hi there!')
  ];

  beforeEach(() => {
    // Create mock services
    mockConversationRepo = jasmine.createSpyObj('ConversationRepository', 
      ['getAll', 'getById', 'save', 'delete']);
    mockMessageRepo = jasmine.createSpyObj('MessageRepository', 
      ['getByConversationId', 'save', 'delete', 'update', 'uploadPendingFiles']);
    mockApiService = jasmine.createSpyObj('ApiService', 
      ['checkConnection', 'generateMessage', 'uploadFiles', 'sendAndGenerateMessage']);
    mockSyncEngine = jasmine.createSpyObj('SyncEngineService', 
      ['syncNow']);

    // Set up default mock returns
    mockConversationRepo.getAll.and.returnValue(of([mockConversation]));
    mockConversationRepo.getById.and.returnValue(of(mockConversation));
    mockConversationRepo.save.and.returnValue(Promise.resolve(mockConversation));
    mockConversationRepo.delete.and.returnValue(Promise.resolve());
    
    mockMessageRepo.getByConversationId.and.returnValue(of(mockMessages));
    mockMessageRepo.save.and.returnValue(Promise.resolve(mockMessages[0]));
    mockMessageRepo.delete.and.returnValue(Promise.resolve());
    mockMessageRepo.update.and.returnValue(Promise.resolve(mockMessages[0]));
    mockMessageRepo.uploadPendingFiles.and.returnValue(Promise.resolve());
    
    mockApiService.checkConnection.and.returnValue(Promise.resolve(true));
    mockApiService.generateMessage.and.returnValue(Promise.resolve(mockMessages[1]));
    mockApiService.uploadFiles.and.returnValue(Promise.resolve(['https://example.com/file']));

    TestBed.configureTestingModule({
      providers: [
        ChatStateService,
        { provide: ConversationRepository, useValue: mockConversationRepo },
        { provide: MessageRepository, useValue: mockMessageRepo },
        { provide: ApiService, useValue: mockApiService },
        { provide: SyncEngineService, useValue: mockSyncEngine }
      ]
    });
    
    service = TestBed.inject(ChatStateService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  describe('Conversations', () => {
    it('should load conversations on init', (done) => {
      service.conversations$.subscribe(conversations => {
        expect(conversations).toEqual([mockConversation]);
        expect(mockConversationRepo.getAll).toHaveBeenCalled();
        done();
      });
    });

    it('should create new conversation', async () => {
      const newConv = await service.createNewConversation();
      expect(mockConversationRepo.save).toHaveBeenCalled();
      expect(newConv).toBeTruthy();
    });

    it('should delete conversation', async () => {
      await service.deleteConversation('conv-123');
      expect(mockConversationRepo.delete).toHaveBeenCalledWith('conv-123');
    });

    it('should update conversation', async () => {
      const updates = { title: 'Updated Title' };
      await service.updateConversation('conv-123', updates);
      expect(mockConversationRepo.save).toHaveBeenCalledWith(jasmine.objectContaining({
        id: 'conv-123'
        title: 'Updated Title'
      }));
    });
  });

  describe('Active Conversation', () => {
    it('should set active conversation', (done) => {
      service.setActiveConversation('conv-123');
      service.activeConversation$.subscribe(conv => {
        expect(conv).toEqual(mockConversation);
        expect(mockConversationRepo.getById).toHaveBeenCalledWith('conv-123');
        done();
      });
    });

    it('should handle null active conversation', (done) => {
      service.setActiveConversation(null);
      service.activeConversation$.subscribe(conv => {
        expect(conv?.id).toBe('new-chat');
        expect(conv?.name).toBe('New Chat');
        done();
      });
    });

    it('should load messages for active conversation', (done) => {
      service.setActiveConversation('conv-123');
      service.messages$.subscribe(messages => {
        expect(messages).toEqual(mockMessages);
        expect(mockMessageRepo.getByConversationId).toHaveBeenCalledWith('conv-123');
        done();
      });
    });
  });

  describe('Messages', () => {
    beforeEach(async () => {
      await service.loadConversation('conv-123');
    });

    it('should send text message', async () => {
      await service.sendMessage('Test message', 'user');
      expect(mockMessageRepo.save).toHaveBeenCalledWith(jasmine.objectContaining({
        content: jasmine.objectContaining({
          type: 'text',
          text: 'Test message'
        }),
        roleName: 'user',
        conversationId: 'conv-123'
      }));
    });

    it('should send message with files', async () => {
      const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
      const filePreview: FilePreview = {
        file: mockFile,
        name: 'test.txt',
        size: 4,
        mimeType: 'text/plain',
        url: 'data:text/plain;base64,dGVzdA=='
      };

      await service.sendMessageWithFiles('Test with file', [filePreview]);
      
      expect(mockMessageRepo.save).toHaveBeenCalledWith(jasmine.objectContaining({
        content: jasmine.objectContaining({
          type: 'text',
          text: 'Test with file',
          files: jasmine.arrayContaining([jasmine.objectContaining({
            name: 'test.txt',
            mimeType: 'text/plain'
          })])
        })
      }));
    });

    it('should send voice message', async () => {
      const mockBlob = new Blob(['audio'], { type: 'audio/webm' });
      await service.sendVoiceMessage(mockBlob, 5, 'audio/webm', 'Test transcript');
      
      expect(mockMessageRepo.save).toHaveBeenCalledWith(jasmine.objectContaining({
        content: jasmine.objectContaining({
          type: 'voice',
          duration: 5,
          mimeType: 'audio/webm',
          transcript: 'Test transcript'
        })
      }));
    });

    it('should generate AI message', async () => {
      await service.generateMessage('assistant');
      expect(mockApiService.generateMessage).toHaveBeenCalled();
    });

    it('should handle offline message generation', async () => {
      mockApiService.checkConnection.and.returnValue(Promise.resolve(false));
      
      await service.generateMessage('assistant');
      expect(mockMessageRepo.save).toHaveBeenCalledWith(jasmine.objectContaining({
        content: jasmine.objectContaining({
          type: 'text',
          text: 'I am currently offline. Please check your internet connection.'
        }),
        roleName: 'assistant'
      }));
    });

    it('should delete message', async () => {
      await service.deleteMessage(123);
      expect(mockMessageRepo.delete).toHaveBeenCalledWith(123);
    });

    it('should patch message', async () => {
      await service.patchMessage(123, 'Updated content');
      expect(mockMessageRepo.update).toHaveBeenCalledWith(jasmine.objectContaining({
        content: jasmine.objectContaining({
          text: 'Updated content'
        })
      }));
    });
  });

  describe('State Management', () => {
    it('should update loading state', (done) => {
      service.setActiveConversation('conv-123');
      // The loading state is set when operations are performed
      service.state$.subscribe(state => {
        expect(state.isLoading).toBeDefined();
        done();
      });
    });

    it('should handle errors gracefully', async () => {
      mockMessageRepo.save.and.returnValue(Promise.reject(new Error('Test error')));
      
      await service.sendMessage('Test').catch(() => {});
      
      service.state$.subscribe(state => {
        expect(state.error).toBe('Failed to send message');
      });
    });

    it('should clear errors', () => {
      service.clearError();
      service.state$.subscribe(state => {
        expect(state.error).toBeNull();
      });
    });
  });

  describe('Sync Operations', () => {
    it('should trigger sync after message operations', async () => {
      await service.sendMessage('Test');
      expect(mockSyncEngine.syncNow).toHaveBeenCalled();
    });

    it('should not sync for offline operations', async () => {
      mockApiService.checkConnection.and.returnValue(Promise.resolve(false));
      await service.generateMessage('assistant');
      expect(mockSyncEngine.syncNow).not.toHaveBeenCalled();
    });
  });

  describe('File Upload', () => {
    it('should handle pending file uploads', async () => {
      await service.uploadPendingFiles();
      expect(mockMessageRepo.uploadPendingFiles).toHaveBeenCalled();
    });
  });
});