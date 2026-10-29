# Scroll Solution Implementation Plan

## Problem Statement

Current scroll behavior scrolls to the absolute bottom of the chat container, which:
1. Pushes user messages off-screen when AI starts responding
2. During streaming, only the latest words are visible (not ideal for reading)
3. Agent steps expansion doesn't intelligently adjust scroll position

**Desired behavior** (like Claude/ChatGPT):
- When user sends a message, the user message appears at the **top** of the viewport
- AI response grows below the user message
- Whitespace fills the rest of the viewport initially
- As AI response grows and fills viewport, switch to "keep bottom visible" mode
- User can scroll up to read (disables auto-scroll) - already implemented
- Agent steps expansion keeps relevant content visible

---

## Current Implementation Analysis

### Files Involved

| File | Role |
|------|------|
| `chat-ui.component.ts` | Main scroll logic, viewport management |
| `chat-ui.component.html` | Message container with `#messageContainer` ref |
| `chat-ui-message.component.ts` | Individual message, `onStepsExpandedChange()` handler |
| `agent-steps.component.ts` | Expansion panel, emits `expandedChange` event |
| `chat-state.service.ts` | `streamingMessage$` observable for AI response |

### Current Scroll Methods

```typescript
// chat-ui.component.ts (lines 250-277)

// Scrolls to absolute bottom
scrollToBottom(): void {
  this.messageContainer.nativeElement.scrollTop =
    this.messageContainer.nativeElement.scrollHeight;
}

// Checks if within 150px of bottom
isNearBottom(): boolean {
  const element = this.messageContainer.nativeElement;
  const threshold = 150;
  return element.scrollHeight - element.scrollTop - element.clientHeight < threshold;
}
```

### Scroll Triggers

1. **Message sent** (line 318): Sets `shouldScrollToBottom = true`
2. **AfterViewChecked** (line 280-297): Scrolls if message count changed
3. **Streaming subscription** (line 117-135): Scrolls every 50+ characters if at bottom

### User Scroll Intent (already implemented)

- `userIsAtBottom` flag tracks if user is at bottom
- Scrolling up disables auto-scroll
- Scrolling back to bottom re-enables auto-scroll

---

## Proposed Solution: Dynamic Anchor-Based Scrolling

### Core Concept

Instead of "scroll to bottom", use **anchor-based positioning**:

1. **Anchor element**: The user's message (or the element we want at the top)
2. **Growing element**: The AI response (streaming content)
3. **Scroll target**: Calculated based on anchor position and growing element height

### Two-Phase Scroll Strategy

```
Phase 1: ANCHOR MODE (initial)
┌─────────────────────────────┐
│ User message (anchor) ←─────│── Anchored at top with small padding
├─────────────────────────────┤
│ AI response (growing)       │
│ ...                         │
├─────────────────────────────┤
│                             │
│     [empty space]           │←── Viewport fills with whitespace
│                             │
└─────────────────────────────┘
         ↑ Input field

Phase 2: FOLLOW MODE (when content fills viewport)
┌─────────────────────────────┐
│ (user message scrolled up)  │
├─────────────────────────────┤
│ ... AI response ...         │
│ ... continues ...           │
│ ... latest content ←────────│── Auto-scroll keeps this visible
└─────────────────────────────┘
         ↑ Input field
```

### Phase Transition Logic

```typescript
// Pseudo-code for phase detection
const anchorRect = userMessageElement.getBoundingClientRect();
const growingRect = aiResponseElement.getBoundingClientRect();
const containerRect = messageContainer.getBoundingClientRect();

// Check if AI response extends below the visible viewport
const contentExceedsViewport = growingRect.bottom > containerRect.bottom;

if (contentExceedsViewport) {
  // Phase 2: Follow mode - scroll to keep bottom visible
  scrollToKeepBottomVisible();
} else {
  // Phase 1: Anchor mode - keep user message at top
  scrollToAnchorAtTop();
}
```

---

## Implementation Steps

### Step 1: Add Message Element References

Add `ViewChildren` to track message elements for anchor positioning.

```typescript
// chat-ui.component.ts

import { QueryList, ViewChildren } from '@angular/core';
import { ChatUiMessageComponent } from './chat-ui-message/chat-ui-message.component';

export class ChatUiComponent {
  @ViewChildren(ChatUiMessageComponent, { read: ElementRef })
  messageElements!: QueryList<ElementRef>;

  // Track the anchor message (last user message when generating)
  private anchorMessageIndex: number | null = null;
}
```

### Step 2: Create Scroll Service/Methods

Replace `scrollToBottom()` with intelligent positioning:

```typescript
// New scroll methods

/**
 * Scroll to position a specific message at the top of the viewport
 */
private scrollToMessageAtTop(messageIndex: number, padding: number = 16): void {
  const elements = this.messageElements.toArray();
  if (messageIndex < 0 || messageIndex >= elements.length) return;

  const messageEl = elements[messageIndex].nativeElement;
  const container = this.messageContainer.nativeElement;

  // Calculate scroll position to place message at top with padding
  const messageTop = messageEl.offsetTop;
  container.scrollTop = messageTop - padding;
}

/**
 * Check if the growing content (AI response) extends below viewport
 */
private isContentBelowViewport(): boolean {
  const container = this.messageContainer.nativeElement;
  const containerRect = container.getBoundingClientRect();

  // Get the last message element (AI response during streaming)
  const elements = this.messageElements.toArray();
  if (elements.length === 0) return false;

  const lastMessage = elements[elements.length - 1].nativeElement;
  const lastMessageRect = lastMessage.getBoundingClientRect();

  // Check if bottom of last message is below container's visible area
  return lastMessageRect.bottom > containerRect.bottom;
}

/**
 * Smart scroll that positions based on current phase
 */
private smartScroll(): void {
  if (!this.userIsAtBottom) return; // Respect user scroll intent

  if (this.anchorMessageIndex !== null && !this.isContentBelowViewport()) {
    // Phase 1: Keep anchor at top
    this.scrollToMessageAtTop(this.anchorMessageIndex);
  } else {
    // Phase 2: Follow bottom
    this.scrollToBottom();
  }
}
```

### Step 3: Modify Message Send Handler

Set anchor when user sends message:

```typescript
// chat-ui.component.ts - onMessageSent()

async onMessageSent(message: string): Promise<void> {
  if (message.trim() || this.pendingFiles.length > 0) {
    try {
      // ... existing send logic ...

      // Set anchor to the message being sent (will be last user message)
      // After DOM updates, this will be currentMessages.length - 1
      this.shouldScrollToBottom = true;
      this.userIsAtBottom = true;

      // Mark that we want anchor mode for the next AI response
      this.useAnchorMode = true;

    } catch (error) {
      console.error('Error sending message:', error);
    }
  }
}
```

### Step 4: Modify Streaming Subscription

Use smart scroll during streaming:

```typescript
// chat-ui.component.ts - ngOnInit() streaming subscription

this.destroy$.add(
  this.streamingMessage$.subscribe(streamingMsg => {
    if (streamingMsg && this.userIsAtBottom) {
      const currentContent = streamingMsg.content?.content || '';

      // Throttle scroll updates
      if (currentContent.length > this.lastStreamingContent.length + 50) {
        this.lastStreamingContent = currentContent;

        // Use smart scroll instead of scrollToBottom
        requestAnimationFrame(() => this.smartScroll());
      }
    } else if (!streamingMsg) {
      // Streaming ended - reset anchor mode
      this.lastStreamingContent = '';
      this.anchorMessageIndex = null;
      this.useAnchorMode = false;
    }
  })
);
```

### Step 5: Handle Anchor Index Calculation

Update anchor index when messages change:

```typescript
// chat-ui.component.ts - ngAfterViewChecked or messages$ subscription

private updateAnchorIndex(): void {
  if (!this.useAnchorMode) return;

  // Find the last user message index
  const messages = this.currentMessages;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].roleName === 'user') {
      this.anchorMessageIndex = i;
      break;
    }
  }
}
```

### Step 6: Handle Agent Steps Expansion

Add scroll adjustment when agent steps expand/collapse:

```typescript
// chat-ui-message.component.ts

onStepsExpandedChange(expanded: boolean): void {
  // Emit event to parent for scroll adjustment
  this.stepsExpanded.emit({ expanded, messageElement: this.elementRef.nativeElement });
}

// chat-ui.component.ts

onMessageStepsExpanded(event: { expanded: boolean, messageElement: HTMLElement }): void {
  if (!event.expanded) return; // Only handle expansion

  // After DOM updates, ensure the expanded content is visible
  requestAnimationFrame(() => {
    const container = this.messageContainer.nativeElement;
    const messageRect = event.messageElement.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();

    // If expansion pushed content below viewport, scroll to show it
    if (messageRect.bottom > containerRect.bottom) {
      const scrollAmount = messageRect.bottom - containerRect.bottom + 50; // 50px buffer
      container.scrollTop += scrollAmount;
    }
  });
}
```

---

## Alternative Approaches Considered

### Option A: CSS scroll-snap (Not Recommended)

```css
.message-container {
  scroll-snap-type: y proximity;
}
.message-row {
  scroll-snap-align: start;
}
```

**Pros**: Native browser handling
**Cons**: Fights with programmatic scrolling, unpredictable with streaming

### Option B: IntersectionObserver (Partial Use)

Could use for detecting when anchor leaves viewport, but adds complexity.

```typescript
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (!entry.isIntersecting && isStreaming) {
      // Anchor scrolled out of view, switch to follow mode
    }
  });
}, { root: messageContainer, threshold: 0 });
```

### Option C: Virtual Scrolling (Overkill)

Libraries like `@angular/cdk/scrolling` are designed for large lists, not this use case.

---

## Mobile Considerations

### Known Issues

| Issue | Platform | Impact | Solution |
|-------|----------|--------|----------|
| `getBoundingClientRect` returns wrong values after `scrollTo` | iOS Safari | Scroll calculations off | Use `requestAnimationFrame` before reading, or small timeout |
| Virtual keyboard doesn't resize layout viewport | iOS Safari | Content hidden under keyboard | Use `window.visualViewport` API |
| `position: fixed` breaks during scroll | iOS Safari | Fixed elements drift | Not using fixed positioning in scroll area (OK) |
| Rubber-banding/overscroll | iOS | Temporary incorrect scroll values | Debounce scroll calculations |

### Mobile-Safe Implementation

```typescript
/**
 * Safely get bounding rect after scroll (handles iOS Safari bug)
 */
private getBoundingRectSafe(element: HTMLElement): Promise<DOMRect> {
  return new Promise(resolve => {
    // Double RAF to ensure layout is stable (iOS Safari workaround)
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        resolve(element.getBoundingClientRect());
      });
    });
  });
}

/**
 * Get actual visible viewport height (accounts for virtual keyboard)
 */
private getVisibleViewportHeight(): number {
  // visualViewport API handles iOS virtual keyboard
  if (window.visualViewport) {
    return window.visualViewport.height;
  }
  return window.innerHeight;
}

/**
 * Check if content exceeds visible viewport (mobile-safe)
 */
private isContentBelowViewport(): boolean {
  const container = this.messageContainer.nativeElement;
  const containerRect = container.getBoundingClientRect();

  const elements = this.messageElements.toArray();
  if (elements.length === 0) return false;

  const lastMessage = elements[elements.length - 1].nativeElement;
  const lastMessageRect = lastMessage.getBoundingClientRect();

  // Use visualViewport for accurate visible area on mobile
  const visibleBottom = window.visualViewport
    ? window.visualViewport.height + window.visualViewport.offsetTop
    : containerRect.bottom;

  return lastMessageRect.bottom > visibleBottom;
}
```

### Virtual Keyboard Handling

When the virtual keyboard opens on mobile, the input field may push content up. We should:

1. **Listen to `visualViewport` resize events**:
```typescript
ngAfterViewInit() {
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', () => {
      // Keyboard opened/closed - may need to re-anchor
      if (this.useAnchorMode && this.anchorMessageIndex !== null) {
        this.smartScroll();
      }
    });
  }
}
```

2. **Debounce scroll calculations** to avoid rapid recalculations during keyboard animation:
```typescript
private scrollDebounceTimer: any = null;

private debouncedSmartScroll(): void {
  if (this.scrollDebounceTimer) {
    clearTimeout(this.scrollDebounceTimer);
  }
  this.scrollDebounceTimer = setTimeout(() => {
    this.smartScroll();
  }, 50); // 50ms debounce
}
```

### Touch Scroll vs Mouse Scroll

The existing `onScroll` event handler works identically for touch and mouse. However, touch scrolling has momentum (inertia), so:

- **Scroll end detection**: May need to wait for momentum to stop before making decisions
- **User intent**: A small touch scroll shouldn't immediately disable auto-scroll

```typescript
// More forgiving threshold on mobile for "near bottom" detection
private isNearBottom(): boolean {
  const element = this.messageContainer.nativeElement;
  // Larger threshold on mobile to account for touch momentum
  const threshold = this.uiState.isMobile ? 200 : 150;
  return element.scrollHeight - element.scrollTop - element.clientHeight < threshold;
}
```

### CSS Considerations for Mobile

```scss
// Prevent iOS rubber-banding from affecting scroll container
.message-container {
  -webkit-overflow-scrolling: touch; // Smooth momentum scrolling
  overscroll-behavior: contain; // Prevent scroll chaining

  // Ensure touch targets are large enough
  @media (max-width: 768px) {
    padding-bottom: 100px; // Extra space for keyboard
  }
}
```

### Testing on Mobile

**Must test on actual devices** (not just browser DevTools):
- iPhone Safari (most problematic)
- Android Chrome
- Samsung Internet

Key scenarios:
1. Send message with keyboard open
2. Scroll during AI streaming
3. Expand agent steps panel
4. Rotate device during streaming

---

## Testing Scenarios

1. **Send short message, short AI response**
   - User message stays at top
   - AI response visible below
   - Whitespace fills rest of viewport

2. **Send message, long AI response (streaming)**
   - Initially: user message at top
   - As response grows past viewport: switches to follow mode
   - Final state: can scroll up to see user message

3. **User scrolls up during streaming**
   - Auto-scroll disables (existing behavior)
   - User can read earlier content
   - Scrolling back to bottom re-enables

4. **Agent steps expansion**
   - Expanding steps scrolls to show expanded content
   - Doesn't disrupt reading position unnecessarily

5. **Multiple messages in quick succession**
   - Each new user message becomes the anchor
   - Previous anchors are released

---

## File Changes Summary

| File | Changes |
|------|---------|
| `chat-ui.component.ts` | Add `smartScroll()`, `scrollToMessageAtTop()`, `isContentBelowViewport()`, anchor tracking |
| `chat-ui.component.html` | Add message element refs, event binding for steps expansion |
| `chat-ui-message.component.ts` | Emit `stepsExpanded` event with element reference |

---

## Implementation Priority

1. **Phase 1**: Basic anchor positioning (user message at top on send)
2. **Phase 2**: Smart scroll transition (anchor → follow when content fills viewport)
3. **Phase 3**: Agent steps expansion handling
4. **Phase 4**: Edge cases and polish (animation smoothing, mobile behavior)

---

## References

- [React Native Streaming Message List](https://github.com/bacarybruno/react-native-streaming-message-list) - ChatGPT/Claude-like scroll behavior
- [MDN: getBoundingClientRect()](https://developer.mozilla.org/en-US/docs/Web/API/Element/getBoundingClientRect)
- [MDN: scrollIntoView()](https://developer.mozilla.org/en-US/docs/Web/API/Element/scrollIntoView)
- [CSS overflow-anchor](https://css-tricks.com/almanac/properties/o/overflow-anchor/) - Browser scroll anchoring
- [Angular Chat Scroll Position](https://neoito.com/blog/how-to-maintain-scroll-position-in-angular-chat-app/)
