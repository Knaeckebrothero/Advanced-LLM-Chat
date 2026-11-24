import { Message } from '../data/objects/message';

/**
 * What a message (ChatUiMessageComponent) asks of the chat that shows it: the main chat
 * (ChatUiComponent) or the side chat panel (SideChatPanelComponent, docs/side_chats.md).
 */
export abstract class MessageHost {
  /** An answer is being written in this chat. */
  abstract get isStreaming(): boolean;
  /** The names a message's text may use ({{user}}, "Assistant:"). */
  abstract userName: string;
  abstract aiName: string;
  /** The image and name of the chat's agent, shown with its answers (null: none). */
  abstract agentAvatar: string | null;
  abstract agentName: string | null;
  /** Messages can be edited, inserted and sent again here (the side chat panel can't). */
  abstract get canEdit(): boolean;
  /** Side chats can be forked from the messages here (not in a side chat: no side chats of side chats). */
  abstract get canForkSideChats(): boolean;

  /** How many side chats this message has (0 where there are none). */
  abstract sideChatCount(message: Message): number;
  /** Open a new side chat forked from this message. */
  abstract openSideChat(message: Message): void;
  /** Open this message's side chats: the one, or the list of them. */
  abstract openSideChatsOf(message: Message): void;

  abstract deleteMessage(messageId: number): void;
  abstract switchAlternative(message: Message, position: number): Promise<void>;
  abstract deleteAlternative(message: Message): Promise<void>;
  abstract patchMessage(messageId: number, content: string): Promise<void>;
  abstract resendEditedMessage(messageId: number, content: string): Promise<void>;
  abstract insertMessage(
    next: Message, position: 'before' | 'after', roleName: 'user' | 'Assistant' | 'system', content: string
  ): Promise<void>;
  abstract countMessagesAfter(message: Message): number;
  abstract resendMessage(messageId: number): Promise<void>;
  abstract regenerateMessage(message: Message, modelId?: number): void;
  abstract rateMessage(message: Message, rating: number | null): void;
}
