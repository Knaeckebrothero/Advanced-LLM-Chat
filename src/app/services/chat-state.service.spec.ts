import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
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

  const mockConversation = new Conversation(1, 1, 'Test Conversation', ['user', 'assistant']);
  const mockMessages = [
    Message.createText('Hello', 'user', 1),
    Message.createText('Hi there!', 'assistant', 2)
  ];

  beforeEach(() => {
    // Create mock services
    mockConversationRepo = jasmine.createSpyObj('ConversationRepository', 
      ['getAll', 'getById', 'save', 'delete', 'create']);
    mockMessageRepo = jasmine.createSpyObj('MessageRepository', 
      ['getByConversation', 'save', 'delete', 'update', 'uploadPendingFiles']);
    mockApiService = jasmine.createSpyObj('ApiService', 
      ['isAvailable', 'generateMessage', 'uploadFile']);
    mockSyncEngine = jasmine.createSpyObj('SyncEngineService', 
      ['syncNow']);

    // Set up default mock returns
    mockConversationRepo.getAll.and.returnValue(of([mockConversation]));
    mockConversationRepo.getById.and.returnValue(of(mockConversation));
    mockConversationRepo.save.and.returnValue(Promise.resolve(mockConversation));
    mockConversationRepo.create.and.returnValue(Promise.resolve(mockConversation));
    mockConversationRepo.delete.and.returnValue(Promise.resolve());
    
    mockMessageRepo.getByConversation.and.returnValue(of(mockMessages));
    mockMessageRepo.save.and.returnValue(Promise.resolve(mockMessages[0]));
    mockMessageRepo.delete.and.returnValue(Promise.resolve());
    mockMessageRepo.update.and.returnValue(Promise.resolve(mockMessages[0]));
    mockMessageRepo.uploadPendingFiles.and.returnValue(Promise.resolve());
    
    mockApiService.isAvailable.and.returnValue(Promise.resolve(true));
    mockApiService.generateMessage.and.returnValue(Promise.resolve(mockMessages[1]));
    mockApiService.uploadFile.and.returnValue(Promise.resolve({ 
      id: 'file-123', 
      url: 'https://example.com/file' 
    }));

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
      const newConv = await service.createConversation();
      expect(mockConversationRepo.create).toHaveBeenCalledWith(jasmine.objectContaining({
        title: 'New Chat',
        participants: ['user', 'Assistant']
      }));
      expect(newConv).toEqual(mockConversation);
    });

    it('should delete conversation', async () => {
      await service.deleteConversation(1);
      expect(mockConversationRepo.delete).toHaveBeenCalledWith(1);
    });

    it('should update conversation', async () => {
      const updates = { title: 'Updated Title' };
      await service.updateConversation(1, updates);
      expect(mockConversationRepo.save).toHaveBeenCalledWith(jasmine.objectContaining({
        conversationId: 1,
        title: 'Updated Title'
      }));
    });
  });

  describe('Active Conversation', () => {
    it('should set active conversation', (done) => {
      service.setActiveConversation(1);
      service.activeConversation$.subscribe(conv => {
        expect(conv).toEqual(mockConversation);
        expect(mockConversationRepo.getById).toHaveBeenCalledWith(1);
        done();
      });
    });

    it('should handle null active conversation', (done) => {
      service.setActiveConversation(null);
      service.activeConversation$.subscribe(conv => {
        expect(conv?.conversationId).toBe(0);
        expect(conv?.title).toBe('New Chat');
        done();
      });
    });

    it('should load messages for active conversation', (done) => {
      service.setActiveConversation(1);
      service.messages$.subscribe(messages => {
        expect(messages).toEqual(mockMessages);
        expect(mockMessageRepo.getByConversation).toHaveBeenCalledWith(1);
        done();
      });
    });
  });

  describe('Messages', () => {
    beforeEach(() => {
      service.setActiveConversation(1);
    });

    it('should send text message', async () => {
      await service.sendMessage('Test message', 'user');
      expect(mockMessageRepo.save).toHaveBeenCalledWith(jasmine.objectContaining({
        content: jasmine.objectContaining({
          type: 'text',
          text: 'Test message'
        }),
        roleName: 'user',
        conversationId: 1
      }));
    });

    it('should send message with files', async () => {
      const mockFile = new File(['test'], 'test.txt', { type: 'text/plain' });
      const filePreview: FilePreview = {
        file: mockFile,
        name: 'test.txt',
        size: 4,
        mimeType: 'text/plain',
        dataUrl: 'data:text/plain;base64,dGVzdA=='
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
      expect(mockApiService.generateMessage).toHaveBeenCalledWith(1, 'assistant');
    });

    it('should handle offline message generation', async () => {
      mockApiService.isAvailable.and.returnValue(Promise.resolve(false));
      
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
      expect(mockMessageRepo.delete).toHaveBeenCalledWith(1, 123);
    });

    it('should patch message', async () => {
      await service.patchMessage(123, 'Updated content');
      expect(mockMessageRepo.update).toHaveBeenCalledWith(1, 123, jasmine.objectContaining({
        content: jasmine.objectContaining({
          text: 'Updated content'
        })
      }));
    });
  });

  describe('State Management', () => {
    it('should update loading state', (done) => {
      service.setActiveConversation(1);
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
      mockApiService.isAvailable.and.returnValue(Promise.resolve(false));
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