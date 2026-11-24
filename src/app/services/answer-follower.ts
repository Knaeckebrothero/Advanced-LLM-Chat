// src/app/services/answer-follower.ts
import { TranslateService } from '@ngx-translate/core';
import { BehaviorSubject, Observable, Subscription } from 'rxjs';
import { AgentContent, AgentStep, Message } from '../data/objects/message';
import { IConversationSummary } from '../data/models/conversation.model';
import { ConversationRepository } from '../repositories/conversation.repository';
import { MessageRepository } from '../repositories/message.repository';
import { ApiService } from './api.service';
import { NotificationService } from './notification.service';
import {
  DoneEventData,
  ErrorEventData,
  MessageStartEventData,
  NoAnswerRunningError,
  StepDeltaEventData,
  StreamEvent,
  StreamHttpError,
  StreamingService
} from './streaming.service';

/**
 * The answer a follower follows. It runs on the server on its own (docs/background_answers.md):
 * a stream that breaks only stops watching it, so it is followed again from the last event it got.
 */
interface Following {
  conversationId: string;
  message: Message<AgentContent>;
  runId: string | null;  // From message_start: to follow it again and to stop it
  lastEventId: number;  // The number of the last event it got
  attempts: number;  // Attempts in a row to follow it again without getting anything
  shown: boolean;  // The chat shows it (an answer followed again shows once its first event arrives)
  stored?: Message[];  // Followed again: the conversation's messages, to find the answer it writes a new version of
}

/** What a follower needs from the app. */
export interface AnswerFollowerDeps {
  streamingService: StreamingService;
  messageRepository: MessageRepository;
  conversationRepository: ConversationRepository;
  apiService: ApiService;
  notificationService: NotificationService;
  translate: TranslateService;
}

/** What its owner does with what a follower learns. */
export interface AnswerFollowerHooks {
  /** The stored messages of a conversation whose running answer is followed (to find one it writes a new version of). */
  storedMessages(conversationId: string): Promise<Message[]>;
  /** Whether a running answer of this conversation is still wanted (its conversation is still open). */
  canFollow(conversationId: string): boolean;
  /** A summary of the conversation's oldest messages was written before the answer. */
  onSummary?(summary: IConversationSummary): void;
  /** The answer's agent hid its conversation, or took the mark back. */
  onAgentHide?(conversationId: string, hidden: boolean): void;
}

/**
 * Follows the answer of one conversation at a time: one it starts (a new answer, or a new version
 * of one) or one that is being written already (started before the app was closed, or on another
 * device). It puts the answer's events into a message the chat shows while it is written
 * (streamingMessage$), saves what the server stored when it ends, follows a broken stream again,
 * and stops the answer on request. The main chat has one, and the side chat panel another
 * (docs/side_chats.md), so both can show an answer at the same time.
 */
export class AnswerFollower {
  /** The answer being written, as the chat shows it; null when there is none. */
  readonly streamingMessage$ = new BehaviorSubject<Message<AgentContent> | null>(null);
  /** Whether an answer is being written and shown. */
  readonly isStreaming$ = new BehaviorSubject<boolean>(false);

  private streamingSubscription: Subscription | null = null;
  // Answers that failed and that the server stored (with its error): kept when their stream ends
  private storedErrors = new WeakSet<Message>();
  // The answer a running stream writes a new version of (Regenerate), null for a new answer
  private regenerating: Message | null = null;
  // The answer this browser follows, also while it tries to follow it again (Following)
  private following: Following | null = null;
  // Waits before following an answer again after its stream broke without anything new
  private static readonly FOLLOW_AGAIN_DELAYS = [0, 2000, 5000, 10000];

  constructor(private deps: AnswerFollowerDeps, private hooks: AnswerFollowerHooks) {}

  /** The conversation whose answer is followed (also while it waits to follow it again), or null. */
  get followedConversationId(): string | null {
    return this.following?.conversationId ?? null;
  }

  /**
   * Start an answer in a conversation and follow it.
   * @param modelId - Answer with this catalog model instead of the conversation's model
   * @param regenerate - Write a new version of this answer (it keeps its id and place)
   */
  start(conversationId: string, modelId?: number, regenerate?: Message): void {
    // Create placeholder agent message for streaming
    const agentMessage = Message.createAgent(conversationId, [], '', 'thinking');
    if (regenerate) {
      // A new version of a stored answer takes its place and id: the chat hides the stored copy
      // while it streams (and shows it again if it is stopped before the model wrote anything)
      agentMessage.id = regenerate.id;
      agentMessage.roleName = regenerate.roleName;
    }
    this.regenerating = regenerate ?? null;
    this.streamingMessage$.next(agentMessage);
    this.isStreaming$.next(true);

    // Start streaming (an earlier stream, e.g. an attempt to follow an answer, is closed)
    this.watch(
      { conversationId, message: agentMessage, runId: null, lastEventId: 0, attempts: 0, shown: true },
      this.deps.streamingService.streamAgentResponse(conversationId, 'Assistant', modelId, regenerate?.id)
    );
  }

  /**
   * Follow the answer that is being written in a conversation, if there is one
   * (docs/background_answers.md). The answer shows once its first events arrive, with what was
   * written so far. Nothing happens while this follower follows an answer already.
   */
  async follow(conversationId: string): Promise<void> {
    if (!conversationId || conversationId === '0' || this.following) {
      return;
    }
    const stored = await this.hooks.storedMessages(conversationId);
    if (this.following || !this.hooks.canFollow(conversationId)) {
      return;
    }
    const message = Message.createAgent(conversationId, [], '', 'thinking');
    this.watch(
      { conversationId, message, runId: null, lastEventId: 0, attempts: 0, shown: false, stored },
      this.deps.streamingService.followAgentResponse(conversationId)
    );
  }

  /**
   * Stop following the answer, without stopping it: it goes on on the server (another
   * conversation opens), and opening its conversation follows it again.
   */
  leave(): void {
    const following = this.following;
    if (!following) {
      return;
    }
    this.following = null;
    this.streamingSubscription?.unsubscribe();
    this.streamingSubscription = null;
    if (following.shown) {
      this.regenerating = null;
      this.isStreaming$.next(false);
      this.streamingMessage$.next(null);
    }
  }

  /**
   * Stop the answer (Stop). Saves the partial response if any content was generated.
   */
  async cancel(): Promise<void> {
    // Unsubscribe first to stop receiving more tokens; nothing follows the answer again
    const following = this.following;
    this.following = null;
    if (this.streamingSubscription) {
      this.streamingSubscription.unsubscribe();
      this.streamingSubscription = null;
    }

    // The answer runs on the server on its own (docs/background_answers.md): closing its stream
    // doesn't stop it, the server does, and keeps what was written (as a new answer, or as a new
    // version of the regenerated one). Only that run, so a late Stop can't stop a newer answer
    const stopped = following
      ? this.deps.streamingService.stopAgentResponse(following.conversationId, following.runId).catch(error => {
          console.warn('Could not stop the answer:', error);
          return false;
        })
      : Promise.resolve(false);

    // Get the current streaming message before clearing
    const streamingMessage = this.streamingMessage$.getValue();
    const regenerated = this.regenerating;
    this.regenerating = null;

    // Save partial response if we have any content. The server keeps it too
    if (streamingMessage && streamingMessage.content) {
      const hasContent = streamingMessage.content.content?.trim().length > 0;
      const hasSteps = streamingMessage.content.steps?.length > 0;

      if (hasContent || hasSteps) {
        // Mark as complete (user intentionally stopped it)
        streamingMessage.content.status = 'complete';

        // Save to IndexedDB
        await this.deps.messageRepository.save(streamingMessage);

        // The conversation moves up in the sidebar
        await this.deps.conversationRepository.recordMessage(streamingMessage.conversationId, streamingMessage.id);

        // The version counter and the versions are the server's: ask for them once it has the answer
        if (regenerated && streamingMessage.id === regenerated.id) {
          void stopped.then(() => this.refreshStoppedVersion(streamingMessage, regenerated.version));
        }
      }
      // Otherwise nothing changed: the version shown before appears again
    }

    // Clean up streaming state
    this.isStreaming$.next(false);
    this.streamingMessage$.next(null);
  }

  /**
   * After a stopped regeneration: take the answer as the server stored it (its version counter
   * and versions), once it is newer than the version this browser regenerated. Called once Stop
   * returned (the server has stored it then); it asks again a moment later in case it hadn't.
   */
  private async refreshStoppedVersion(message: Message, regeneratedVersion: number): Promise<void> {
    for (const wait of [500, 2000]) {
      await new Promise(resolve => setTimeout(resolve, wait));
      try {
        const [stored] = await this.deps.apiService.getConversationMessages(message.conversationId, 1, message.id + 1);
        if (stored?.id === message.id && stored.version > regeneratedVersion) {
          await this.deps.messageRepository.save(stored, true);
          return;
        }
      } catch {
        return;  // The next sync brings it
      }
    }
  }

  /**
   * Handle individual stream events
   */
  private handleStreamEvent(event: StreamEvent, message: Message<AgentContent>): void {
    switch (event.type) {
      case 'message_start':
        // Message envelope received - apply metadata immediately
        const startData = event.data as MessageStartEventData;
        // The server didn't have the answer being regenerated (only this browser did): it writes a
        // new answer, and this browser's copy goes
        const replaced = this.regenerating;
        if (replaced && replaced.id !== startData.messageId) {
          void this.deps.messageRepository.removeLocally(replaced.conversationId, [replaced.id]);
          this.regenerating = null;
        }
        // Followed again (the app was closed): a new version of a stored answer hides it, as Regenerate does
        const stored = this.following?.message === message ? this.following.stored : undefined;
        if (!this.regenerating && stored) {
          this.regenerating = stored.find(m => m.id === startData.messageId && !m.isText()) ?? null;
        }
        message.id = startData.messageId;
        message.time = new Date(startData.time * 1000);
        message.roleName = startData.roleName;
        // Which model answers (modelId null = the environment model)
        if (startData.modelId !== undefined) message.content.modelId = startData.modelId;
        if (startData.modelName !== undefined) message.content.modelName = startData.modelName;
        // Status remains 'thinking' until we get steps or tokens
        break;

      case 'step': {
        // A step with a known id replaces the earlier one (e.g. the reasoning step, sent
        // empty at its start and complete at its end); otherwise it is a new step
        const step = event.data as AgentStep;
        // The agent hid its conversation, or took the mark back
        const hiddenChat = (step.metadata as Record<string, unknown> | undefined)?.['hiddenChat'];
        if (typeof hiddenChat === 'boolean' && message.conversationId) {
          this.hooks.onAgentHide?.(message.conversationId, hiddenChat);
        }
        const steps = message.content.steps;
        const index = steps.findIndex(s => s.id === step.id);
        if (index >= 0) {
          steps[index] = step;
        } else {
          steps.push(step);
          message.content.status = 'thinking';
        }
        break;
      }

      case 'step_delta': {
        // Live reasoning text for an earlier step
        const delta = event.data as StepDeltaEventData;
        const step = message.content.steps.find(s => s.id === delta.id);
        if (step) {
          step.content = (step.content || '') + delta.delta;
        }
        break;
      }

      case 'token':
        // Append the token to the response content
        message.content.content += event.data as string;
        message.content.status = 'responding';
        break;

      case 'summary':
        // The oldest messages were summarized before the answer
        this.hooks.onSummary?.(event.data as IConversationSummary);
        break;

      case 'done': {
        // Mark as complete (ID should already be set from message_start)
        const doneData = event.data as DoneEventData;
        if (doneData.modelId !== undefined) message.content.modelId = doneData.modelId;
        if (doneData.modelName !== undefined) message.content.modelName = doneData.modelName;
        if (doneData.usage !== undefined) message.content.usage = doneData.usage;
        this.takeVersions(message, doneData);
        message.content.status = 'complete';
        break;
      }

      case 'error': {
        // Handle error
        const errorData = event.data as ErrorEventData;
        message.content.status = 'error';
        message.content.error = errorData.error;
        if (errorData.messageId !== undefined) {
          // The server stored the failed answer: it stays here too
          message.id = errorData.messageId;
          this.takeVersions(message, errorData);
          this.storedErrors.add(message);
        }
        break;
      }
    }

    // Emit the updated message (create a new reference to trigger change detection)
    this.streamingMessage$.next(message);
  }

  /** The stored answer's version counter and versions, from a 'done' or a stored 'error' event. */
  private takeVersions(message: Message<AgentContent>, data: DoneEventData | ErrorEventData): void {
    if (data.version !== undefined) message.version = data.version;
    message.metadata.alternatives = Message.readAlternatives(data.alternativePosition, data.alternativeCount);
  }

  /**
   * Handle stream errors
   */
  private async handleStreamError(error: any, message: Message<AgentContent>): Promise<void> {
    console.error('Stream error:', error);

    // Update message to show error state
    message.content.status = 'error';
    message.content.error = error.message || 'An error occurred during streaming';

    // A new version that failed this way doesn't replace the stored answer here: its error is
    // shown on its own after it, as only this browser has it
    if (this.regenerating && message.id === this.regenerating.id) {
      message.id = Message.localId();
    }
    this.regenerating = null;

    // Save the error message to the repository (the server stored it too if it had started it)
    await this.deps.messageRepository.save(message);
    await this.deps.conversationRepository.recordMessage(message.conversationId, message.id);

    // Clean up streaming state
    this.following = null;
    this.streamingSubscription = null;
    this.isStreaming$.next(false);
    this.streamingMessage$.next(null);

    this.deps.notificationService.showError('Failed to generate response');
  }

  /**
   * Handle stream completion
   */
  private async handleStreamComplete(message: Message<AgentContent>): Promise<void> {
    // Save what the server stored: a complete answer, or one that failed (with its error)
    const complete = message.content.status === 'complete';
    if (complete || this.storedErrors.has(message)) {
      // The message was already saved on the backend by the SSE endpoint,
      // but we need to save it locally to IndexedDB
      await this.deps.messageRepository.save(message);

      // The conversation moves up in the sidebar
      await this.deps.conversationRepository.recordMessage(message.conversationId, message.id);

      if (complete) {
        this.deps.notificationService.showSuccess('Response generated');
      }
    }

    // Clean up streaming state
    this.regenerating = null;
    this.following = null;
    this.isStreaming$.next(false);
    this.streamingMessage$.next(null);
    this.streamingSubscription = null;
  }

  /** Put an answer's events into its message; how its stream ends decides what follows (onStreamEnd()). */
  private watch(following: Following, events$: Observable<StreamEvent>): void {
    this.streamingSubscription?.unsubscribe();
    this.following = following;
    this.streamingSubscription = events$.subscribe({
      next: event => {
        if (this.following !== following) return;
        if (event.id !== undefined) following.lastEventId = event.id;
        if (event.type === 'message_start') {
          following.runId = (event.data as MessageStartEventData).runId ?? null;
        }
        following.attempts = 0;
        this.handleStreamEvent(event, following.message);
        if (!following.shown) {
          // Followed again: the chat shows it from now on (its turn goes to the top of the view)
          following.shown = true;
          this.isStreaming$.next(true);
        }
      },
      error: error => void this.onStreamEnd(following, error),
      complete: () => void this.onStreamEnd(following)
    });
  }

  /**
   * An answer's stream ended. With its done or error event the answer is complete; otherwise only
   * the stream broke (the network, a phone that locked, a server that restarts) and the answer
   * goes on on the server: it is followed again from the last event this browser got.
   */
  private async onStreamEnd(following: Following, error?: unknown): Promise<void> {
    if (this.following !== following) {
      return;  // Stopped, left or replaced meanwhile
    }
    const message = following.message;
    if (message.content.status === 'complete' || message.content.status === 'error') {
      await this.handleStreamComplete(message);
      return;
    }
    if (error instanceof NoAnswerRunningError) {
      // Nothing to follow (any more): the stored answer, if any, comes with the sync
      this.finishFollowing(following);
      return;
    }
    if (error instanceof StreamHttpError && error.status === 409 && !following.runId) {
      // Another answer is being written in this conversation (another device's): follow that one
      this.finishFollowing(following);
      this.deps.notificationService.showInfo(this.deps.translate.instant('message.answerStillRunning'));
      void this.follow(following.conversationId);
      return;
    }
    if (!following.runId) {
      if (!following.shown) {
        this.finishFollowing(following);  // Following an answer failed
      } else if (error) {
        await this.handleStreamError(error, message);  // The answer never began
      } else {
        await this.handleStreamComplete(message);
      }
      return;
    }
    if (error instanceof StreamHttpError) {
      this.finishFollowing(following);  // E.g. the session ended: the sync brings what is stored
      return;
    }
    await this.followAgain(following);
  }

  /** Follow an answer again after its stream broke, after a short wait and once the app is visible. */
  private async followAgain(following: Following): Promise<void> {
    const wait = AnswerFollower.FOLLOW_AGAIN_DELAYS[following.attempts];
    if (wait === undefined) {
      // Unreachable for now (offline, or the server restarts): the sync and coming back to the
      // conversation bring the answer, or follow it again while it is written
      this.finishFollowing(following);
      return;
    }
    following.attempts++;
    if (wait) {
      await new Promise(resolve => setTimeout(resolve, wait));
    }
    // A hidden page (a locked phone) can't hold a connection: wait until it is visible
    while (document.hidden && this.following === following) {
      await new Promise<void>(resolve => document.addEventListener('visibilitychange', () => resolve(), { once: true }));
    }
    if (this.following !== following) {
      return;
    }
    this.watch(following, this.deps.streamingService.followAgentResponse(
      following.conversationId, following.runId, following.lastEventId));
  }

  /** Stop following an answer that can't be followed: what the server stored comes with the sync. */
  private finishFollowing(following: Following): void {
    if (this.following !== following) {
      return;
    }
    const shown = following.shown;
    this.leave();
    if (shown) {
      this.deps.conversationRepository.syncConversation(following.conversationId).catch(console.error);
    }
  }
}
