# Files of a conversation

Every file in the chat is handled the same way, whether the user uploaded it or a tool created it (an image an MCP server generated, for example). It is stored once, belongs to one conversation, and the agent of that conversation lists and reads it with two tools, `list_files` and `read_file`, and shows it to the user by placing it in the text of its answer.

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

A file is named by its name (case doesn't matter) or by its file ID; when several files have the same name, `list_files` shows their IDs and the name alone is refused.

### Showing a file: placed in the answer's text

No tool shows a file. The agent writes a Markdown image whose address is the file's name or file ID, where it talks about the file: `![A red fox in the snow](fox-1.png)`. The chat shows the file at that place (below, "In the chat"): an image as the picture, any other file as a card. The prompt of the file tools (`FILE_ACCESS_PROMPT`) says so, and the note under an MCP result that saved files gives the exact line to write.

- **Why not a tool:** the text can say "the second draft" right next to the image, it costs no extra model call, and there is one way to show a file instead of two. The `show_file` tool (until November 2026) put files into one block above the text. Its results in stored answers still show that way (`shownFiles`).
- **Only stored files:** the address is resolved against the conversation's files, never loaded as an address. An image at a web address becomes a link: the page may only load images from the app's own address (Content-Security-Policy), and an address a model writes can carry data out of the conversation (a planted instruction makes the model put it into the address).
- **Tested on 2026-11-13**, one run each, all right on the first try: DeepSeek V4.1 Flash, Kimi K3 and Claude Haiku 5.5 placed two images they had just generated (a demo MCP server), DeepSeek V4.1 Flash and Mistral Large 4 placed two uploaded images they were asked to show again.

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

An agent with the `files` tool group is told that the user sees only a small preview and how to place a file in its answer. An agent without it isn't told, so everything its tools create is shown.

## In the chat

The tool result steps of an answer carry the files in their metadata:

- `files`: the files a tool created (`[{fileId, name, mimeType, size, width, height}]`, `file_store.file_ref()`).
- `shownFiles`: all files of an agent without the file tools (and what `show_file` showed in older answers).

**Files placed in the text.** `answerParts()` (`src/app/chat-ui/chat-ui-message/answer-parts.ts`) splits a message's text at every Markdown image (and Obsidian's `![[fox-1.png]]`) that names a file, outside of code. The message is then drawn as parts: Markdown, a row of files, Markdown. While an answer is written only its last part is drawn again, and a reference that isn't complete yet is held back.

- **Which file:** `findFile()` looks in the answer's own steps first (what its tools just created), then in the conversation's files (`ConversationFilesService`, `GET /api/files?conversationId=`, loaded when an answer first needs it and once more for a name it doesn't have). Of several files with one name it takes the newest the answer could know. Names match whatever their case, with spaces and brackets, and as `sandbox:/mnt/data/fox-1.png`.
- **Next to each other:** references with nothing between them (one per line, or a list of them) are one row. A file in a list ends the list item before it; in a table it is a link that opens the file, since a table row can't be split.
- **Not found:** "(File not found: name)" in the text. An image at a web address is a link. `![[Some note]]` that names no file stays a link to the note.

`AnswerFilesComponent` (between the steps and the answer's text) shows what the answer doesn't place: the `shownFiles` large and, under them, the other created files as a row of small previews. So nothing a tool made stays hidden in a collapsed step, and it appears as soon as the tool's result arrives. The step itself shows its files in place of the metadata. Since this comes from the steps, it is stored with the message.

`FileTileComponent` is one file: an image as its preview, anything else as a card with its name (a PDF with its first page); a click opens the existing preview dialog (zoom, download). Previews come from `GET /api/files/{id}/thumbnail` and are loaded with the session (`FilePreviewsService`), since the page may only show images from its own address or ones it loaded itself. Uploaded images in messages that came from the server use the same previews.

**Files of this chat.** A dialog lists every file of a conversation, to open and to download: what the user attached and what the agent's tools created, newest first (`ConversationFilesDialogComponent` in `src/app/components/conversation-files/`, loaded from `GET /api/files?conversationId=` each time it opens). It opens from **Files** in a conversation's menu in the sidebar, and from **Files of this chat** in the composer's attach menu once the server has the conversation.

- **Images** are a gallery of tiles in rows of one height (128 px, 96 px on phones), each as wide as its shape makes it. A tile's preview is loaded when it comes into view (`lazy`). A click opens the preview dialog, which steps through the listed images: buttons at the screen's edges, the arrow keys, or a swipe across an image that isn't zoomed in.
- **Any other file** is a row with its size, where it comes from ("Uploaded", "Created by Civitai: Run step") and when. A click opens it in the preview dialog (a document as its extracted text, audio in a player).
- **Download:** a button in each row, a button over each image for devices with a pointer (on a touch screen a tap opens the image, with Download there), and in the preview dialog. A document's preview shows only its text, so its download fetches the file.
- **Filter:** in a conversation with files of both kinds, "All", "Uploaded" and "Created by the agent".
- **Not in it:** files of deleted messages (they left the conversation), and files attached in the composer but not sent yet.

**All files.** The same dialog lists the files of all the user's conversations, from **All files** in the settings (`GET /api/files/all`). They are grouped by conversation: the conversation with the newest file first, each under its name, its images as a gallery and its other files as rows under them. A click on a conversation's name closes the dialog and the settings and opens that conversation. The preview steps through the images of all listed conversations. The files arrive 100 at a time, with "Show more" for the next ones; the filter asks the server, since not all files are in the browser. Files in no conversation (of deleted messages and deleted conversations) are not listed.

**Never cropped.** Every image is shown whole, everywhere:

- **A file tile** is as high as its place says (320 px alone, 200 px in a row, 72 px as a small preview; less on phones) and as wide as the image's shape makes it. In a column narrower than that it is as wide as the column and lower. Its space is reserved from the stored width and height, so nothing jumps when the image loads.
- **A message's only image** is shown large, as in a messenger: scaled down to fit 320 by 420 px (300 by 380 px on phones, and at most 68 % of the screen's width). The bubble is as wide as the image, and the text wraps under it (`message-body--photo`).
- **Several attachments of a message** are tiles: each image is scaled down to fit a square of 160 px (120 px on phones), and the tile is as large as the image then is.
- **In the composer** a preview is as high as the row (80 px, 70 px on phones) and as wide as its shape makes it.
- **Very long and very wide images** would become slivers, so a tile stays within 1:3 and 3:1 (an attachment at least 64 px wide and high), and a blurred copy of the image fills what the image leaves of it.

**Attaching.** Files are picked, dropped anywhere on the window (the composer says so while they are dragged), or pasted into the message (a screenshot; text copied from an office program stays text). They are uploaded right away. A message sent while one is still uploading waits and goes out with it, and files alone are a message. A file over 10 MB is not attached, and the chat says so.

## HTTP API

All under `/api/files`, for the file's owner only (404 otherwise):

- `POST /upload`: store files (multipart `files`); returns `[{fileId, transcript?}]`. PDFs get their text and pages extracted, audio is transcribed.
- `GET /{id}`: the file.
- `GET ?conversationId=…`: the files of a conversation, oldest first, as `[{fileId, name, mimeType, size, width, height, source, origin, createdAt}]` (`file_store.file_entry()`): `source` is `upload` or `tool`, `origin` the tool's title (files of tools only), `createdAt` UTC. None for a conversation of somebody else.
- `GET /all?offset=0&limit=100&source=upload|tool`: the files of all the user's conversations (at most 200 at once), as `{files, counts, size}`. `files` are entries as above with `conversationId` and `conversationName`, the conversations by their newest file, each conversation's files together, newest first. `counts` is `{upload, tool}` for all of them whatever `source` asks for, `size` the bytes they take. Files in no conversation are not among them.
- `GET /{id}/thumbnail?size=small|large`: a preview of an image, or of a PDF's first page (rendered at the upload), as WebP, at most 256 or 1024 pixels on its longer edge. Made on the first request and kept next to the file (`<file ID>_thumb_<size>.webp`); cached by the browser for good, since a file never changes. 404 for any other file.
- `GET /{id}/text`: a document's extracted text, or an audio file's transcript.
- `DELETE /{id}`: the file with everything derived from it.

## Limits

A file comes from anybody (a guest, an MCP server), so nothing that reads one may cost more than a fixed amount, whatever the file claims to be.

- **PDFs** are read in a process of their own, never in the server (`document_handler.process_pdf_safely()`, `backend/services/pdf_worker.py`): at most 60 seconds, at most 512 MB allocated by the worker and by the `pdftoppm` it starts, at most 2 at once. Up to 4 more wait their turn; beyond that a PDF is not processed. Of a PDF, the first 20 pages are rendered, each scaled to 1754 pixels on its longer edge (an A4 page at 150 dpi) whatever its size on paper, and at most 500,000 characters of text are kept. The page images of one PDF may take 32 MB together; the pages past that are not kept (pages of text take a few hundred KB each). A PDF that takes too long, or whose text needs more memory than that, is still stored, but without text and pages; one that only `pdftoppm` fails on keeps its text. The worker gets none of the server's settings (no keys, no passwords), only where programs are and the language. It is limited, not locked in: it runs as the server's user. The call blocks, so it runs in a thread (`asyncio.to_thread`). In the backend image `tini` is the first process, so the `pdftoppm` of a worker that was killed doesn't stay behind as a dead process.
- **Images** are decoded only up to 25 megapixels (`file_store.MAX_IMAGE_PIXELS`), two at a time. A larger one is stored and served, but has no preview and is not shown to a model. A camera's JPEG is the exception: it is decoded at a fraction of its size, so photos of any size get both. Reading an image's size (`image_size()`) never decodes it.
- **Audio:** the local Whisper model is loaded into the server and transcribes on its CPU for as long as the audio takes, one file at a time in a thread of its own. `WHISPER_LOCAL_FALLBACK=false` keeps a failed API transcription from starting it; a public deployment should set that.

## Data

`uploaded_files`: `file_id`, `user_id`, `created_at`, `conversation_id` (null: in no conversation), `message_id` (the message it came with: the user's, or the answer a tool made it in), `name`, `mime_type`, `size_bytes`, `width`, `height`, `source` (`upload` or `tool`), `origin` and `details` (files of tools).

## Tests

- `python -m backend.llm.tests.run_all`: the file tools on a fake file table (the conversation's files only, names and IDs, a vision model gets the scaled image, a text-only model the description, a PDF's preview), lists that models send as text, the vision helper's errors not cached, and images in tool results for both adapters.
- `ng test advanced-llm-chat --include='src/app/chat-ui/chat-ui-message/answer-parts.spec.ts'`: the files placed in an answer's text: where the text is split, rows, lists and tables, names in every spelling, files that don't exist, web addresses, code, an answer still being written.
- `python backend/services/tests/mcp_test.py` (`test_files`, `test_media`): against a real Postgres and real MCP servers: images of a result saved with unique names, linked resources, the download fallback and its limits, uploads linked and unlinked with their messages, the migration's backfill, previews, the files API (with where each listed file comes from, and the list of all files: its order, pages and filter).
- `python backend/services/tests/upload_safety_test.py`: the limits above, offline, with files it builds itself: PDFs with pages of 200 inches, PDFs that take poppler minutes or pdfminer gigabytes, PNGs that claim millions of pixels, a camera's JPEG, the local Whisper model as a fake.

## Not built yet

- **More to do with a listed file.** The lists open and download single files. There is no download of all files at once, no deleting a file from a list, and no jump from a file to its message (only to its conversation, from "All files"). Files in no conversation show in no list.
- **Deleting files with their conversation.** Deleting a conversation, or a message, leaves its files on disk (as uploads always were; only an expired guest's files are deleted). They are in no conversation then, so a cleanup can find them (`conversation_id IS NULL`).
- **One conversation per file.** A conversation imported into the account that already has its original shows the attachments, but its agent can't open them: they stay with the first conversation.
- **Video, and media a result only names by address.** Linked videos are not fetched. A server that returns nothing but a web address in its text (no image block, no resource link) gets no file.
- **Passing a file to a tool.** The agent can read and show a file, but not hand it to an MCP tool (as the start image of an image-to-image run, say): tools take JSON arguments, and the files are not reachable from outside.
- **Files of the knowledge base.** A file belongs to one conversation, so an image can't be kept in the knowledge base and shown in another chat yet. The direction (researched on 2026-11-13, see the backlog in `docs/generalization_refactor.md`): one note per image with a description the agent searches as text, the file owned by the user, shown with the same Markdown image.
- **The model isn't told about a wrong name.** A reference to a file that doesn't exist shows "(File not found)" to the user; the model learns of it only if the user says so.
- **Images of user messages are not scaled.** The image in the latest user message goes to a vision model as uploaded; only `read_file` scales.
