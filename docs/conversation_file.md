# Conversation files (export and import)

A conversation file holds one conversation with all its messages as JSON. **Export** in a conversation's menu in the sidebar downloads one; **Settings > Import conversations** adds one or more as new conversations. Guests can export, but not import, since their conversations are deleted with the guest.

## Format (version 1)

```json
{
  "type": "advanced-llm-chat-conversation",
  "version": 1,
  "exportedAt": "2026-10-31T11:18:42.353Z",
  "conversation": {
    "name": "Rezept für Käsekuchen",
    "createdAt": "2024-04-28T15:20:16.573Z",
    "updatedAt": "2024-04-28T15:20:55.030Z"
  },
  "messages": [
    { "roleName": "system", "type": "text", "time": "2024-04-28T15:20:16.573Z", "content": "You are a helpful assistant." },
    { "roleName": "user", "type": "text", "time": "2024-04-28T15:20:50.678Z", "content": "Hey",
      "attachments": [{ "fileId": "file_1730000000000_ab12", "fileName": "notes.pdf", "fileSize": 1234, "mimeType": "application/pdf" }] },
    { "roleName": "Assistant", "type": "agent", "time": "2024-04-28T15:20:55.030Z", "content": "Hello!",
      "steps": [], "status": "complete", "modelName": "Claude Haiku 5.5", "rating": 1,
      "usage": { "inputTokens": 1113, "outputTokens": 13, "reasoningTokens": 0, "cachedInputTokens": null, "cost": 0.000118, "currency": "USD" } }
  ]
}
```

- **Messages** have no id; the order of the list is the order of the conversation (oldest first). `time` is ISO 8601; without a time zone it counts as UTC.
- **`roleName`** is `user`, `Assistant` or `system` (`assistant` is read as `Assistant`). System messages are shown as "System" but not sent to the model, which gets the app's own system prompt.
- **`type`** is `text`, `voice` (old voice messages, content as stored) or `agent`. Only agent messages have `steps`, `status`, `error`, `modelName` and `usage`; `rating` (1 or 0) can be on any message.
- **Left out:** ids, the conversation's model and agent (catalog ids belong to one server; an imported conversation uses the user's default model) and the uploaded files themselves. An attachment stays on import only if the importing user uploaded that file, so a re-import into the same account keeps them.

The models are `backend/models/conversation_file.py`; export and import are in `backend/services/conversation_file.py`.

## API

- `GET /api/conversation/{id}/export`: the conversation file of one of the user's conversations (404 otherwise).
- `POST /api/conversation/import`: body is a conversation file; returns the new conversation (201). 403 for guests, 422 for a file that doesn't match the format, 400 for an unknown role. Nothing is stored unless the whole file is valid; at most 10,000 messages.

An imported message gets its time as its id (milliseconds), like the messages the server stores itself. Ids are unique across all conversations, so an id that is taken (the same file imported twice) moves to the next free millisecond.

## Conversations of the old app (2023/24)

The app before Fessi exported a conversation as two JSON values in one file: the conversation (`id`, `summary`, `participants`, `enviorementVariables`, …) and the list of its messages (`id`, `conversationID`, `content`, `role`, `time`). `scripts/convert_legacy_conversations.py` turns them into conversation files:

```bash
python scripts/convert_legacy_conversations.py ~/old/*.json -o ~/old/converted
```

It needs only the standard library. Only the messages are converted (the summary, participants and variables are left out); empty messages and unknown roles are skipped with a note. The old files have no name, so a conversation is named after the start of its first user message, as the app names a new one (`--name` for a single file).
