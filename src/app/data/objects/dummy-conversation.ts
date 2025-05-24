import { Conversation } from '../objects/conversation';

// crearte dummy conversations
const conv1 = new Conversation(1, 1, 'Test Chat A', ['MM Max Mustermann']);
conv1.updatedAt = new Date('2025-05-21T12:00:00');

const conv2 = new Conversation(2, 1, 'Test Chat B', ['MM Max Mustermann']);
conv2.updatedAt = new Date('2025-05-23T09:00:00');

const conv3 = new Conversation(3, 1, 'Sidebar implementieren', ['MM Max Mustermann']);
conv3.updatedAt = new Date('2025-05-23T09:00:00');

const conv4 = new Conversation(4, 1, 'TestTestTestTest...', ['MM Max Mustermann']);
conv4.updatedAt = new Date('2025-05-04T09:00:00');

const conv5 = new Conversation(5, 1, 'sehr alter Chat', ['MM Max Mustermann']);
conv5.updatedAt = new Date('2024-02-23T09:00:00');

const conv6 = new Conversation(5, 1, 'sehr alter Chat', ['MM Max Mustermann']);
conv6.updatedAt = new Date('2024-02-23T09:00:00');

const conv7 = new Conversation(5, 1, 'sehr alter Chat', ['MM Max Mustermann']);
conv7.updatedAt = new Date('2024-02-23T09:00:00');

const conv8 = new Conversation(5, 1, 'sehr alter Chat', ['MM Max Mustermann']);
conv8.updatedAt = new Date('2024-02-23T09:00:00');

const conv9 = new Conversation(5, 1, 'sehr alter Chat', ['MM Max Mustermann']);
conv9.updatedAt = new Date('2024-02-23T09:00:00');


export const DUMMY_CONVERSATIONS = [conv1, conv2, conv3, conv4, conv5, conv6, conv7, conv8, conv9];
