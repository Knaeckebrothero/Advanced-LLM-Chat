# Files of a conversation

Every file in the chat is handled the same way, whether the user uploaded it or a tool created it (an image an MCP server generated, for example). It is stored once, belongs to one conversation, and the agent of that conversation reaches it through three tools: `list_files`, `read_file` and `show_file`.

- **Stored:** in `FILES_DIR` as `<file ID><extension>`, with a row in `uploaded_files`. A file ID is `file_<milliseconds>_<hex>`. At most 10 MB per file.
- **Owner:** the user who uploaded it, or the user a tool created it for. Only the owner gets it from the files API.
- **Conversation:** the one it was attached or created in. Only that conversation's agent sees it. A file belongs to one conversation.

`backend/services/file_store.py` is the store; `backend/services/tools/file_tools.py` has the tools; `backend/services/mcp/media.py` gets the media out of MCP tool results.

## How a file gets its conversation

- **Uploads:** `POST /api/files/upload` stores the file with its name, type, size (and pixels, for images) for the uploader, in no conversation yet. When the message that attaches it is stored (`db.create_message()`, also a conversation import), the file gets that conversation and message (`_link_message_files()` in `backend/database/db.py`). Only files of the conversation's owner are linked, and only ones that are in no conversation yet: the first conversation keeps the file.
- **Files of tools:** `file_store.save_tool_file()` stores them straight into the conversation of the answer, with the answer's message id, the tool's title (`origin`) and the call's arguments (`details`, cut at 2000 characters), so a later answer can tell how an image was made. They are named `<server slug>-<n>.<ext>` (`civitai-1.png`), unique in the conversation.
- **Deleted messages:** when a message is deleted (alone, or with the messages after an edited one), its files leave the conversation: the agent no longer sees them. The files themselves stay, and their owner can still open them.

Databases from before files had a conversation are migrated by the run that adds `uploaded_files.conversation_id` (the backend's start, or `app_init --prod`): `backfill_file_conversations()` gives every file the conversation of the oldest message that attaches it.

## The agent's tools

The tool group `files` (`TOOL_GROUPS` in `backend/llm/tools.py`). The tools are built per answer for the user, the conversation and the model; none of these is an argument the model can pass. Files of other conversations and other users are "not found", like missing ones.

| Tool | What it does |
|---|---|
| `list_files()` | The conversation's files, oldest first: name, type, pixels, size, where each comes from ("uploaded by the user", "created by Civitai: Run step") and when |
| `read_file(file, query?, pages?)` | A file's content: text, a PDF's extracted text and page descriptions (`pages` for some of them), an audio transcript. **Images:** a model that takes images (`supports_vision`) gets the image itself, scaled to at most 1568 pixels; a text-only model gets a description from the vision helper (`VISION_MODEL`), or its answer to `query`. For a file a tool made, the result ends with the arguments it was made with |
| `show_file(files)` | Shows files to the user above the text of the answer: images large, other files as a card. The result carries them as `shownFiles` (below) |

A file is named by its name (case doesn't matter) or by its file ID; when several files have the same name, `list_files` shows their IDs and the name alone is refused.

What the model sees without calling a tool is unchanged: the attachments of the latest user message are in the message (images only for models that take them), earlier ones are placeholders (`[Attachment: report.pdf (fileId: …)]`). Earlier answers go back with their tool calls and results (`docs/model_catalog_api.md`, "Tool calls of earlier answers"), so the model sees that a tool saved `civitai-1.png` and that it read it; the image itself is not sent again (below), and `list_files` finds it in any later turn.

### Images in tool results (`ToolText.images`)

A tool returns an image to the model as `ToolText(text, images=[image_url part])`. The agent loop turns that into a tool message with a content list (`tool_message_content()`), and the adapters put the image where their API takes it:

- **Anthropic:** inside the `tool_result` block.
- **OpenAI-compatible:** a tool message only takes text, so the images of a model call's tool results follow them in one user message (`prepare_messages()` in `backend/llm/openai_chat.py`), marked as not from the user.

The image goes to the model once, in the answer the tool ran in. In later turns the result's text ends with a note in its place (`images_note()` in `backend/llm/tool_record.py`): the model saw the image then, and calls `read_file` again to look once more.

## Files from MCP servers

`backend/services/mcp/tools.py` keeps the binary content of a tool's result as files of the conversation (at most 20 per result) and tells the model their names in place of the content: `[Image saved as file "civitai-1.png" (1024×1024 px, 143 KB)]`. `backend/services/mcp/media.py` gets the bytes:

- **In the result itself:** image and audio blocks, and embedded resources, as base64.
- **Linked** (`resource_link`): images, audio and PDFs are read from the server (`resources/read`). Text and video are not fetched; they stay links.
- **Linked, but not deliverable:** when the read fails, or what comes back is no base64, the web address in the result that ends in the resource's file name is downloaded instead (of several, the largest). Civitai needs this: its `resources/read` returns an image's bytes as text, which destroys them, and names the image's signed address in the result's text (seen 2026-11-12). Downloads follow only https, only to public addresses (unless `MCP_ALLOW_PRIVATE_URLS`), send none of the server's headers, take only images, audio and PDFs, and stop at 10 MB.

What can't be kept never fails the tool call (the tool ran, and may have cost something): the model is told `not kept` and why.

An agent with the `files` tool group is told that the user sees only a small preview and that `show_file` shows a file large. An agent without it can't show anything itself, so everything its tools create is shown.

## In the chat

The tool result steps of an answer carry the files in their metadata:

- `files`: the files a tool created (`[{fileId, name, mimeType, size, width, height}]`, `file_store.file_ref()`).
- `shownFiles`: the files `show_file` shows (and all files of an agent without the file tools).

`AnswerFilesComponent` (between the steps and the answer's text) shows the `shownFiles` of all steps large and, under them, the created files that aren't shown, as a row of small previews. So nothing a tool made stays hidden in a collapsed step, and it appears as soon as the tool's result arrives. The step itself shows its files in place of the metadata. Since this comes from the steps, it is stored with the message.

`FileTileComponent` is one file: an image as its preview, anything else as a card with its name; a click opens the existing preview dialog (zoom, download). Previews come from `GET /api/files/{id}/thumbnail` and are loaded with the session (`FilePreviewsService`), since the page may only show images from its own address or ones it loaded itself. Uploaded images in messages that came from the server use the same previews.

## HTTP API

All under `/api/files`, for the file's owner only (404 otherwise):

- `POST /upload`: store files (multipart `files`); returns `[{fileId, transcript?}]`. PDFs get their text and pages extracted, audio is transcribed.
- `GET /{id}`: the file.
- `GET /{id}/thumbnail?size=small|large`: a preview of an image as WebP, at most 256 or 1024 pixels on its longer edge. Made on the first request and kept next to the file (`<file ID>_thumb_<size>.webp`); cached by the browser for good, since a file never changes. 404 for a file that is no image.
- `GET /{id}/text`: a document's extracted text, or an audio file's transcript.
- `DELETE /{id}`: the file with everything derived from it.

## Data

`uploaded_files`: `file_id`, `user_id`, `created_at`, `conversation_id` (null: in no conversation), `message_id` (the message it came with: the user's, or the answer a tool made it in), `name`, `mime_type`, `size_bytes`, `width`, `height`, `source` (`upload` or `tool`), `origin` and `details` (files of tools).

## Tests

- `python -m backend.llm.tests.run_all`: the file tools on a fake file table (the conversation's files only, names and IDs, a vision model gets the scaled image, a text-only model the description, `show_file`), lists that models send as text, the vision helper's errors not cached, and images in tool results for both adapters.
- `python backend/services/tests/mcp_test.py` (`test_files`, `test_media`): against a real Postgres and real MCP servers: images of a result saved with unique names, linked resources, the download fallback and its limits, uploads linked and unlinked with their messages, the migration's backfill, previews, the files API.

## Not built yet

- **Deleting files with their conversation.** Deleting a conversation, or a message, leaves its files on disk (as uploads always were; only an expired guest's files are deleted). They are in no conversation then, so a cleanup can find them (`conversation_id IS NULL`).
- **One conversation per file.** A conversation imported into the account that already has its original shows the attachments, but its agent can't open them: they stay with the first conversation.
- **Video, and media a result only names by address.** Linked videos are not fetched. A server that returns nothing but a web address in its text (no image block, no resource link) gets no file.
- **Passing a file to a tool.** The agent can read and show a file, but not hand it to an MCP tool (as the start image of an image-to-image run, say): tools take JSON arguments, and the files are not reachable from outside.
- **Images of user messages are not scaled.** The image in the latest user message goes to a vision model as uploaded; only `read_file` scales.
