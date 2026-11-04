import { Conversation } from './conversation';

function conversation(id: string, createdAt: string, lastMessageAt?: string): Conversation {
  const conv = new Conversation(id, 1, id, ['user', 'Assistant']);
  conv.createdAt = new Date(createdAt);
  if (lastMessageAt) conv.lastMessageAt = new Date(lastMessageAt);
  return conv;
}

describe('Conversation order in the sidebar', () => {
  it('sorts by the newest message, not by updatedAt', () => {
    const renamedToday = conversation('renamed', '2026-10-01T10:00:00Z', '2026-10-02T10:00:00Z');
    renamedToday.updatedAt = new Date('2026-11-04T08:00:00Z');
    const writtenYesterday = conversation('written', '2026-10-20T10:00:00Z', '2026-11-03T21:00:00Z');

    const sorted = [renamedToday, writtenYesterday].sort(Conversation.compareByActivity);

    expect(sorted.map(c => c.id)).toEqual(['written', 'renamed']);
  });

  it('places a conversation without messages by its creation', () => {
    const empty = conversation('empty', '2026-11-04T09:00:00Z');
    const older = conversation('older', '2026-10-01T10:00:00Z', '2026-11-04T08:00:00Z');

    expect(empty.lastActivity).toEqual(new Date('2026-11-04T09:00:00Z'));
    expect([older, empty].sort(Conversation.compareByActivity).map(c => c.id)).toEqual(['empty', 'older']);
  });

  it('records messages the server stored by their id (the server clock in ms)', () => {
    const conv = conversation('c', '2026-10-01T10:00:00Z');
    const id = Date.parse('2026-11-04T09:30:00Z');

    expect(conv.recordMessage(id)).toBeTrue();
    expect(conv.lastMessageAt).toEqual(new Date(id));
  });

  it('ignores messages only in the browser and never moves back', () => {
    const conv = conversation('c', '2026-10-01T10:00:00Z', '2026-11-04T09:30:00Z');

    expect(conv.recordMessage(-5)).toBeFalse();
    expect(conv.mergeLastMessageAt(new Date('2026-11-01T00:00:00Z'))).toBeFalse();
    expect(conv.mergeLastMessageAt(undefined)).toBeFalse();
    expect(conv.lastMessageAt).toEqual(new Date('2026-11-04T09:30:00Z'));
  });

  it('reads the server times as UTC and keeps lastMessageAt in IndexedDB', () => {
    const fromApi = Conversation.fromApiResponse({
      id: 'c', userId: 1, name: 'n', participants: [],
      createdAt: '2026-10-01T10:00:00Z', updatedAt: '2026-10-01T10:00:00Z',
      lastMessageAt: '2026-11-03T21:40:05.236Z'
    });
    expect(fromApi.lastMessageAt?.toISOString()).toBe('2026-11-03T21:40:05.236Z');

    const stored = Conversation.fromPlainObject(fromApi.toJSON());
    expect(stored.lastMessageAt?.toISOString()).toBe('2026-11-03T21:40:05.236Z');

    const none = Conversation.fromApiResponse({ ...fromApi.toJSON(), lastMessageAt: null });
    expect(none.lastMessageAt).toBeUndefined();
  });
});
