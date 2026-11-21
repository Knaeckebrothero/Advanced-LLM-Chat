import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';
import { ConversationRepository, mergeServerMessage, removedOnServer } from './conversation.repository';
import { MessageRepository } from './message.repository';
import { DBService } from '../data/db.service';
import { ApiService } from '../services/api.service';
import { Message } from '../data/objects/message';
import { Conversation } from '../data/objects/conversation';
import { UploadStatus } from '../data/models/file.model';

/**
 * The sync of a conversation's messages: the browser asks for the server's newest messages and
 * merges them by id. Against the real IndexedDB of the test browser, with the server played by
 * a list of messages.
 */
describe('ConversationRepository - sync of messages', () => {
  let repository: ConversationRepository;
  let messageRepository: MessageRepository;
  let dbService: DBService;
  let conversationId: string;
  /** What the server has: the conversation's messages as the API sends them. */
  let server: any[];
  /** Runs while the request for the messages is on its way. */
  let duringRequest: () => Promise<void>;
  let messageRequests: Array<{ count: number; beforeId?: number }>;

  // Ids are the server's clock in milliseconds: a message, and its answer 121 ms later, in the
  // same second
  const T = 1794741599;
  const USER = T * 1000 + 458;
  const ANSWER = T * 1000 + 579;

  const text = (id: number, content: string, extra: object = {}) => ({
    id, conversationId, roleName: 'user', content, time: Math.floor(id / 1000), type: 'text', version: 1, ...extra
  });
  const answer = (id: number, content: string, extra: object = {}) => ({
    id, conversationId, roleName: 'Assistant', content, finalResponse: content, time: Math.floor(id / 1000),
    type: 'agent', version: 1, steps: [], status: 'complete', error: null, modelId: 4, modelName: 'Model',
    usage: { outputTokens: 5, inputTokens: 10 }, ...extra
  });

  const localMessages = async () =>
    (await dbService.getMessagesByConversationId(conversationId)).sort(Message.compare);
  const localIds = async () => (await localMessages()).map(m => m.id);

  beforeEach(async () => {
    conversationId = `sync-test-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    server = [];
    duringRequest = async () => {};
    messageRequests = [];

    const api = {
      getConversations: async () => [Conversation.fromApiResponse({
        id: conversationId, userId: 1, name: 'Sync test', participants: ['user', 'Assistant'],
        createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), version: 1
      })],
      // As the server does: the newest by id, oldest first, or the page before a message
      getConversationMessages: async (_id: string, count: number, beforeId?: number) => {
        messageRequests.push({ count, beforeId });
        const response = server
          .filter(m => beforeId === undefined || m.id < beforeId)
          .sort((a, b) => a.id - b.id)
          .slice(-count)
          .map(m => Message.fromApiResponse(JSON.parse(JSON.stringify(m))));
        await duringRequest();
        return response;
      }
    };

    TestBed.configureTestingModule({ providers: [{ provide: ApiService, useValue: api }] });
    dbService = TestBed.inject(DBService);
    await (dbService as any).status;
    messageRepository = TestBed.inject(MessageRepository);
    repository = TestBed.inject(ConversationRepository);
  });

  afterEach(async () => {
    await dbService.deleteConversationWithMessages(conversationId);
    await dbService.deleteSyncMetadata(conversationId);
  });

  it('gets an answer that was stored after a sync, though it shares its second with its message', async () => {
    // Another device sent a message, its answer is still being written
    server = [text(USER, 'Hello')];
    expect(await repository.syncConversation(conversationId)).toBe(true);
    expect(await localIds()).toEqual([USER]);

    // The answer is stored with the time its generation started at: not later than the message
    server.push(answer(ANSWER, 'Hi there'));
    expect(server[1].time).toBe(server[0].time);
    expect(await repository.syncConversation(conversationId)).toBe(true);

    expect(await localIds()).toEqual([USER, ANSWER]);
    expect((await localMessages())[1].getDisplayContent()).toBe('Hi there');
    // It asks for the newest messages, with no time of its own clock
    expect(messageRequests).toEqual([{ count: 20, beforeId: undefined }, { count: 20, beforeId: undefined }]);
  });

  it('gets an answer in the middle that an older version of the sync missed', async () => {
    const later = USER + 60000;
    await dbService.saveMessage(Message.fromApiResponse(text(USER, 'Hello')));
    await dbService.saveMessage(Message.fromApiResponse(text(later, 'Still there?')));
    server = [text(USER, 'Hello'), answer(ANSWER, 'Hi there'), text(later, 'Still there?')];

    expect(await repository.syncConversation(conversationId)).toBe(true);
    expect(await localIds()).toEqual([USER, ANSWER, later]);
  });

  it('writes nothing and leaves the chat alone when the server has what the browser has', async () => {
    // The browser's copies: its own message and the answer it streamed (keys in another order)
    await dbService.saveMessage(Message.createText(
      { id: USER, conversationId, roleName: 'user', time: new Date(T * 1000) }, 'Hello'));
    const streamed = Message.createAgent(conversationId, [], 'Hi there', 'complete');
    streamed.id = ANSWER;
    streamed.time = new Date(T * 1000);
    streamed.roleName = 'Assistant';
    streamed.content.modelId = 4;
    streamed.content.modelName = 'Model';
    streamed.content.usage = { inputTokens: 10, outputTokens: 5 } as any;
    await dbService.saveMessage(streamed);
    server = [text(USER, 'Hello'), answer(ANSWER, 'Hi there')];

    const refresh = spyOn(messageRepository, 'refreshConversationCache').and.callThrough();
    const write = spyOn(dbService, 'applyServerMessages').and.callThrough();
    expect(await repository.syncConversation(conversationId)).toBe(false);
    expect(await repository.syncConversation(conversationId)).toBe(false);
    expect(write).toHaveBeenCalledTimes(2);
    expect(refresh).not.toHaveBeenCalled();
  });

  it('takes a message another device edited or rated', async () => {
    server = [text(USER, 'Hello'), answer(ANSWER, 'Hi there')];
    await repository.syncConversation(conversationId);

    server[0] = text(USER, 'Hello again', { version: 2 });
    server[1] = answer(ANSWER, 'Hi there', { rating: 1 });
    expect(await repository.syncConversation(conversationId)).toBe(true);

    const [message, reply] = await localMessages();
    expect(message.getDisplayContent()).toBe('Hello again');
    expect(message.version).toBe(2);
    expect(reply.rating).toBe(1);
  });

  it('takes another version of an answer that another device regenerated or switched to', async () => {
    server = [text(USER, 'Hello'), answer(ANSWER, 'Hi there')];
    await repository.syncConversation(conversationId);

    // Regenerated: the answer keeps its id, says something else and has two versions
    server[1] = answer(ANSWER, 'Hello you', { version: 2, alternativePosition: 2, alternativeCount: 2 });
    expect(await repository.syncConversation(conversationId)).toBe(true);
    let reply = (await localMessages())[1];
    expect(reply.getDisplayContent()).toBe('Hello you');
    expect(reply.version).toBe(2);
    expect(reply.alternatives).toEqual({ position: 2, count: 2 });

    // A third version that another device keeps while it shows the second: only the versions changed
    server[1] = answer(ANSWER, 'Hello you', { version: 3, alternativePosition: 2, alternativeCount: 3 });
    expect(await repository.syncConversation(conversationId)).toBe(true);
    reply = (await localMessages())[1];
    expect(reply.alternatives).toEqual({ position: 2, count: 3 });

    // The same again: nothing to write
    expect(await repository.syncConversation(conversationId)).toBe(false);
  });

  it('removes what another device deleted: an answer that was generated again', async () => {
    const again = ANSWER + 30000;
    server = [text(USER, 'Hello'), answer(ANSWER, 'Hi there')];
    await repository.syncConversation(conversationId);

    server = [text(USER, 'Hello'), answer(again, 'Good morning')];
    expect(await repository.syncConversation(conversationId)).toBe(true);
    expect(await localIds()).toEqual([USER, again]);

    // And the last message, deleted with nothing after it
    server = [text(USER, 'Hello')];
    expect(await repository.syncConversation(conversationId)).toBe(true);
    expect(await localIds()).toEqual([USER]);
  });

  it('keeps what only this browser has: a message that was not sent, an answer that was stopped', async () => {
    const notSent = Message.createText(
      { id: Message.localId(), conversationId, roleName: 'user', time: new Date() }, 'Not sent');
    // The server gave the answer its id when it started, and never stored it
    const stopped = Message.createAgent(conversationId, [], 'Hi th', 'complete');
    stopped.id = ANSWER;
    stopped.time = new Date(T * 1000);
    await dbService.saveMessage(notSent);
    await dbService.saveMessage(stopped);

    server = [text(USER, 'Hello')];
    await repository.syncConversation(conversationId);
    expect(await localIds()).toEqual([USER, ANSWER, notSent.id]);

    // Also once the conversation went on
    server.push(text(USER + 60000, 'Next'), answer(ANSWER + 60000, 'Yes'));
    await repository.syncConversation(conversationId);
    await repository.syncConversation(conversationId);
    expect(await localIds()).toEqual([USER, ANSWER, USER + 60000, ANSWER + 60000, notSent.id]);
    expect((await localMessages())[1].getDisplayContent()).toBe('Hi th');
  });

  it('keeps older messages that are no longer among the newest', async () => {
    server = Array.from({ length: 20 }, (_, i) => text(USER + i * 1000, `Message ${i}`));
    await repository.syncConversation(conversationId);
    expect((await localIds()).length).toBe(20);

    // Five more: the five oldest are not returned any more, and are still there
    server.push(...Array.from({ length: 5 }, (_, i) => text(USER + (20 + i) * 1000, `Message ${20 + i}`)));
    await repository.syncConversation(conversationId);
    expect(await localIds()).toEqual(server.map(m => m.id));

    // One of the newest is deleted: an older one moves up among the newest, nothing else changes
    const deleted = server.splice(22, 1)[0].id;
    await repository.syncConversation(conversationId);
    expect(await localIds()).toEqual(server.map(m => m.id));
    expect(await localIds()).not.toContain(deleted);
  });

  it('leaves the merge to the next sync when a message changed here while the request ran', async () => {
    server = [text(USER, 'Hello'), answer(ANSWER, 'Hi there')];
    await repository.syncConversation(conversationId);

    // The answer is deleted here while the server's reply, which still has it, is on its way
    spyOn<any>(messageRepository, 'isOnline').and.resolveTo(false);
    duringRequest = () => messageRepository.delete(ANSWER);
    expect(await repository.syncConversation(conversationId)).toBe(false);
    expect(await localIds()).toEqual([USER]);

    // The next sync (the server deleted it too) changes nothing
    duringRequest = async () => {};
    server = [text(USER, 'Hello')];
    expect(await repository.syncConversation(conversationId)).toBe(false);
    expect(await localIds()).toEqual([USER]);
  });

  it('changes nothing when the request fails', async () => {
    server = [text(USER, 'Hello'), answer(ANSWER, 'Hi there')];
    await repository.syncConversation(conversationId);

    duringRequest = async () => { throw new Error('offline'); };
    spyOn(console, 'error');
    expect(await repository.syncConversation(conversationId)).toBe(false);
    expect(await localIds()).toEqual([USER, ANSWER]);
  });

  it('loads the page before the oldest message by id, also a message of the same second', async () => {
    // 21 messages: the newest 20 start with an answer, whose message shares its second with it
    server = [text(USER, 'Hello'), answer(ANSWER, 'Hi there'),
      ...Array.from({ length: 19 }, (_, i) => text(USER + (i + 1) * 1000, `Message ${i}`))];
    await repository.syncConversation(conversationId);
    expect((await localIds())[0]).toBe(ANSWER);

    const older = await repository.loadOlderMessages(conversationId, ANSWER, 20);
    expect(older.map(m => m.id)).toEqual([USER]);
    expect(messageRequests[1]).toEqual({ count: 20, beforeId: ANSWER });
    expect(await localIds()).toEqual(server.map(m => m.id));
  });

  it('saves a streamed answer the sync already brought, without a second copy in the chat', async () => {
    server = [text(USER, 'Hello'), answer(ANSWER, 'Hi there')];
    const shown = messageRepository.getByConversationId(conversationId);
    await repository.syncConversation(conversationId);

    const streamed = Message.createAgent(conversationId, [], 'Hi there', 'complete');
    streamed.id = ANSWER;
    streamed.time = new Date(T * 1000);
    await messageRepository.save(streamed);

    expect((await firstValueFrom(shown)).map(m => m.id).sort()).toEqual([USER, ANSWER]);
    expect(await localIds()).toEqual([USER, ANSWER]);
  });
});

describe('removedOnServer', () => {
  const messages = (...ids: number[]) =>
    ids.map(id => Message.createText({ id, conversationId: 'c', roleName: 'user', time: new Date() }, ''));

  it('names the known messages the server no longer returns among its newest', () => {
    expect(removedOnServer([10, 20, 30], messages(10, 30))).toEqual([20]);
    expect(removedOnServer([10, 20, 30], messages(10, 20))).toEqual([30]);
  });

  it('leaves the ones that are older than what the server returns', () => {
    expect(removedOnServer([10, 20, 30], messages(20, 30, 40))).toEqual([]);
  });

  it('names all of them when the server has no messages left', () => {
    expect(removedOnServer([10, 20], [])).toEqual([10, 20]);
  });

  it('knows nothing before the first sync', () => {
    expect(removedOnServer([], messages(10, 20))).toEqual([]);
  });
});

describe('mergeServerMessage', () => {
  const voice = (extra: object) => Message.createText(
    { id: 1, conversationId: 'c', roleName: 'user', time: new Date(1000), version: 1 }, 'Hello',
    [{ id: 'f1', name: 'voice.webm', size: 1, sizeFormatted: '1 B', type: 'audio' as any, mimeType: 'audio/webm',
      uploadStatus: UploadStatus.COMPLETED, ...extra }]);

  it('keeps the audio and the transcript only this browser has', () => {
    const local = voice({ base64Data: 'AAAA', transcript: 'Hello' });
    const server = voice({});
    server.version = 2;

    const merged = mergeServerMessage(server, local);
    expect(merged?.version).toBe(2);
    expect(merged?.attachments?.[0].base64Data).toBe('AAAA');
    expect(merged?.attachments?.[0].transcript).toBe('Hello');
  });

  it('leaves a copy that says the same, whatever else the browser keeps with it', () => {
    expect(mergeServerMessage(voice({}), voice({ base64Data: 'AAAA', transcript: 'Hello' }))).toBeNull();
  });
});
