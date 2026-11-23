// src/app/services/streaming.service.ts
import { Injectable } from '@angular/core';
import { Observable, Subscriber } from 'rxjs';
import { environment } from '../environments/environment';
import { AgentStep } from '../data/objects/message';
import { IMessageUsage } from '../data/models/catalog.model';
import { IConversationSummary } from '../data/models/conversation.model';
import { ApiService } from './api.service';
import { FamilyModeService } from './family-mode.service';

/**
 * Types of events that can be received from the SSE stream
 */
export type StreamEventType = 'message_start' | 'step' | 'step_delta' | 'token' | 'summary' | 'done' | 'error';

/**
 * Represents an event from the SSE stream
 */
export interface StreamEvent {
  type: StreamEventType;
  data: MessageStartEventData | AgentStep | StepDeltaEventData | string | IConversationSummary | DoneEventData | ErrorEventData;
  // The event's number in its answer (the SSE id): following the answer again with this number
  // gets only the events after it (docs/background_answers.md)
  id?: number;
}

/**
 * Data payload for 'message_start' events
 * Sent at the start of streaming to provide message metadata upfront
 */
export interface MessageStartEventData {
  messageId: number;
  conversationId: string;
  roleName: string;
  time: number;
  type: 'agent';
  modelId?: number | null;  // null for the environment model
  modelName?: string | null;
  runId?: string | null;  // The answer's run on the server: to follow it again, or to stop it
}

/**
 * Data payload for 'step_delta' events: text appended to the content of an earlier step
 * (the model's reasoning as it streams in)
 */
export interface StepDeltaEventData {
  id: string;
  delta: string;
}

/**
 * Data payload for 'done' events
 */
export interface DoneEventData extends AnswerVersionsData {
  messageId: number;
  conversationId: string;
  modelId?: number | null;
  modelName?: string | null;
  usage?: IMessageUsage | null;
  stopped?: boolean;  // Stop stopped it: what was written so far is stored
}

/**
 * The stored answer's version counter and its versions (docs/answer_versions.md), sent with
 * 'done' and with an 'error' the server stored
 */
export interface AnswerVersionsData {
  version?: number;
  alternativePosition?: number | null;
  alternativeCount?: number | null;
}

/**
 * Data payload for 'error' events
 */
export interface ErrorEventData extends AnswerVersionsData {
  error: string;
  messageId?: number;  // The server stored the failed answer with this id
}

/** The server refused the request (its status), e.g. 409: an answer is being written in the conversation. */
export class StreamHttpError extends Error {
  constructor(public readonly status: number, statusText: string) {
    super(`HTTP ${status}: ${statusText}`);
  }
}

/** Nothing is being written in the conversation (204): the stored answer comes with the sync. */
export class NoAnswerRunningError extends Error {
  constructor() {
    super('No answer is being written');
  }
}

/** The stream got nothing for a while, not even the server's pings: its connection is gone. */
export class StreamStalledError extends Error {
  constructor() {
    super('The stream stalled');
  }
}

/**
 * Service for handling Server-Sent Events (SSE) streaming from the backend.
 *
 * This service manages the connection to the streaming endpoint and provides
 * an Observable interface for consuming streaming events. It handles:
 * - Agent reasoning steps (thoughts, tool calls, observations)
 * - Token streaming for the final response
 * - A new summary of the conversation's oldest messages
 * - Completion and error events
 *
 * An answer runs on the server on its own (docs/background_answers.md): a stream that ends only
 * stops watching it. followAgentResponse() follows it again, stopAgentResponse() stops it.
 * The requests bypass the service worker (ngsw-bypass): a stream it passes on can be cut after
 * about 70 seconds on iOS.
 */
@Injectable({ providedIn: 'root' })
export class StreamingService {
  private apiUrl = environment.apiUrl;
  // The server pings an open stream every 15 seconds; a stream that got nothing for this long is gone
  private static readonly STALLED_MS = 45000;

  constructor(private apiService: ApiService, private familyMode: FamilyModeService) {}

  /**
   * Initiates a streaming request for agent response generation.
   *
   * @param conversationId - The ID of the conversation to generate a response for
   * @param aiParticipant - The name of the AI participant (default: 'Assistant')
   * @param modelId - Optional catalog model to answer with instead of the conversation's model
   * @param regenerateId - Write a new version of this stored answer (Regenerate, docs/answer_versions.md)
   * @returns An Observable that emits StreamEvent objects
   */
  streamAgentResponse(
    conversationId: string,
    aiParticipant: string = 'Assistant',
    modelId?: number,
    regenerateId?: number
  ): Observable<StreamEvent> {
    return this.stream(`${this.apiUrl}/api/message/stream-generate?ngsw-bypass=true`, {
      method: 'POST',
      headers: this.headers(),
      body: JSON.stringify({
        conversationId,
        aiParticipant,
        // Only sent to answer with another model than the conversation's
        ...(modelId !== undefined && { modelId }),
        ...(regenerateId !== undefined && { regenerateId })
      })
    });
  }

  /**
   * Follow the answer that is being written in a conversation (opened again, back to the app, or
   * after its stream broke): the same events, with what was written so far at once. Without runId
   * only an answer that still runs; with runId and after (the number of the last event this
   * browser got), the rest of that answer, also if it ended a moment ago. Fails with
   * NoAnswerRunningError when there is nothing to follow.
   */
  followAgentResponse(conversationId: string, runId?: string | null, after?: number): Observable<StreamEvent> {
    const query = new URLSearchParams({ 'ngsw-bypass': 'true' });
    if (runId) {
      query.set('runId', runId);
      query.set('after', String(after ?? 0));
    }
    return this.stream(`${this.apiUrl}/api/message/stream/${encodeURIComponent(conversationId)}?${query}`, {
      method: 'GET',
      headers: this.headers()
    });
  }

  /**
   * Stop the answer that is being written in a conversation (the Stop button: closing the stream
   * doesn't stop it). Resolves once the server stored what was written; false if it had ended.
   */
  async stopAgentResponse(conversationId: string, runId?: string | null): Promise<boolean> {
    const response = await fetch(`${this.apiUrl}/api/message/stop?ngsw-bypass=true`, {
      method: 'POST',
      headers: { ...this.headers(), 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ conversationId, ...(runId && { runId }) })
    });
    if (!response.ok) {
      throw new StreamHttpError(response.status, response.statusText);
    }
    return (await response.json()).stopped === true;
  }

  /** The headers of the answer requests: the CSRF token and family mode. */
  private headers(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    const csrfToken = this.apiService.csrfToken;
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    } else {
      console.warn('StreamingService: No CSRF token available');
    }
    // The agent leaves out hidden content while this device is in family mode
    Object.assign(headers, this.familyMode.headers());
    return headers;
  }

  /** The events of an SSE request; unsubscribing closes the connection. */
  private stream(url: string, init: RequestInit): Observable<StreamEvent> {
    return new Observable(observer => {
      const controller = new AbortController();
      const watch = { lastActivity: Date.now(), stalled: false };
      // A stream that got nothing for a while is closed and reported as stalled, so the answer is
      // followed again (a connection that died while the phone was locked doesn't always end)
      const watchdog = setInterval(() => {
        if (Date.now() - watch.lastActivity > StreamingService.STALLED_MS) {
          watch.stalled = true;
          controller.abort();
        }
      }, 5000);

      this.read(url, init, observer, controller.signal, watch).finally(() => clearInterval(watchdog));

      // Cleanup function - called when the subscription is unsubscribed
      return () => {
        clearInterval(watchdog);
        controller.abort();
      };
    });
  }

  /**
   * Internal method to handle the actual streaming connection.
   */
  private async read(
    url: string,
    init: RequestInit,
    observer: Subscriber<StreamEvent>,
    signal: AbortSignal,
    watch: { lastActivity: number; stalled: boolean }
  ): Promise<void> {
    let currentEventType: StreamEventType | null = null;
    let currentId: number | undefined;

    try {
      const response = await fetch(url, { ...init, credentials: 'include', signal });
      watch.lastActivity = Date.now();

      if (response.status === 204) {
        observer.error(new NoAnswerRunningError());
        return;
      }
      if (!response.ok) {
        throw new StreamHttpError(response.status, response.statusText);
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      // Accumulate data lines for multi-line SSE data (per SSE spec)
      let dataLines: string[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        watch.lastActivity = Date.now();  // Also the server's pings (comments) keep the stream alive

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          // SSE spec: lines can have \r\n or \n endings, trim only \r
          const cleanLine = line.endsWith('\r') ? line.slice(0, -1) : line;

          if (cleanLine.startsWith('id:')) {
            // The event's number in its answer
            const id = Number(cleanLine.slice(3).trim());
            currentId = Number.isFinite(id) ? id : undefined;
          } else if (cleanLine.startsWith('event:')) {
            // Parse the event type
            currentEventType = cleanLine.slice(6).trim() as StreamEventType;
          } else if (cleanLine.startsWith('data:') && currentEventType) {
            // Accumulate data lines - per SSE spec, strip exactly one leading space after colon
            const rawData = cleanLine.slice(5);
            const dataContent = rawData.startsWith(' ') ? rawData.slice(1) : rawData;
            dataLines.push(dataContent);
          } else if (cleanLine === '' && currentEventType && dataLines.length > 0) {
            // Blank line signals end of event - emit accumulated data
            // Per SSE spec, multiple data lines are joined with newlines
            const fullData = dataLines.join('\n');
            const data = currentEventType === 'token'
              ? fullData  // Preserve all whitespace for tokens
              : fullData.trim();  // Trim for JSON events
            const event = this.parseEvent(currentEventType, data);
            if (event) {
              if (currentId !== undefined) event.id = currentId;
              observer.next(event);
            }
            // Reset for next event
            currentEventType = null;
            currentId = undefined;
            dataLines = [];
          }
        }
      }

      // Handle any remaining data at end of stream
      if (currentEventType && dataLines.length > 0) {
        const fullData = dataLines.join('\n');
        const data = currentEventType === 'token' ? fullData : fullData.trim();
        const event = this.parseEvent(currentEventType, data);
        if (event) {
          if (currentId !== undefined) event.id = currentId;
          observer.next(event);
        }
      }

      observer.complete();
    } catch (error: any) {
      if (watch.stalled) {
        observer.error(new StreamStalledError());
      } else if (error.name !== 'AbortError') {
        // Don't report abort errors (these happen when the user cancels)
        console.error('Streaming error:', error);
        observer.error(error);
      }
    }
  }

  /**
   * Parses an SSE event into a StreamEvent object.
   */
  private parseEvent(type: StreamEventType, data: string): StreamEvent | null {
    try {
      switch (type) {
        case 'message_start':
          // Message start events contain message metadata
          return { type, data: JSON.parse(data) as MessageStartEventData };

        case 'token':
          // Token events are plain strings
          return { type, data };

        case 'step':
          // Step events are JSON AgentStep objects; a step with a known id replaces the earlier one
          return { type, data: JSON.parse(data) as AgentStep };

        case 'step_delta':
          // Text to append to the content of an earlier step
          return { type, data: JSON.parse(data) as StepDeltaEventData };

        case 'summary':
          // A new summary of the oldest messages, written before the answer
          return { type, data: JSON.parse(data) as IConversationSummary };

        case 'done':
          // Done events contain messageId, conversationId, the model and its usage
          return { type, data: JSON.parse(data) as DoneEventData };

        case 'error':
          // Error events contain an error message
          return { type, data: JSON.parse(data) as ErrorEventData };

        default:
          console.warn('Unknown event type:', type);
          return null;
      }
    } catch (e) {
      console.error('Error parsing event:', e, 'type:', type, 'data:', data);
      return null;
    }
  }
}
