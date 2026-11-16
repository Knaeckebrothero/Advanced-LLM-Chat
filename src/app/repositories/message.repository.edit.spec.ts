import { TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { filter } from 'rxjs/operators';
import { MessageRepository } from './message.repository';
import { mergeServerMessage } from './conversation.repository';
import { DBService } from '../data/db.service';
import { ApiService } from '../services/api.service';
import { Message } from '../data/objects/message';

/**
 * Editing and rating a stored message. The server counts a version per message and takes an edit
 * only of the version it has; the browser's copy has to carry that version, or the next edit is
 * refused ("version conflict"). Against the real IndexedDB of the test browser, with the server
 * played by a map of messages that checks versions as the API does.
 */
describe('MessageRepository - editing and rating a stored message', () => {
  let repository: MessageRepository;
  let dbService: DBService;
  let conversationId: string;
  /** What the server has, by id: the messages as the API sends them to a sync. */
  let server: Map<number, any>;
  /** The version the browser sent with each edit. */
  let sentVersions: number[];
  let unreachable: boolean;
  let refusesEveryVersion: boolean;

  const T = 1794741599;
  const USER = T * 1000 + 458;
  const ANSWER = T * 1000 + 579;
  const LATER = USER + 60000;

  const text = (id: number, content: string, extra: object = {}) => ({
    id, conversationId, roleName: 'user', content, time: Math.floor(id / 1000), type: 'text', version: 1,
    lastModified: Math.floor(id / 1000), rating: null, ...extra
  });
  const answer = (id: number, content: string, extra: object = {}) => ({
    id, conversationId, roleName: 'Assistant', content, finalResponse: content, time: Math.floor(id / 1000),
    type: 'agent', version: 1, lastModified: Math.floor(id / 1000), rating: null,
    steps: [{ id: 's1', type: 'thought', title: 'Thinking', content: 'Hm', timestamp: id }],
    status: 'complete', error: null, modelId: 4, modelName: 'Model', usage: { inputTokens: 10, outputTokens: 5 },
    ...extra
  });
  const attachment = { fileId: 'f1', fileName: 'notes.pdf', mimeType: 'application/pdf', fileSize: 12 };

  /**
   * The server's answer to an edit or a rating (MessageResponse): the message's text, version and
   * rating. An answer's steps, model and usage and a message's attachments are not in it.
   */
  const shortResponse = (stored: any) => Message.fromApiResponse({
    id: stored.id, conversationId: stored.conversationId, roleName: stored.roleName, content: stored.content,
    time: stored.time, type: stored.type, version: stored.version, lastModified: stored.lastModified,
    rating: stored.rating, attachments: null, steps: null, finalResponse: null, status: null, error: null,
    modelId: null, modelName: null, usage: null
  });
  const httpError = (status: number, detail?: string) =>
    new HttpErrorResponse({ status, error: detail ? { detail } : null });

  /** The server's copy as a sync gets it. */
  const fromServer = (id: number) => Message.fromApiResponse(JSON.parse(JSON.stringify(server.get(id))));
  /** The browser has what the server has, as after a sync. */
  const syncAll = async () => {
    for (const id of server.keys()) {
      await dbService.saveMessage(fromServer(id));
    }
  };
  /** What the chat shows: the conversation's messages in the repository's cache. */
  const shown = async () => {
    const messages = await firstValueFrom(
      repository.getByConversationId(conversationId).pipe(filter(list => list.length > 0)));
    return [...messages].sort(Message.compare);
  };
  const shownMessage = async (id: number) => (await shown()).find(m => m.id === id)!;
  /** As the chat does: the message it shows, with a new text. */
  const edit = async (id: number, content: string, deleteFollowing = false) =>
    repository.patch(await shownMessage(id), content, deleteFollowing);

  beforeEach(async () => {
    conversationId = `edit-test-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    server = new Map();
    sentVersions = [];
    unreachable = false;
    refusesEveryVersion = false;

    const api = {
      // PATCH /api/message/patch
      patchMessage: async (_conversationId: string, id: number, content: string, version: number,
                           deleteFollowing = false) => {
        sentVersions.push(version);
        if (unreachable) throw httpError(0);
        const stored = server.get(id);
        if (!stored) throw httpError(404, 'Message not found');
        if (stored.version !== version || refusesEveryVersion) {
          throw httpError(409, `Version conflict: current version is ${stored.version}, provided version is ${version}`);
        }
        stored.content = content;
        if (stored.type === 'agent') stored.finalResponse = content;
        stored.version += 1;
        stored.lastModified += 100;
        if (deleteFollowing) {
          [...server.keys()].filter(other => other > id).forEach(other => server.delete(other));
        }
        return shortResponse(stored);
      },
      // POST /api/message/rate: the version stays
      rateMessage: async (id: number, _conversationId: string, rating: number | null) => {
        if (unreachable) throw httpError(0);
        const stored = server.get(id);
        if (!stored) throw httpError(404, 'Message not found');
        stored.rating = rating;
        return shortResponse(stored);
      },
      // GET /api/conversation/{id}/messages: the newest by id, or the ones before a message
      getConversationMessages: async (_conversationId: string, count: number, beforeId?: number) =>
        [...server.keys()]
          .filter(id => beforeId === undefined || id < beforeId)
          .sort((a, b) => a - b)
          .slice(-count)
          .map(fromServer)
    };

    TestBed.configureTestingModule({ providers: [{ provide: ApiService, useValue: api }] });
    dbService = TestBed.inject(DBService);
    await (dbService as any).status;
    repository = TestBed.inject(MessageRepository);
  });

  afterEach(async () => {
    await dbService.deleteConversationWithMessages(conversationId);
  });

  it('saves an edit twice in a row', async () => {
    server.set(USER, text(USER, 'Hello'));
    await syncAll();
    const before = Date.now();

    await edit(USER, 'Hello there');
    await edit(USER, 'Hello there, you');
    await edit(USER, 'Hello there, you two');

    // The server took each edit at once: the browser sent the version the server had
    expect(sentVersions).toEqual([1, 2, 3]);
    expect(server.get(USER).content).toBe('Hello there, you two');
    const stored = (await dbService.getMessage(USER))!;
    expect(stored.getDisplayContent()).toBe('Hello there, you two');
    expect(stored.version).toBe(server.get(USER).version);
    expect((await shownMessage(USER)).getDisplayContent()).toBe('Hello there, you two');
    // A sync that asked the server before the edit doesn't put the old text back
    expect(repository.changedLocallySince(conversationId, before)).toBe(true);
  });

  it('saves the edit of an answer twice in a row, and the answer keeps its steps', async () => {
    server.set(USER, text(USER, 'Hello'));
    server.set(ANSWER, answer(ANSWER, 'Hi there'));
    await syncAll();

    await edit(ANSWER, 'Hi');
    await edit(ANSWER, 'Hi!');

    expect(sentVersions).toEqual([1, 2]);
    const stored = (await dbService.getMessage(ANSWER))!;
    expect(stored.getDisplayContent()).toBe('Hi!');
    expect(stored.version).toBe(3);
    expect(stored.isAgent() && stored.content.steps.map(step => step.id)).toEqual(['s1']);
    expect(stored.isAgent() && stored.content.modelName).toBe('Model');
  });

  it('saves the edit of a message that was rated before', async () => {
    server.set(ANSWER, answer(ANSWER, 'Hi there'));
    await syncAll();

    await repository.rateMessage(ANSWER, conversationId, 1);
    await edit(ANSWER, 'Hi');

    expect(sentVersions).toEqual([1]);
    const stored = (await dbService.getMessage(ANSWER))!;
    expect(stored.getDisplayContent()).toBe('Hi');
    expect(stored.rating).toBe(1);
    expect(stored.version).toBe(2);
  });

  it('keeps the steps, model and usage of an answer that is rated', async () => {
    server.set(ANSWER, answer(ANSWER, 'Hi there'));
    await syncAll();

    const rated = await repository.rateMessage(ANSWER, conversationId, 1);

    for (const copy of [rated, (await dbService.getMessage(ANSWER))!, await shownMessage(ANSWER)]) {
      expect(copy.rating).toBe(1);
      expect(copy.version).toBe(1);
      expect(copy.isAgent() && copy.content.steps.map(step => step.id)).toEqual(['s1']);
      expect(copy.isAgent() && copy.content.modelName).toBe('Model');
      expect(copy.isAgent() && copy.content.usage?.outputTokens).toBe(5);
    }

    // And the rating can be taken back
    await repository.rateMessage(ANSWER, conversationId, null);
    expect((await dbService.getMessage(ANSWER))!.rating).toBeNull();
  });

  it('keeps the attachments of a message that is rated or edited', async () => {
    server.set(USER, text(USER, 'See this', { attachments: [attachment] }));
    await syncAll();

    await repository.rateMessage(USER, conversationId, 0);
    await edit(USER, 'See that');

    const stored = (await dbService.getMessage(USER))!;
    expect(stored.getDisplayContent()).toBe('See that');
    expect(stored.rating).toBe(0);
    expect(stored.attachments?.map(file => file.id)).toEqual(['f1']);
  });

  it('leaves the browser with what the server has: the next sync changes nothing', async () => {
    server.set(USER, text(USER, 'See this', { attachments: [attachment] }));
    server.set(ANSWER, answer(ANSWER, 'Hi there'));
    await syncAll();

    await edit(USER, 'See that');
    await repository.rateMessage(ANSWER, conversationId, 1);
    await edit(ANSWER, 'Hi');
    await edit(ANSWER, 'Hi!');

    for (const id of [USER, ANSWER]) {
      expect(mergeServerMessage(fromServer(id), await dbService.getMessage(id))).toBeNull();
    }
  });

  it('saves the edit of a copy whose version ran ahead of the server', async () => {
    // An older version of the app counted the version itself: by two for every edit
    server.set(USER, text(USER, 'Hello there', { version: 2 }));
    await dbService.saveMessage(Message.fromApiResponse(text(USER, 'Hello there', { version: 3 })));

    await edit(USER, 'Hello there, you');

    // Refused, asked which version the server has, saved on that one
    expect(sentVersions).toEqual([3, 2]);
    expect(server.get(USER).content).toBe('Hello there, you');
    expect((await dbService.getMessage(USER))!.version).toBe(3);

    await edit(USER, 'Hello');
    expect(sentVersions).toEqual([3, 2, 3]);
  });

  it('saves the edit of a message another device edited since the last sync', async () => {
    server.set(USER, text(USER, 'Hello'));
    server.set(LATER, text(LATER, 'Still there?'));
    await syncAll();
    server.set(USER, text(USER, 'Edited elsewhere', { version: 4 }));

    await edit(USER, 'Edited here');

    expect(sentVersions).toEqual([1, 4]);
    expect(server.get(USER).content).toBe('Edited here');
    const stored = (await dbService.getMessage(USER))!;
    expect(stored.getDisplayContent()).toBe('Edited here');
    expect(stored.version).toBe(5);
    expect(server.has(LATER)).toBe(true);
  });

  it('deletes the later messages on the server when asked to, also on the second try', async () => {
    server.set(USER, text(USER, 'Hello', { version: 2 }));
    server.set(ANSWER, answer(ANSWER, 'Hi there'));
    await dbService.saveMessage(Message.fromApiResponse(text(USER, 'Hello', { version: 3 })));

    await edit(USER, 'Hello again', true);

    expect([...server.keys()]).toEqual([USER]);
    expect(server.get(USER).content).toBe('Hello again');
  });

  it('leaves the message as it was when the server cannot be reached', async () => {
    server.set(USER, text(USER, 'Hello'));
    await syncAll();
    unreachable = true;

    await expectAsync(edit(USER, 'Hello there')).toBeRejectedWith(jasmine.objectContaining({ status: 0 }));
    await expectAsync(repository.rateMessage(USER, conversationId, 1))
      .toBeRejectedWith(jasmine.objectContaining({ status: 0 }));

    const stored = (await dbService.getMessage(USER))!;
    expect(stored.getDisplayContent()).toBe('Hello');
    expect(stored.version).toBe(1);
    expect(stored.rating).toBeNull();
    expect((await shownMessage(USER)).getDisplayContent()).toBe('Hello');
  });

  it('gives up after one more try when the server still refuses the edit', async () => {
    server.set(USER, text(USER, 'Hello'));
    await syncAll();
    refusesEveryVersion = true;

    await expectAsync(edit(USER, 'Hello there')).toBeRejectedWith(jasmine.objectContaining({ status: 409 }));

    expect(sentVersions).toEqual([1, 1]);
    expect((await dbService.getMessage(USER))!.getDisplayContent()).toBe('Hello');
  });

  it('leaves the message as it was when the server no longer has it', async () => {
    server.set(USER, text(USER, 'Hello'));
    server.set(LATER, text(LATER, 'Still there?'));
    await syncAll();
    server.delete(LATER);

    await expectAsync(edit(LATER, 'Anyone?')).toBeRejectedWith(jasmine.objectContaining({ status: 404 }));

    expect(sentVersions).toEqual([1]);
    expect((await dbService.getMessage(LATER))!.getDisplayContent()).toBe('Still there?');
  });
});
