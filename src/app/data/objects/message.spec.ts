import { Message } from './message';

/** The versions of an answer (docs/answer_versions.md) as the server sends them and IndexedDB keeps them. */
describe('Message - versions of an answer', () => {
  const answer = (extra: object = {}) => ({
    id: 1794741599579, conversationId: 'c', roleName: 'Assistant', content: 'Hi', finalResponse: 'Hi',
    time: 1794741599, type: 'agent', version: 3, steps: [], status: 'complete', ...extra
  });

  it('reads the version shown and their number from the server', () => {
    const message = Message.fromApiResponse(answer({ alternativePosition: 2, alternativeCount: 3 }));
    expect(message.alternatives).toEqual({ position: 2, count: 3 });
  });

  it('has none without other versions', () => {
    expect(Message.fromApiResponse(answer()).alternatives).toBeNull();
    expect(Message.fromApiResponse(answer({ alternativePosition: null, alternativeCount: null })).alternatives)
      .toBeNull();
    expect(Message.fromApiResponse(answer({ alternativePosition: 1, alternativeCount: 1 })).alternatives).toBeNull();
  });

  it('keeps them in IndexedDB', () => {
    const message = Message.fromApiResponse(answer({ alternativePosition: 1, alternativeCount: 2 }));
    const stored = Message.fromJSON(JSON.parse(JSON.stringify(message.toJSON())));
    expect(stored.alternatives).toEqual({ position: 1, count: 2 });
    expect(stored.version).toBe(3);

    const without = Message.fromJSON(JSON.parse(JSON.stringify(Message.fromApiResponse(answer()).toJSON())));
    expect(without.alternatives).toBeNull();
  });
});
