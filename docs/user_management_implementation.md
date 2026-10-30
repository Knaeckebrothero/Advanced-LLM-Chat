# Guest User Management Implementation

## Issue

When visiting the application for the first time, users are shown a login screen instead of being able to use the app immediately. The current authentication flow has a race condition where the `AuthGuard` checks for a user before the automatic guest session creation completes.

Additionally, the guest system lacks proper boundaries - guests can use the app indefinitely without any incentive to create an account, and guest data is stored on the backend (which is unnecessary and wasteful).

## Solution / Goal

Transform the guest experience into a "taste test" that:

1. **Immediate access**: Users start as guests automatically - no login screen on first visit
2. **Limited interaction**: Guests can send ONE message per conversation, then must login to continue
3. **Local-only storage**: Guest data lives only in IndexedDB - backend generates responses but doesn't persist
4. **Seamless migration**: On login, local guest conversations automatically sync to the new account

This creates a frictionless onboarding flow while encouraging account creation for continued use.

## Current Architecture

### What Works
- Guest sessions with IP-based rate limiting (5 sessions per IP / 3 hours)
- Guest session timeout (6 hours, configurable)
- Guest ID `0` - not a real user in the database (perfect for local-only storage)
- Ownership verification bypassed for guests
- Sync engine preserves local-only conversations

### What Needs Change
- `AuthGuard` has race condition with auth initialization
- IP-only rate limiting easily bypassed with VPNs (add browser fingerprinting)
- Backend persists messages for guests (should skip)
- No message limit per conversation for guests
- No UI to indicate guest limitations
- Sync engine doesn't upload local conversations on login

## Implementation Plan

### Phase 1: Fix Auth Guard Race Condition
**File**: `src/app/auth/auth.guard.ts`

Modify the guard to wait for auth initialization before checking user state:
```typescript
canActivate(): Observable<boolean | UrlTree> {
  return from(this.authService.initializeAuth()).pipe(
    switchMap(() => this.authService.currentUser$.pipe(take(1))),
    map(user => user ? true : this.router.createUrlTree(['/login']))
  );
}
```

### Phase 1.5: Add Browser Fingerprinting to Guest Rate Limiting

**Problem**: IP-only rate limiting is easily bypassed with VPNs, proxies, or TOR. Major AI providers (OpenAI, Google) use multi-dimensional identification combining IP with device fingerprinting.

**Solution**: Use [FingerprintJS](https://github.com/fingerprintjs/fingerprintjs) (open source) to generate a stable device identifier. Rate limit by (IP + fingerprint) tuple.

**Files**:
- `src/app/auth/auth.service.ts` - Generate fingerprint on guest login
- `src/app/models/auth.ts` - Add fingerprint to request model
- `backend/models/auth.py` - Add fingerprint field
- `backend/api/auth.py` - Use composite key for rate limiting
- `backend/database/tables.py` - Update guest_usage table
- `backend/database/db.py` - Update guest usage queries

#### Frontend Changes

**Install FingerprintJS**:
```bash
npm install @fingerprintjs/fingerprintjs
```

**Generate fingerprint** (`src/app/auth/auth.service.ts`):
```typescript
import FingerprintJS from '@fingerprintjs/fingerprintjs';

private async getDeviceFingerprint(): Promise<string> {
  try {
    const fp = await FingerprintJS.load();
    const result = await fp.get();
    return result.visitorId;
  } catch (error) {
    // Fallback: generate random ID stored in localStorage
    let fallback = localStorage.getItem('device_id');
    if (!fallback) {
      fallback = crypto.randomUUID();
      localStorage.setItem('device_id', fallback);
    }
    return fallback;
  }
}

// Update autoGuestLogin to include fingerprint
private async autoGuestLogin(): Promise<void> {
  const ip = await this.getClientIp();
  const fingerprint = await this.getDeviceFingerprint();

  const response = await firstValueFrom(
    this.http.post<LoginResponse>(`${environment.apiUrl}/api/auth/guest-login`, {
      ip_address: ip,
      device_fingerprint: fingerprint  // NEW
    })
  );
  // ...
}
```

#### Backend Changes

**Update request model** (`backend/models/auth.py`):
```python
class GuestLoginRequest(BaseModel):
    ip_address: str
    device_fingerprint: str | None = None  # Optional for backward compatibility
```

**Update table** (`backend/database/tables.py`):
```python
guest_usage = Table(
    'guest_usage',
    metadata,
    Column('ip_address', Text, nullable=False),
    Column('device_fingerprint', Text, nullable=False, server_default='unknown'),
    Column('request_count', Integer, nullable=False),
    Column('last_request_at', DateTime, nullable=False),
    PrimaryKeyConstraint('ip_address', 'device_fingerprint')  # Composite key
)
```

**Update rate limiting logic** (`backend/api/auth.py`):
```python
@router.post("/guest-login")
async def guest_login(request: GuestLoginRequest, req: Request, response: Response):
    ip_address = request.ip_address
    fingerprint = request.device_fingerprint or "unknown"

    # Rate limit by (IP + fingerprint) tuple
    usage = db.get_guest_usage(ip_address, fingerprint)

    if usage:
        # ... existing rate limit logic
    else:
        db.increment_guest_usage(ip_address, fingerprint)

    # ... rest of login logic
```

**Update database methods** (`backend/database/db.py`):
```python
def get_guest_usage(self, ip_address: str, fingerprint: str = "unknown") -> dict | None:
    query = select(guest_usage).where(
        and_(
            guest_usage.c.ip_address == ip_address,
            guest_usage.c.device_fingerprint == fingerprint
        )
    )
    # ...

def increment_guest_usage(self, ip_address: str, fingerprint: str = "unknown"):
    # Upsert with composite key
    # ...
```

#### Migration

Add a migration script to update existing `guest_usage` table:
```sql
-- Add fingerprint column with default for existing rows
ALTER TABLE guest_usage ADD COLUMN device_fingerprint TEXT NOT NULL DEFAULT 'unknown';

-- Drop old primary key and create composite
ALTER TABLE guest_usage DROP CONSTRAINT guest_usage_pkey;
ALTER TABLE guest_usage ADD PRIMARY KEY (ip_address, device_fingerprint);
```

### Phase 2: Backend - Skip Persistence for Guests
**File**: `backend/api/messages.py`

In `stream_generate()`, wrap the database calls with a guest check:

```python
# Around line 1076 - only save for authenticated users
if not current_user.get("is_guest", False):
    db.create_agent_message(
        message_id=message_id,
        conversation_id=request_body.conversationId,
        ...
    )
```

Also skip conversation history lookup from DB for guests (they won't have any).

### Phase 3: Frontend - Guest Message Limit Tracking
**Files**:
- `src/app/data/db-schema.ts` - Add guest metadata store
- `src/app/data/db.service.ts` - Add methods to track guest message count
- `src/app/services/chat.service.ts` - Check limit before sending

Track per-conversation message count for guests:
```typescript
interface GuestConversationMeta {
  conversationId: string;
  messageCount: number;  // Increment after AI response
  locked: boolean;       // True after first AI response
}
```

### Phase 4: Frontend - Locked Input UI
**Files**:
- `src/app/chat-ui/chat-ui-inputfield/chat-ui-inputfield.component.ts`
- `src/app/chat-ui/chat-ui-inputfield/chat-ui-inputfield.component.html`
- `src/app/chat-ui/chat-ui-inputfield/chat-ui-inputfield.component.scss`

When conversation is locked for guest:
- Blur/disable the input field
- Show overlay with "Login to continue chatting" message
- Add login button that navigates to `/login`

```html
<div class="guest-lock-overlay" *ngIf="isGuestLocked">
  <div class="lock-message">
    <mat-icon>lock</mat-icon>
    <span>{{ 'Login to continue chatting' | translate }}</span>
    <button mat-raised-button color="primary" (click)="navigateToLogin()">
      {{ 'Login' | translate }}
    </button>
  </div>
</div>
```

### Phase 5: Sync Engine - Upload Guest Conversations on Login
**Files**:
- `src/app/repositories/conversation.repository.ts`
- `src/app/services/api.service.ts`
- `backend/api/conversations.py` (if needed)

On login (after `mockLogin` or future OAuth):
1. Find local conversations with no server counterpart
2. POST them to backend with new user ID
3. Backend creates conversations owned by the logged-in user
4. Continue with normal sync

```typescript
// In sync engine, after login detected
async uploadLocalConversations(): Promise<void> {
  const localConversations = await this.dbService.getAllConversations();
  const serverConversations = await this.apiService.getConversations();
  const serverIds = new Set(serverConversations.map(c => c.id));

  for (const local of localConversations) {
    if (!serverIds.has(local.id)) {
      // Upload conversation and its messages
      await this.apiService.createConversation(local);
      const messages = await this.dbService.getMessagesByConversationId(local.id);
      await this.apiService.uploadMessages(local.id, messages);
    }
  }
}
```

## Data Flow Diagram

```
First Visit (Guest)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  AuthGuard waits for initializeAuth()               │
│  → autoGuestLogin() creates guest session           │
│  → User sees chat immediately (no login screen)     │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Guest sends first message                          │
│  → Message saved to IndexedDB only                  │
│  → Backend generates response (no persistence)      │
│  → Response saved to IndexedDB                      │
│  → Input field locked with "Login to continue"      │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Guest clicks login                                 │
│  → Authenticates (mock/OAuth)                       │
│  → Gets real user ID                                │
│  → Sync engine uploads local conversations          │
│  → Input unlocked, full access granted              │
└─────────────────────────────────────────────────────┘
```

## Testing Checklist

- [ ] First visit shows chat, not login screen
- [ ] Guest can send one message and receive AI response
- [ ] After first response, input is locked with login prompt
- [ ] Guest can create multiple conversations (each with 1 message limit)
- [ ] Backend doesn't store guest messages (check DB)
- [ ] After login, guest conversations appear in account
- [ ] After login, input is unlocked
- [ ] Existing logged-in users unaffected
- [ ] Rate limiting still works for guests
- [ ] Browser fingerprint is generated and sent with guest login
- [ ] Same device + different VPN still hits rate limit (fingerprint works)
- [ ] Different device + same IP gets separate rate limit allowance

## Files to Modify

| File | Change |
|------|--------|
| `src/app/auth/auth.guard.ts` | Wait for auth init |
| `src/app/auth/auth.service.ts` | Add fingerprint generation |
| `backend/models/auth.py` | Add device_fingerprint field |
| `backend/api/auth.py` | Use (IP + fingerprint) composite key |
| `backend/database/tables.py` | Update guest_usage table schema |
| `backend/database/db.py` | Update guest usage query methods |
| `backend/api/messages.py` | Skip persistence for guests |
| `src/app/data/db-schema.ts` | Add guest metadata store |
| `src/app/data/db.service.ts` | Guest message tracking methods |
| `src/app/services/chat.service.ts` | Check message limit |
| `src/app/chat-ui/chat-ui-inputfield/*` | Locked input UI |
| `src/app/repositories/sync-engine.service.ts` | Upload on login |
| `src/app/services/api.service.ts` | Bulk upload methods |
| `package.json` | Add @fingerprintjs/fingerprintjs dependency |

## Future Considerations

- Increase message limit (e.g., 3 messages) if conversion rate is too low
- Add "Continue as guest" option with extended limits for returning visitors
- Track guest-to-user conversion metrics
- Consider storing guest session ID to restore conversations on return visit
