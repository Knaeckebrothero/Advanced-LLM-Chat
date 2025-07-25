import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { ChatStateService } from './chat-state.service';
import { ApiService } from './api.service';
import { NotificationService } from './notification.service';
import { Message } from '../data/objects/message';
import { of, throwError } from 'rxjs';

describe('ChatStateService - Conflict Resolution', () => {
  let service: ChatStateService;
  let apiService: jasmine.SpyObj<ApiService>;
  let notificationService: jasmine.SpyObj<NotificationService>;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    const apiServiceSpy = jasmine.createSpyObj('ApiService', ['patchMessage', 'updateConversation']);
    const notificationServiceSpy = jasmine.createSpyObj('NotificationService', ['showWarning', 'showError', 'showSuccess']);

    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [
        ChatStateService,
        { provide: ApiService, useValue: apiServiceSpy },
        { provide: NotificationService, useValue: notificationServiceSpy }
      ]
    });

    service = TestBed.inject(ChatStateService);
    apiService = TestBed.inject(ApiService) as jasmine.SpyObj<ApiService>;
    notificationService = TestBed.inject(NotificationService) as jasmine.SpyObj<NotificationService>;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  describe('patchMessage with version conflicts', () => {
    it('should retry on version conflict and succeed', async () => {
      // Create a test message
      const testMessage = Message.createText(
        {
          id: 1001,
          conversationId: 'test-conv-1',
          roleName: 'user',
          time: new Date(),
          version: 1
        },
        'Original content'
      );

      // Mock the message in the service
      spyOn(service.messages$, 'subscribe').and.returnValue(
        of([testMessage]).subscribe()
      );

      // First call fails with 409, second succeeds
      apiService.patchMessage
        .withArgs('test-conv-1', 1001, 'Updated content', 1)
        .and.returnValue(throwError({ status: 409 }));
      
      apiService.patchMessage
        .withArgs('test-conv-1', 1001, 'Updated content', 2)
        .and.returnValue(Promise.resolve(testMessage));

      // Mock sync engine to refresh message with new version
      const syncEngine = (service as any).syncEngine;
      spyOn(syncEngine, 'syncConversation').and.returnValue(Promise.resolve());

      // Execute
      await service.patchMessage(1001, 'Updated content');

      // Verify
      expect(apiService.patchMessage).toHaveBeenCalledTimes(2);
      expect(notificationService.showWarning).toHaveBeenCalledWith(
        'Version conflict detected. Refreshing and retrying... (Attempt 1/3)'
      );
      expect(notificationService.showSuccess).toHaveBeenCalledWith(
        'Message updated successfully after resolving conflicts'
      );
    });

    it('should fail after max retries', async () => {
      // Create a test message
      const testMessage = Message.createText(
        {
          id: 1001,
          conversationId: 'test-conv-1',
          roleName: 'user',
          time: new Date(),
          version: 1
        },
        'Original content'
      );

      // Mock the message in the service
      spyOn(service.messages$, 'subscribe').and.returnValue(
        of([testMessage]).subscribe()
      );

      // All calls fail with 409
      apiService.patchMessage.and.returnValue(
        throwError({ status: 409 })
      );

      // Mock sync engine
      const syncEngine = (service as any).syncEngine;
      spyOn(syncEngine, 'syncConversation').and.returnValue(Promise.resolve());

      // Execute and expect error
      await expectAsync(
        service.patchMessage(1001, 'Updated content', 2)
      ).toBeRejectedWithError('Unable to update message due to version conflicts. Please refresh and try again.');

      // Verify
      expect(apiService.patchMessage).toHaveBeenCalledTimes(2);
      expect(notificationService.showError).toHaveBeenCalledWith(
        'Unable to update message due to version conflicts. Please refresh and try again.'
      );
    });
  });

  describe('updateConversation with version conflicts', () => {
    it('should retry on version conflict and succeed', async () => {
      // Create test conversation
      const testConversation = {
        id: 'test-conv-1',
        name: 'Test Conversation',
        version: 1
      };

      // Mock active conversation
      spyOn(service.activeConversation$, 'subscribe').and.returnValue(
        of(testConversation).subscribe()
      );

      // First call fails with 409, second succeeds
      const conversationRepo = (service as any).conversationRepository;
      spyOn(conversationRepo, 'save')
        .and.returnValues(
          throwError({ status: 409 }),
          Promise.resolve()
        );

      // Mock sync engine
      const syncEngine = (service as any).syncEngine;
      spyOn(syncEngine, 'syncConversation').and.returnValue(Promise.resolve());

      // Execute
      await service.updateConversation(testConversation as any);

      // Verify
      expect(conversationRepo.save).toHaveBeenCalledTimes(2);
      expect(notificationService.showWarning).toHaveBeenCalledWith(
        'Version conflict detected. Refreshing and retrying... (Attempt 1/3)'
      );
      expect(notificationService.showSuccess).toHaveBeenCalledWith(
        'Conversation updated successfully after resolving conflicts'
      );
    });
  });
});