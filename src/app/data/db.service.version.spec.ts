import { TestBed } from '@angular/core/testing';
import { DBService } from './db.service';
import { Message } from './objects/message';
import { Conversation } from './objects/conversation';

describe('DBService - Version Management', () => {
  let service: DBService;

  beforeEach(async () => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(DBService);
    // The database is opened in the background
    await (service as any).status;
  });

  afterEach(async () => {
    await service.deleteConversationWithMessages('test-conv-1');
  });

  it('stores a message with the version it has: the server counts it, not the browser', async () => {
    const testMessage = Message.createText(
      {
        id: 1001,
        conversationId: 'test-conv-1',
        roleName: 'user',
        time: new Date(),
        version: 2
      },
      'Original content'
    );
    await service.saveMessage(testMessage);

    testMessage.content = { type: 'text', content: 'Updated content' };
    await service.saveMessage(testMessage);

    const stored = await service.getMessage(1001);
    expect(stored?.getDisplayContent()).toBe('Updated content');
    expect(stored?.version).toBe(2);
  });

  it('should increment conversation version on update', async () => {
    // Create test conversation
    const testConversation = new Conversation(
      'test-conv-1',
      1,
      'Test Conversation',
      ['user', 'assistant']
    );
    testConversation.version = 1;

    // Add conversation
    await service.addConversation(testConversation);

    // Update conversation
    testConversation.name = 'Updated Conversation';
    await service.updateConversation(testConversation);

    // Retrieve and verify
    const updatedConversation = await service.getConversation('test-conv-1');
    expect(updatedConversation?.version).toBe(2);
    expect(updatedConversation?.lastModified).toBeDefined();
  });
});