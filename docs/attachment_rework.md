# Attachment System Rework

## Problem Statement

The current file attachment system exposes raw file IDs (e.g., `file_1767214027759_af42f342a75c9715`) directly to the LLM through placeholder text. This causes several issues:

1. **LLM Extraction Errors**: Long, complex IDs are prone to transcription mistakes when the model extracts them from conversation history to pass to tools
2. **No Access Control**: The current system doesn't validate that a user has permission to access a file - anyone with a file ID could potentially retrieve it
3. **No Centralized Metadata**: File descriptions, dimensions, and other metadata are scattered or not stored at all
4. **Poor UX for File References**: Users cannot easily reference previously uploaded files in their messages

## Goals

1. **Simplify LLM Interaction**: Replace complex file IDs with short, memorable aliases that are easy for the model to copy and use
2. **Enforce Security**: Ensure files can only be accessed by their owner within the correct conversation context
3. **Centralize File Metadata**: Create a single source of truth for all file-related information
4. **Enable File References**: Allow users to reference files using `@filename` syntax in the frontend
5. **Support Future Features**: Design for artifacts, shared files, and cross-conversation file access

---

## Feature Overview

### 1. File Alias System

Instead of showing the LLM raw file IDs, we introduce human-readable **aliases** that are unique within a conversation:

| Current (problematic) | New (alias-based) |
|-----------------------|-------------------|
| `[Attachment: photo.jpg (fileId: file_1767214027759_af42f342a75c9715)]` | `[Attachment: battery_disposal_photo.jpg]` |
| `get_file_content(file_id="file_1767214027759_af42f342a75c9715")` | `get_file_content(filename="battery_disposal_photo.jpg")` |

**Alias Generation Rules:**
- **Images**: Vision model generates a descriptive name based on image content (e.g., `rusty_car_battery.jpg`, `recycling_bin_contents.png`)
- **Documents**: Preserve original filename or use extracted title (e.g., `tax_return_2024.pdf`, `meeting_notes.docx`)
- **Audio**: Use original filename or generate from transcript (e.g., `voice_memo_about_recycling.mp3`)
- **Collision Handling**: If an alias already exists in the conversation, append a number (e.g., `photo.jpg` → `photo_2.jpg`)

### 2. Attachments Table

Replace the `file_description_cache` table with a comprehensive `attachments` table:

**Core Fields:**
- `id` - Primary key (auto-increment or UUID)
- `file_id` - Internal filesystem identifier (the current long ID format)
- `user_id` - Owner of the file (foreign key to users)
- `conversation_id` - Conversation this file belongs to (foreign key to conversations)
- `alias` - LLM-friendly filename (unique within conversation)
- `original_name` - Original filename as uploaded by user

**Metadata Fields:**
- `mime_type` - File MIME type
- `file_size` - Size in bytes
- `description` - AI-generated description (cached)
- `description_query` - Query used to generate description (if any)
- `dimensions` - For images: "1920x1080" format
- `page_count` - For PDFs: number of pages
- `duration_seconds` - For audio/video: length
- `transcript` - For audio: transcribed text
- `preview_base64` - Optional thumbnail for sync to frontend

**Tracking Fields:**
- `created_at` - Upload timestamp
- `updated_at` - Last modification timestamp
- `accessed_at` - Last access timestamp (for cleanup policies)

### 3. Secure File Retrieval

The `get_file_content` tool will be updated to:

1. Accept `filename` (alias) instead of raw `file_id`
2. Require `conversation_id` context (injected automatically, not from LLM)
3. Look up the actual `file_id` from the attachments table
4. Validate that the file belongs to the current user and conversation
5. Return content with proper error messages if access is denied

**Security Model:**
- Files are scoped to `(user_id, conversation_id)` pairs
- No file can be accessed outside its owning conversation (unless explicitly shared - future feature)
- The LLM never sees or handles the internal file IDs
- Tool injection provides conversation context automatically

### 4. Frontend File References

Enable `@filename` syntax for users to reference files in messages:

**Behavior:**
- Typing `@` shows autocomplete dropdown with files from current conversation
- Selecting a file inserts a reference token (e.g., `@battery_photo.jpg`)
- Backend recognizes references and provides file context to the LLM
- References are visually distinct in the message (pill/chip styling)

**Benefits:**
- Users can easily refer to files from earlier in the conversation
- Reduces need to re-upload files
- Creates explicit file context for the LLM

### 5. Placeholder Format Update

Update how file attachments appear in conversation history:

**Current Format:**
```
[Attachment: report.pdf (fileId: file_1767214027759_af42f342a75c9715) - 5 pages, PDF document]
```

**New Format:**
```
[File: quarterly_report.pdf - 5 pages, PDF document]

To access this file's content, use: get_file_content(filename="quarterly_report.pdf")
```

**Benefits:**
- Cleaner, more readable format
- Explicit instruction on how to access the file
- No complex IDs to misparse

---

## Migration Considerations

### Data Migration
- Existing files in the filesystem remain unchanged (same `file_id` format)
- Create attachment records for existing files based on message content
- Generate aliases retroactively (may require re-processing for AI-generated names)

### Backward Compatibility
- Support both old `file_id` and new `filename` parameters during transition
- Gradually deprecate `file_id` parameter in tool calls
- Frontend must handle both old and new message formats

### Filesystem Changes
- No changes required to how files are stored on disk
- The `file_id` continues to serve as the filesystem path identifier
- Only the LLM-facing interface changes

---

## Future Extensions

### Cross-Conversation Files
- Allow files to be "shared" to other conversations
- Maintain access control through explicit sharing records

### Artifacts System
- Code artifacts, generated files, exports
- Same alias and access control patterns
- Distinguished by `artifact_type` field

### File Versioning
- Track edits to artifacts
- Link versions together
- Enable rollback functionality

### Collaborative Access
- Share files with other users
- Team/organization file libraries
- Permission levels (view, edit, delete)

---

## Success Metrics

1. **Zero LLM extraction errors** for file references in tool calls
2. **No unauthorized file access** attempts succeed
3. **User adoption** of `@filename` references
4. **Reduced support tickets** related to "file not found" errors

---

## Open Questions

1. **Alias uniqueness scope**: Should aliases be unique per-conversation or globally per-user?
   - *Recommendation*: Per-conversation, as this matches the mental model of "files in this chat"

2. **AI naming cost**: Should we always generate AI names or only on-demand?
   - *Recommendation*: Generate on upload for images (already calling vision API), preserve original for documents

3. **Orphan file cleanup**: How do we handle files in conversations that are deleted?
   - *Recommendation*: Soft delete with grace period, then hard delete

4. **Maximum files per conversation**: Should we limit the number of attachments?
   - *Recommendation*: Yes, with configurable limit (default: 50) to prevent alias collision issues

5. **Rename functionality**: Should users be able to rename file aliases?
   - *Recommendation*: Yes, with UI in file preview dialog

---
---

# Tool Error Handling

## Problem Statement

When the LLM provides incorrect parameters to tools (e.g., a filename that doesn't exist), the error messages are not helpful enough for the model to self-correct.

## Goals

1. **Clear Error Messages**: Return actionable error messages that help the LLM recover
2. **Available Options**: When a file isn't found, list available files in the conversation
3. **Graceful Degradation**: Don't crash the agent loop on bad input

## Implementation

### File Tool Error Responses

When `get_file_content` receives an invalid filename:

```
[Error: No file named "batteryphoto.jpg" found in this conversation]

Available files in this conversation:
- battery_disposal_photo.jpg (image, uploaded 2 messages ago)
- recycling_guide.pdf (document, 5 pages)
- voice_note.mp3 (audio, 45 seconds)

Please try again with one of the available filenames.
```

### Error Categories

| Error Type | Response Format |
|------------|-----------------|
| File not found | List available files with brief descriptions |
| Access denied | "You don't have access to this file" (no details to prevent enumeration) |
| File corrupted/missing | "This file is no longer available. It may have been deleted." |
| Invalid parameters | Explain what's wrong and show expected format |

---
---

# Guest User Limitations

## Problem Statement

Guest users currently have the same capabilities as registered users, which:
- Increases API costs
- Allows abuse of the system
- Provides no incentive to register

## Goals

1. **Cost Control**: Limit resource-intensive operations for guests
2. **Abuse Prevention**: Prevent guests from running expensive agent loops
3. **Registration Incentive**: Give users a reason to create an account

## Limitations

### Reasoning Steps Limit

| User Type | Max Steps per Message | Max Tool Calls |
|-----------|----------------------|----------------|
| Guest | 10 | 5 |
| Registered | 25 | 15 |
| Premium (future) | Unlimited | Unlimited |

**Behavior when limit reached:**
- Agent stops reasoning and generates best response with available information
- User sees message: "Reasoning limit reached. Register for extended capabilities."

### Reasoning Level Tiers

| User Type | Available Levels |
|-----------|-----------------|
| Guest | Low only |
| Registered | Low, Medium |
| Premium (future) | Low, Medium, High |

**Reasoning levels affect:**
- Model used (e.g., smaller model for Low, larger for High)
- Token limits for context
- Tool complexity available

### Other Guest Limitations

- **Conversations**: Max 5 active conversations
- **Messages per conversation**: Max 50
- **File uploads**: Max 3 files per conversation, 5MB each
- **TTS**: Disabled or limited
- **Message history**: 7-day retention only

---
---

# Authentication Rework

## Problem Statement

Current authentication is minimal:
- Guest accounts show ugly placeholder emails (e.g., `697438753953guest@guest.com`)
- No real login system exists
- No way to recover/persist accounts across devices

## Goals

1. **Clean Guest UX**: Show "Login" button instead of fake guest email
2. **Passwordless Auth**: Email-based login with magic codes
3. **Dev Mode**: Bypass email verification for development
4. **Account Persistence**: Users can access their data from any device

---

## Feature Overview

### 1. Guest Account Display

**Current:**
```
Sidebar shows: 697438753953guest@guest.com
```

**New:**
```
Sidebar shows: [Login] button
Header shows: "Guest" badge with "Login to save your chats" tooltip
```

### 2. Login Screen Redesign

**Current State:**
- Minimal/non-existent login UI
- No clear path from guest to registered user

**New Design:**

```
┌─────────────────────────────────────────┐
│                                         │
│            🗑️ Fessi                      │
│     Your Waste Disposal Assistant       │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │  📧 Enter your email            │   │
│  └─────────────────────────────────┘   │
│                                         │
│       [ Send Login Code ]               │
│                                         │
│  ─────────── or ───────────            │
│                                         │
│       [ Continue as Guest ]             │
│                                         │
│  By continuing, you agree to our        │
│  Terms of Service and Privacy Policy    │
│                                         │
└─────────────────────────────────────────┘
```

**Code Entry Screen:**

```
┌─────────────────────────────────────────┐
│                                         │
│         Check your email 📬             │
│                                         │
│  We sent a 6-digit code to:             │
│  user@example.com                       │
│                                         │
│  ┌───┬───┬───┬───┬───┬───┐            │
│  │ _ │ _ │ _ │ _ │ _ │ _ │            │
│  └───┴───┴───┴───┴───┴───┘            │
│                                         │
│       [ Verify Code ]                   │
│                                         │
│  Didn't receive it? [Resend]            │
│  [← Use different email]                │
│                                         │
└─────────────────────────────────────────┘
```

### 3. Email Login Flow

1. User enters email address
2. Backend generates 6-digit code, stores with expiry (10 minutes)
3. Backend sends email with code (and magic link as alternative)
4. User enters code OR clicks magic link
5. Backend validates code, creates session
6. Frontend receives auth token, transitions from guest to authenticated

**Email Template:**
```
Subject: Your Fessi Login Code: 123456

Hi!

Your login code is: 123456

This code expires in 10 minutes.

Or click here to login instantly: [Magic Link]

If you didn't request this, you can ignore this email.

- The Fessi Team
```

### 4. Dev Mode

**Environment Variable:**
```
AUTH_DEV_MODE=true
```

**Behavior when enabled:**
- Any email address is accepted without sending actual email
- Code is always `000000` (or shown in console)
- Magic links work immediately
- Useful for local development and testing

**Security:**
- Only works when `AUTH_DEV_MODE=true` AND `USE_DEV_CERTS=true`
- Logged prominently at startup: "⚠️ AUTH DEV MODE ENABLED - DO NOT USE IN PRODUCTION"

### 5. Guest to User Migration

When a guest logs in:
1. Check if email already has an account
2. If yes: Offer to merge guest conversations into existing account
3. If no: Create new account, migrate all guest data to it
4. Delete guest account after successful migration

**Migration Dialog:**
```
┌─────────────────────────────────────────┐
│                                         │
│  Welcome back! 👋                       │
│                                         │
│  You have 3 conversations as a guest.   │
│  Would you like to keep them?           │
│                                         │
│  [ Keep Guest Chats ]  [ Start Fresh ]  │
│                                         │
└─────────────────────────────────────────┘
```

---
---

# Multi-User Frontend Isolation

## Problem Statement

The frontend currently doesn't properly isolate data between users:
- IndexedDB may contain data from previous user sessions
- Switching accounts could expose another user's messages
- No clear "logout" that clears local data

## Goals

1. **Data Isolation**: Each user's data is completely separate
2. **Clean Logout**: Logging out removes all local traces
3. **Account Switching**: Support multiple accounts without data leakage

## Implementation

### IndexedDB Namespacing

**Current:**
```
Database: fessi_chat
Tables: conversations, messages, settings
```

**New:**
```
Database: fessi_chat
Tables:
  - conversations (with user_id column, indexed)
  - messages (with user_id column, indexed)
  - settings (keyed by user_id)
  - active_session (single row with current user_id)
```

**Query Pattern:**
All queries filter by `user_id` from active session:
```typescript
// Before
db.conversations.toArray()

// After
db.conversations.where('userId').equals(currentUserId).toArray()
```

### Logout Behavior

**Soft Logout (default):**
- Clears session token
- Keeps data in IndexedDB (for easy re-login)
- Shows login screen

**Hard Logout ("Logout and clear data"):**
- Clears session token
- Deletes all data for this user from IndexedDB
- Clears any cached files/previews
- Shows login screen

### Account Switching

**Flow:**
1. User clicks account menu → "Switch Account"
2. Current session is preserved (soft logout)
3. Login screen appears
4. User logs in with different account
5. New user's data loads (or syncs from backend)

**Visual Indicator:**
- Show colored avatar/initial based on user
- Different accent color per account (optional)

### Sync Considerations

When user logs in on new device:
1. Local IndexedDB is empty for this user
2. Fetch conversation list from backend
3. Lazy-load messages as user opens conversations
4. Cache locally for offline access

---
---

# Open Questions (All Features)

## Authentication

6. **Email provider**: Which service for sending login emails? (SendGrid, AWS SES, self-hosted?)
   - *Consideration*: Cost, deliverability, setup complexity

7. **Session duration**: How long before requiring re-authentication?
   - *Recommendation*: 30 days for remembered devices, 24 hours for "don't remember me"

8. **Rate limiting login attempts**: How many codes can be requested per email per hour?
   - *Recommendation*: 3 codes per email per hour, 10 per IP per hour

## Guest Limitations

9. **Limit messaging**: Should guests see limits before hitting them?
   - *Recommendation*: Yes, show "5/10 reasoning steps used" during generation

10. **Grace period**: Should new guests get a "trial" with higher limits?
    - *Recommendation*: First conversation gets registered-user limits as taste

## Frontend Isolation

11. **Data retention on logout**: Keep data for how long after soft logout?
    - *Recommendation*: Until hard logout or 30 days of inactivity

12. **Conflict resolution**: What if local and server data diverge?
    - *Recommendation*: Server wins, with option to export local data first
