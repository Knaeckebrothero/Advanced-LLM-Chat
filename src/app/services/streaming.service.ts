// src/app/services/streaming.service.ts
import { Injectable } from '@angular/core';
import { Observable, Subscriber } from 'rxjs';
import { environment } from '../environments/environment';
import { AgentStep } from '../data/objects/message';
import { ApiService } from './api.service';

/**
 * Types of events that can be received from the SSE stream
 */
export type StreamEventType = 'step' | 'token' | 'done' | 'error';

/**
 * Represents an event from the SSE stream
 */
export interface StreamEvent {
  type: StreamEventType;
  data: AgentStep | string | DoneEventData | ErrorEventData;
}

/**
 * Data payload for 'done' events
 */
export interface DoneEventData {
  messageId: number;
  conversationId: string;
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
   * @returns An Observable that emits StreamEvent objects
   */
  streamAgentResponse(
    conversationId: string,
    aiParticipant: string = 'Assistant'
  ): Observable<StreamEvent> {
    return new Observable(observer => {
      const controller = new AbortController();

      this.initiateStream(conversationId, aiParticipant, observer, controller.signal);

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
          aiParticipant
        }),
        signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmedLine = line.trim();

          if (trimmedLine.startsWith('event:')) {
            // Parse the event type
            currentEventType = trimmedLine.slice(6).trim() as StreamEventType;
          } else if (trimmedLine.startsWith('data:') && currentEventType) {
            // Parse and emit the event data
            const data = trimmedLine.slice(5).trim();
            const event = this.parseEvent(currentEventType, data);
            if (event) {
              observer.next(event);
            }
            // Reset event type after processing
            currentEventType = null;
          }
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
        case 'token':
          // Token events are plain strings
          return { type, data };

        case 'step':
          // Step events are JSON AgentStep objects
          return { type, data: JSON.parse(data) as AgentStep };

        case 'done':
          // Done events contain messageId and conversationId
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
