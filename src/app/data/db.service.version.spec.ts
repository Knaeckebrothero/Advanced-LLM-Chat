import { TestBed } from '@angular/core/testing';
import { DBService } from './db.service';
import { IDBPDatabase } from 'idb';
import { Message } from './objects/message';
import { Conversation } from './objects/conversation';

describe('DBService - Version Management', () => {
  let service: DBService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(DBService);
  });

  it('should increment message version on update', async () => {
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

    // Add message
    await service.addMessage(testMessage);

    // Update message
    testMessage.content = { type: 'text', content: 'Updated content' };
    await service.updateMessage(testMessage);

    // Retrieve and verify
    const updatedMessage = await service.getMessage(1001);
    expect(updatedMessage?.version).toBe(2);
    expect(updatedMessage?.lastModified).toBeDefined();
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

  it('should handle version in transactional updates', async () => {
    // Create test conversation and messages
    const testConversation = new Conversation(
      'test-conv-1',
      1,
      'Test Conversation',
      ['user', 'assistant']
    );
    
    const testMessages = [
      Message.createText(
        {
          id: 1001,
          conversationId: 'test-conv-1',
          roleName: 'user',
          time: new Date(),
          version: 1
        },
        'Message 1'
      ),
      Message.createText(
        {
          id: 1002,
          conversationId: 'test-conv-1',
          roleName: 'assistant',
          time: new Date(),
          version: 1
        },
        'Message 2'
      )
    ];

    // Add initial data
    await service.addConversation(testConversation);
    for (const msg of testMessages) {
      await service.addMessage(msg);
    }

    // Update transactionally
    await service.updateConversationTransactional(
      testConversation,
      { messages: testMessages }
    );

    // Verify conversation version
    const updatedConv = await service.getConversation('test-conv-1');
    expect(updatedConv?.version).toBe(2);

    // Verify message versions
    const updatedMsg1 = await service.getMessage(1001);
    const updatedMsg2 = await service.getMessage(1002);
    expect(updatedMsg1?.version).toBe(2);
    expect(updatedMsg2?.version).toBe(2);
  });
});