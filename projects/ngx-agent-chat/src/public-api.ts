/*
 * Public API Surface of ngx-agent-chat
 */

// Models & Types
export * from './lib/models/message.model';
export * from './lib/models/file.model';
export { Message, FilePreviewUtil } from './lib/models/message';

// Components
export { AgentStepsComponent } from './lib/components/agent-steps/agent-steps.component';
export {
  ChatMessageComponent,
  MessageEditEvent,
  MessageRateEvent,
  AttachmentClickEvent,
} from './lib/components/chat-message/chat-message.component';
export { ChatInputComponent } from './lib/components/chat-input/chat-input.component';
export {
  ChatContainerComponent,
  SendMessageEvent,
} from './lib/components/chat-container/chat-container.component';
