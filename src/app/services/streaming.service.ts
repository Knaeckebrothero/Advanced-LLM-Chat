// src/app/services/streaming.service.ts
import { Injectable } from '@angular/core';
import { Observable, Subscriber } from 'rxjs';
import { environment } from '../environments/environment';
import { AgentStep } from '../data/objects/message';
import { IMessageUsage } from '../data/models/catalog.model';
import { ApiService } from './api.service';

/**
 * Types of events that can be received from the SSE stream
 */
export type StreamEventType = 'message_start' | 'step' | 'step_delta' | 'token' | 'done' | 'error';

/**
 * Represents an event from the SSE stream
 */
export interface StreamEvent {
  type: StreamEventType;
  data: MessageStartEventData | AgentStep | StepDeltaEventData | string | DoneEventData | ErrorEventData;
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
export interface DoneEventData {
  messageId: number;
  conversationId: string;
  modelId?: number | null;
  modelName?: string | null;
  usage?: IMessageUsage | null;
}

/**
 * Data payload for 'error' events
 */
export interface ErrorEventData {
  error: string;
}

/**
 * Service for handling Server-Sent Events (SSE) streaming from the backend.
 *
 * This service manages the connection to the streaming endpoint and provides
 * an Observable interface for consuming streaming events. It handles:
 * - Agent reasoning steps (thoughts, tool calls, observations)
 * - Token streaming for the final response
 * - Completion and error events
 */
@Injectable({ providedIn: 'root' })
export class StreamingService {
  private apiUrl = environment.apiUrl;

  constructor(private apiService: ApiService) {}

  /**
   * Initiates a streaming request for agent response generation.
   *
   * @param conversationId - The ID of the conversation to generate a response for
   * @param aiParticipant - The name of the AI participant (default: 'Assistant')
   * @param modelId - Optional catalog model to answer with instead of the conversation's model
   * @returns An Observable that emits StreamEvent objects
   */
  streamAgentResponse(
    conversationId: string,
    aiParticipant: string = 'Assistant',
    modelId?: number
  ): Observable<StreamEvent> {
    return new Observable(observer => {
      const controller = new AbortController();

      this.initiateStream(conversationId, aiParticipant, modelId, observer, controller.signal);

      // Cleanup function - called when the subscription is unsubscribed
      return () => {
        controller.abort();
      };
    });
  }

  /**
   * Internal method to handle the actual streaming connection.
   */
  private async initiateStream(
    conversationId: string,
    aiParticipant: string,
    modelId: number | undefined,
    observer: Subscriber<StreamEvent>,
    signal: AbortSignal
  ): Promise<void> {
    let currentEventType: StreamEventType | null = null;

    try {
      // Build headers with CSRF token
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };

      // Add CSRF token if available
      const csrfToken = this.apiService.csrfToken;
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken;
      } else {
        console.warn('StreamingService: No CSRF token available');
      }

      const response = await fetch(`${this.apiUrl}/api/message/stream-generate`, {
        method: 'POST',
        headers,
        credentials: 'include',
        body: JSON.stringify({
          conversationId,
          aiParticipant,
          // Only sent to answer with another model than the conversation's
          ...(modelId !== undefined && { modelId })
        }),
        signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      // Accumulate data lines for multi-line SSE data (per SSE spec)
      let dataLines: string[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          // SSE spec: lines can have \r\n or \n endings, trim only \r
          const cleanLine = line.endsWith('\r') ? line.slice(0, -1) : line;

          if (cleanLine.startsWith('event:')) {
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
              observer.next(event);
            }
            // Reset for next event
            currentEventType = null;
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
          observer.next(event);
        }
      }

      observer.complete();
    } catch (error: any) {
      // Don't report abort errors (these happen when the user cancels)
      if (error.name !== 'AbortError') {
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
