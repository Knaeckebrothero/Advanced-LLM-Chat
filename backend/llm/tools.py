"""
Tool registry for the agent loop.

A tool is an async function plus an explicit JSON schema of its arguments. The
registry renders the schemas for both APIs (OpenAI function tools, Anthropic
tools), checks the arguments the model sends, and runs the function.

The implementations live in backend/services/tools/; this module only describes
them to the model. default_tools() returns the tools that are enabled by the
configuration, tools_for_groups() limits them to a persona's tool groups. Both
are built per answer for the user it is for: the file tools only see the files
of that user's conversation (docs/files.md), the knowledge base tools only
that user's notes (the shared knowledge base, or the agent's own one). Opt-in groups (the knowledge base,
with the memory, and the users' own MCP servers) are never part of "every
enabled tool": an agent has to select them.

Tools of MCP servers are not a static group: backend/services/mcp/tools.py
connects to the servers of an answer and adds their tools to the registry
(docs/mcp.md). The group user_mcp only marks that an agent wants the users'
own servers; it has no tools of its own here.
"""
import asyncio
import contextvars
import functools
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Iterator, Optional

from ..config import MCP_ENABLED, MCP_USER_SERVERS, NEO4J_ENABLED

log = logging.getLogger(__name__)

# English step titles per tool; the frontend translates them by these strings
TOOL_TITLES = {
    "list_files": "Listing Files",
    "read_file": "Reading File",
    "show_file": "Showing File",
    "web_search": "Searching the Web",
    "get_graph_schema": "Inspecting Knowledge Graph",
    "search_graph": "Searching Knowledge Graph",
    "query_graph": "Querying Knowledge Graph",
    "kb_search": "Searching Knowledge Base",
    "kb_list": "Listing Knowledge Base",
    "kb_read": "Reading Note",
    "kb_write": "Writing Note",
    "kb_update": "Updating Note",
    "kb_archive": "Archiving Note",
    "memory_add": "Saving to Memory",
    "memory_replace": "Updating Memory",
    "memory_remove": "Removing from Memory",
}

# Tool groups a persona can select (backend.models.catalog.ToolGroup), with their tools
TOOL_GROUPS = {
    "files": ("list_files", "read_file", "show_file"),
    "web_search": ("web_search",),
    "knowledge_graph": ("get_graph_schema", "search_graph", "query_graph"),
    "knowledge_base": ("kb_search", "kb_list", "kb_read", "kb_write", "kb_update", "kb_archive",
                       "memory_add", "memory_replace", "memory_remove"),
    # The users' own MCP servers: their tools are added per answer (backend/services/mcp/tools.py)
    "user_mcp": (),
}

# The memory tools, part of the knowledge base group
MEMORY_TOOL_NAMES = ("memory_add", "memory_replace", "memory_remove")

# Groups an agent only gets when it selects them: not part of "every enabled tool" (an agent
# with tools null, or no agent). Both also need a signed-in user, never a guest.
OPT_IN_GROUPS = frozenset({"knowledge_base", "user_mcp"})

# JSON schema types the argument check understands
_JSON_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


class ToolInputError(ValueError):
    """The model sent arguments that don't match the tool's schema."""


class ToolError(Exception):
    """A tool failed and says why; the model gets the message as it is (e.g. an MCP server's error)."""


class ToolText(str):
    """
    A tool's text result with more than text:
    - metadata for the chat: the model gets the text, the result step also carries the metadata
      (e.g. {"kbNote": slug}, so the chat can open the note; {"files": [...]} for files a tool made).
    - images for the model: image_url parts (OpenAI format) that go to the model with the text.
      Only for models that take images; the adapters put them where their API accepts them.
    """

    metadata: Optional[dict]
    images: tuple

    def __new__(cls, text: str, metadata: Optional[dict] = None, images: Iterable[dict] = ()):
        result = super().__new__(cls, text)
        result.metadata = metadata
        result.images = tuple(images)
        return result


# Where a running tool sends steps for the chat (an AgentStep goes to the answer's stream right
# away, a step with an earlier id replaces it). The agent loop sets it for each tool call; None
# when nobody is watching (no answer stream), e.g. outside the agent loop.
StepSink = Callable[[Any], None]
_step_sink: contextvars.ContextVar[Optional[StepSink]] = contextvars.ContextVar("tool_step_sink", default=None)


def step_sink() -> Optional[StepSink]:
    """The step sink of the running tool call, or None (see _step_sink)."""
    return _step_sink.get()


def with_step_sink(sink: Optional[StepSink]) -> contextvars.Context:
    """A copy of the current context in which tool calls send their steps to the sink (for asyncio tasks)."""
    context = contextvars.copy_context()
    context.run(_step_sink.set, sink)
    return context


@dataclass(frozen=True)
class Tool:
    """One tool the model can call."""

    name: str
    description: str
    parameters: dict                        # JSON schema of the arguments (type "object")
    func: Callable[..., Awaitable[Any]]     # called with the arguments as keyword arguments
    title: Optional[str] = None             # step title; defaults to TOOL_TITLES or the name

    @property
    def step_title(self) -> str:
        """The English title of this tool's steps."""
        return self.title or TOOL_TITLES.get(self.name, self.name)


class ToolRegistry:
    """An ordered set of tools, keyed by name."""

    def __init__(self, tools: Iterable[Tool] = ()):
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.add(tool)

    def add(self, tool: Tool) -> None:
        """Register a tool, replacing one with the same name."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """The tool with this name, or None."""
        return self._tools.get(name)

    def names(self) -> list[str]:
        """Names of the registered tools, in registration order."""
        return list(self._tools)

    def title(self, name: str) -> str:
        """Step title for a tool name, also for names the registry doesn't know."""
        tool = self._tools.get(name)
        return tool.step_title if tool else TOOL_TITLES.get(name, name)

    def __len__(self) -> int:
        return len(self._tools)

    def __iter__(self) -> Iterator[Tool]:
        return iter(self._tools.values())

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def openai_schemas(self) -> list[dict]:
        """The tools in the Chat Completions format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    def anthropic_schemas(self) -> list[dict]:
        """The tools in the Anthropic Messages format."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
            for tool in self._tools.values()
        ]

    async def call(self, name: str, arguments: Any) -> Any:
        """
        Check the arguments against the tool's schema and run it.

        Raises:
            ToolInputError: Unknown tool, or arguments that don't match the schema.
            Exception: Whatever the tool itself raises.
        """
        tool = self._tools.get(name)
        if tool is None:
            raise ToolInputError(f"Unknown tool '{name}'. Available tools: {', '.join(self._tools) or 'none'}")
        kwargs = _check_arguments(tool, arguments)
        return await tool.func(**kwargs)


def _check_arguments(tool: Tool, arguments: Any) -> dict:
    """Validate arguments against the top level of the tool's schema; drop unknown keys."""
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ToolInputError(f"Arguments for {tool.name} must be a JSON object, got {type(arguments).__name__}")

    properties = tool.parameters.get("properties", {})
    missing = [key for key in tool.parameters.get("required", []) if arguments.get(key) is None]
    if missing:
        raise ToolInputError(f"Missing required argument(s) for {tool.name}: {', '.join(missing)}")

    kwargs = {}
    for key, value in arguments.items():
        schema = properties.get(key)
        if schema is None:
            log.warning(f"Ignoring unknown argument '{key}' for tool {tool.name}")
            continue
        if value is None:
            continue
        if not isinstance(schema, dict):
            kwargs[key] = value
            continue
        # A type may be a list (["string", "null"]) or missing (anyOf, $ref, ...: not checked here)
        types = schema.get("type")
        types = [types] if isinstance(types, str) else [t for t in types if isinstance(t, str)] if isinstance(types, list) else []
        if types and not any(_type_matches(value, t) for t in types):
            # Models sometimes send numbers as strings
            if "integer" in types and isinstance(value, str) and value.strip().lstrip("-").isdigit():
                value = int(value)
            # ... and a list as its JSON text, or one string in place of a list of strings
            elif "array" in types and isinstance(value, str) and _as_list(value, schema) is not None:
                value = _as_list(value, schema)
            else:
                raise ToolInputError(f"Argument '{key}' for {tool.name} must be of type {' or '.join(types)}")
        if schema.get("type") == "array" and isinstance(schema.get("items"), dict) and schema["items"].get("type") == "integer":
            try:
                value = [int(item) for item in value]
            except (TypeError, ValueError):
                raise ToolInputError(f"Argument '{key}' for {tool.name} must be a list of integers")
        kwargs[key] = value
    return kwargs


def _as_list(value: str, schema: dict) -> Optional[list]:
    """The list a model meant by a string: its JSON text ('["a", "b"]'), or the one string of a list of strings."""
    text = value.strip()
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except ValueError:
            pass
    items = schema.get("items")
    if isinstance(items, dict) and items.get("type") == "string":
        return [value]
    return None


def _type_matches(value: Any, json_type: str) -> bool:
    """Whether a value has a JSON schema type; unknown types match anything."""
    if json_type == "null":
        return value is None
    expected = _JSON_TYPES.get(json_type)
    if expected is None:
        return True
    # bool is an int subclass; don't accept true/false for numbers
    if isinstance(value, bool) and json_type != "boolean":
        return False
    return isinstance(value, expected)


def format_tool_output(output: Any) -> str:
    """Render a tool's return value as the text the model receives."""
    if output is None:
        return ""
    if isinstance(output, str):
        return str(output)  # A plain str, also for a ToolText
    return json.dumps(output, ensure_ascii=False, default=str)


def tool_message_content(output: Any) -> Any:
    """
    The content of the tool message for a tool's return value: its text, or for a result with
    images (ToolText.images) a list of parts, the text first.
    """
    text = format_tool_output(output)
    images = getattr(output, "images", None)
    if not images:
        return text
    return [{"type": "text", "text": text}, *images]


def _in_thread(func: Callable[..., Any]) -> Callable[..., Awaitable[Any]]:
    """Wrap a blocking function (database, Neo4j, files) so it runs in a worker thread."""
    @functools.wraps(func)
    async def wrapper(**kwargs):
        return await asyncio.to_thread(func, **kwargs)
    return wrapper


# =========================================================================
# Tool definitions
# =========================================================================

def file_tools(user_id: Optional[int] = None, conversation_id: Optional[str] = None, vision: bool = False) -> list[Tool]:
    """
    list_files, read_file, show_file: the files of the conversation (docs/files.md).

    Args:
        user_id: The user the agent answers for.
        conversation_id: The conversation it answers in. The tools only see this user's files
            of this conversation; the model can't choose another (the arguments are not in
            the schemas). Without either, they see no files at all.
        vision: The model takes images: read_file gives it an image itself instead of a description.
    """
    from ..services.tools import file_tools as tools
    scope = {"user_id": user_id, "conversation_id": conversation_id}
    file_param = {
        "type": "string",
        "description": "The file's name as list_files or an attachment placeholder shows it, e.g. \"report.pdf\", "
                       "or its fileId",
    }
    image_content = (
        "An image you get to see yourself."
        if vision else
        "An image comes as a description written by a vision model; use 'query' to ask it something specific."
    )
    query_subject = "a PDF's pages (a vision model answers it)" if vision else "an image or PDF"
    return [
        Tool(
            name="list_files",
            description=(
                "List the files of this conversation, oldest first: what the user attached and what your tools "
                "created (e.g. generated images), with name, type, size and where each comes from. Call it "
                "when the user refers to a file you can't find in the conversation, or to get a file's name."
            ),
            parameters={"type": "object", "properties": {}},
            func=_in_thread(functools.partial(tools.list_files, **scope)),
        ),
        Tool(
            name="read_file",
            description=(
                "Get the content of a file of this conversation: the text of a text file, the extracted text "
                "plus page descriptions of a PDF, the transcript of an audio file. " + image_content + " "
                "Call it for a file that appears as a placeholder like [Attachment: report.pdf (fileId: abc123) "
                "...], for one list_files shows, and to look at an image a tool created."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "file": file_param,
                    "query": {
                        "type": "string",
                        "description": f"Optional question about {query_subject}, e.g. \"What is the total revenue?\"",
                    },
                    "pages": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "For PDFs: the pages to read, starting at 1, e.g. [1, 3]",
                    },
                },
                "required": ["file"],
            },
            func=functools.partial(tools.read_file, vision=vision, **scope),
        ),
        Tool(
            name="show_file",
            description=(
                "Show files of this conversation to the user: they appear above the text of your answer, images "
                "large, other files as a card to open. Use it for the images you want the user to look at (an "
                "image a tool created is only a small preview for them until you show it) and when the user "
                "asks to see a file again. Several files go in one call."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "The names (or fileIds) of the files to show, e.g. [\"fox-1.png\", \"fox-2.png\"]",
                    },
                },
                "required": ["files"],
            },
            func=_in_thread(functools.partial(tools.show_file, **scope)),
        ),
    ]


def graph_tools() -> list[Tool]:
    """The read-only Neo4j knowledge graph tools."""
    from ..services.tools.neo4j_tools import get_graph_schema, query_graph, search_graph
    return [
        Tool(
            name="get_graph_schema",
            description=(
                "Get the structure of the knowledge graph: node and relationship counts, the properties of "
                "each node label and the relationship patterns that connect them. Call this before searching "
                "or querying the graph."
            ),
            parameters={"type": "object", "properties": {}},
            func=_in_thread(get_graph_schema),
        ),
        Tool(
            name="search_graph",
            description=(
                "Search the knowledge graph for nodes whose text properties contain the given text. The search "
                "is case-insensitive and looks at every string property (and list of strings) of every node. "
                "Returns matching nodes with their id, labels and properties."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to search for, e.g. a name, keyword or phrase",
                    },
                },
                "required": ["text"],
            },
            func=_in_thread(search_graph),
        ),
        Tool(
            name="query_graph",
            description=(
                "Run a read-only Cypher query against the knowledge graph. Call get_graph_schema first so the "
                "query only uses labels, relationship types and properties that exist. Writes (CREATE, MERGE, "
                "SET, DELETE, ...) are rejected. Return only the fields you need; only a limited number of rows "
                "comes back, and the result says whether it was truncated."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "cypher": {
                        "type": "string",
                        "description": "The Cypher query, e.g. 'MATCH (p:Person)-[:KNOWS]->(f) RETURN p.name, f.name'",
                    },
                },
                "required": ["cypher"],
            },
            func=_in_thread(query_graph),
        ),
    ]


def web_search_tool() -> Tool:
    """web_search: Tavily web search."""
    from ..services.tools.web_search_tools import MAX_RESULTS, web_search
    return Tool(
        name="web_search",
        description=(
            "Search the web. Call this for current events, recent facts, prices, or anything you are unsure "
            "about or that may have changed after your training. Returns a short answer when available and the "
            "top results with title, URL and content. Cite the URLs you use."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query, phrased like a web search",
                },
                "max_results": {
                    "type": "integer",
                    "description": f"Number of results, 1 to {MAX_RESULTS} (default {MAX_RESULTS})",
                },
            },
            "required": ["query"],
        },
        func=web_search,
    )


def knowledge_base_tools(user_id: int, conversation: Optional[dict] = None, vault: int = 0,
                         author: str = "agent") -> list[Tool]:
    """
    The knowledge base tools: the notes of one user, kept across all of their conversations, and
    the memory, which is part of every answer.

    Args:
        user_id: The user whose knowledge base it is; not an argument the model sees.
        conversation: The conversation the agent answers in (id, persona_id), recorded with
            every change of a note.
        vault: 0 for the user's shared knowledge base, else the personas.id of the agent whose
            own knowledge base it is (backend.catalog.resolver.persona_vault()).
        author: Recorded with the changes: 'agent', or 'review' for the memory review.
    """
    from ..services.knowledge_base import (MAX_CONTENT_CHARS, MAX_DESCRIPTION_CHARS, MAX_TAGS,
                                           MAX_TITLE_CHARS, MEMORY_LINE_CHARS, MEMORY_SECTION_CHARS, Writer)
    from ..services.tools import kb_tools

    conversation = conversation or {}
    writer = Writer(user_id=user_id, author=author, conversation_id=conversation.get("id"),
                    persona_id=conversation.get("persona_id"), vault=vault)
    reader = {"user_id": user_id, "vault": vault}
    line_param = {
        "type": "string",
        "description": "A part of the line to change, copied from the memory in the system prompt (a few words "
                       "are enough, but they must match only one line)",
    }
    text_param = {
        "type": "string",
        "description": f"The line: one fact, short (at most {MEMORY_LINE_CHARS} characters), e.g. \"Prefers "
                       f"short answers\" or \"Planning a trip to Lisbon in May → [[lisbon-trip]]\". The date "
                       f"is added",
    }
    note_param = {
        "type": "string",
        "description": "The note's slug, e.g. \"project-apollo\" (its exact title works too)",
    }
    tags_param = {
        "type": "array",
        "items": {"type": "string"},
        "description": f"A few lowercase keywords, e.g. [\"work\", \"travel\"] (at most {MAX_TAGS})",
    }
    description_param = {
        "type": "string",
        "description": f"One sentence saying what the note is about, shown in lists and search results "
                       f"(at most {MAX_DESCRIPTION_CHARS} characters)",
    }
    return [
        Tool(
            name="kb_search",
            description=(
                "Search the user's knowledge base: the notes you kept in earlier conversations with them. Give at "
                "least one of: query (words; notes containing them rank higher, words in the title most), exact "
                "(literal texts such as a name, number or phrase, matched as case-insensitive substrings) and tags "
                "(notes with these tags rank higher). Returns the best notes with slug, title, tags and the "
                "passage that matched; read one in full with kb_read. Archived notes are not searched."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Words to look for, e.g. \"apollo budget\""},
                    "exact": {"type": "array", "items": {"type": "string"},
                              "description": "Literal texts to find, e.g. [\"Müller GmbH\"]; a note matches if it "
                                             "contains any of them"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags, e.g. [\"work\"]"},
                    "max_results": {"type": "integer",
                                    "description": f"Number of notes, 1 to {kb_tools.MAX_SEARCH_RESULTS} (default 10)"},
                },
            },
            func=_in_thread(functools.partial(kb_tools.kb_search, **reader)),
        ),
        Tool(
            name="kb_list",
            description=(
                "List the notes in the user's knowledge base, the most recently updated first, with slug, title, "
                "description and tags. Without a tag it also shows the tags in use. Use it for an overview; use "
                "kb_search to find notes on a topic."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "description": "Only notes with this tag"},
                    "max_results": {"type": "integer",
                                    "description": f"Number of notes, 1 to {kb_tools.MAX_LIST_RESULTS} (default 50)"},
                },
            },
            func=_in_thread(functools.partial(kb_tools.kb_list, **reader)),
        ),
        Tool(
            name="kb_read",
            description=(
                "Read a note of the user's knowledge base in full: its Markdown content, tags and dates, the notes "
                "it links to and the notes that link to it."
            ),
            parameters={"type": "object", "properties": {"note": note_param}, "required": ["note"]},
            func=_in_thread(functools.partial(kb_tools.kb_read, **reader)),
        ),
        Tool(
            name="kb_write",
            description=(
                "Create a new note in the user's knowledge base, which keeps notes across all of their "
                "conversations. Write down what is worth remembering beyond this conversation: facts about the "
                "user and their projects, decisions, preferences, results of research, or what the user asks you "
                "to remember. One topic per note. Search first (kb_search): if a note on the topic exists, change "
                "it with kb_update instead; a title whose slug exists already is refused. Link other notes with "
                "[[slug]]. Returns the new note's slug."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string",
                              "description": f"Short and specific, e.g. \"Project Apollo\" (at most {MAX_TITLE_CHARS} "
                                             f"characters); the note's slug is made from it and stays the same"},
                    "content": {"type": "string",
                                "description": f"The note in Markdown, without the title as a heading (at most "
                                               f"{MAX_CONTENT_CHARS} characters)"},
                    "description": description_param,
                    "tags": tags_param,
                },
                "required": ["title", "content"],
            },
            func=_in_thread(functools.partial(kb_tools.kb_write, writer=writer)),
        ),
        Tool(
            name="kb_update",
            description=(
                "Change a note in the user's knowledge base. Give the note and what to change: content (replaces "
                "the whole text) or append (adds text at the end), title, description or tags (replaces the list). "
                "The slug stays the same. Read the note before replacing its content so nothing gets lost. "
                "Updating an archived note restores it."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "note": note_param,
                    "content": {"type": "string", "description": "The new content in Markdown, replacing the old one"},
                    "append": {"type": "string", "description": "Markdown to add at the end of the content"},
                    "title": {"type": "string", "description": "A new title (the slug stays)"},
                    "description": description_param,
                    "tags": {**tags_param, "description": "The complete new list of tags; [] removes them"},
                },
                "required": ["note"],
            },
            func=_in_thread(functools.partial(kb_tools.kb_update, writer=writer)),
        ),
        Tool(
            name="kb_archive",
            description=(
                "Archive a note of the user's knowledge base that is wrong, outdated or no longer wanted, also "
                "when the user asks you to delete it. Archived notes don't show up in kb_list or kb_search; "
                "kb_read still shows them and kb_update restores them."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "note": note_param,
                    "reason": {"type": "string", "description": "Why, e.g. \"The project was cancelled\""},
                },
                "required": ["note"],
            },
            func=_in_thread(functools.partial(kb_tools.kb_archive, writer=writer)),
        ),
        Tool(
            name="memory_add",
            description=(
                "Add a line to your memory of this user. The memory is part of every conversation with them (you "
                "see it in the system prompt), so keep in it what you should always have in mind: who the user "
                "is, their preferences and corrections, ongoing goals, plans and decisions, and where the details "
                "are: a short line that points to a note with [[slug]]. One fact per line; today's date is added "
                "to it. A line the memory has already is not added twice."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": text_param,
                    "section": {"type": "string",
                                "description": f"A heading to put the line under, made if missing (at most "
                                               f"{MEMORY_SECTION_CHARS} characters), e.g. \"About the user\", "
                                               f"\"Preferences\", \"Ongoing\" or \"Where things are\". Without "
                                               f"it the line goes before the first heading"},
                },
                "required": ["text"],
            },
            func=_in_thread(functools.partial(kb_tools.memory_add, writer=writer)),
        ),
        Tool(
            name="memory_replace",
            description=(
                "Replace a line of your memory: when a fact changed, to correct it, or to merge several lines "
                "into one. The new line gets today's date."
            ),
            parameters={
                "type": "object",
                "properties": {"line": line_param, "text": text_param},
                "required": ["line", "text"],
            },
            func=_in_thread(functools.partial(kb_tools.memory_replace, writer=writer)),
        ),
        Tool(
            name="memory_remove",
            description=(
                "Remove a line of your memory that is wrong or no longer true, also when the user asks you to "
                "forget it."
            ),
            parameters={"type": "object", "properties": {"line": line_param}, "required": ["line"]},
            func=_in_thread(functools.partial(kb_tools.memory_remove, writer=writer)),
        ),
    ]


def tool_group_unavailable_reason(group: str) -> Optional[str]:
    """
    Why the configuration switches a tool group off.

    The graph tools need NEO4J_ENABLED, web search needs TAVILY_API_KEY;
    file access and the knowledge base are always available (the knowledge
    base only to signed-in users, which tools_for_groups() checks).

    Args:
        group: A key of TOOL_GROUPS.

    Returns:
        The reason, or None if the group is available.
    """
    from ..services.tools.web_search_tools import is_web_search_available

    if group == "knowledge_graph" and not NEO4J_ENABLED:
        return "NEO4J_ENABLED is off"
    if group == "user_mcp":
        if not MCP_ENABLED:
            return "MCP_ENABLED is off"
        if not MCP_USER_SERVERS:
            return "MCP_USER_SERVERS is off"
    if group == "web_search" and not is_web_search_available():
        return "TAVILY_API_KEY is not set"
    return None


def tool_group_status() -> list[dict]:
    """
    Every tool group with its availability, in TOOL_GROUPS order:
    [{"id", "available", "reason", "optIn"}] (optIn: only for agents that select it).
    """
    status = []
    for group in TOOL_GROUPS:
        reason = tool_group_unavailable_reason(group)
        status.append({"id": group, "available": reason is None, "reason": reason, "optIn": group in OPT_IN_GROUPS})
    return status


def _group_tools(group: str, user_id: Optional[int], guest: bool, conversation: Optional[dict],
                 vault: int = 0, vision: bool = False) -> list[Tool]:
    """The tool definitions of a group, for the user the agent answers for."""
    if group == "files":
        return file_tools(user_id, (conversation or {}).get("id"), vision)
    if group == "web_search":
        return [web_search_tool()]
    if group == "knowledge_graph":
        return graph_tools()
    if group == "knowledge_base":
        if user_id is None or guest:
            log.debug("No knowledge base without a signed-in user")
            return []
        return knowledge_base_tools(user_id, conversation, vault)
    if group == "user_mcp":
        return []  # Added per answer by backend/services/mcp/tools.py
    raise ValueError(f"Unknown tool group '{group}'")


def _enabled_tools(groups: Iterable[str], user_id: Optional[int], guest: bool = False,
                   conversation: Optional[dict] = None, vault: int = 0, vision: bool = False) -> ToolRegistry:
    """The tools of these groups that the configuration enables, in TOOL_GROUPS order."""
    groups = set(groups)
    registry = ToolRegistry()
    for group in TOOL_GROUPS:
        if group not in groups:
            continue
        reason = tool_group_unavailable_reason(group)
        if reason:
            log.debug(f"Tool group {group} disabled: {reason}")
            continue
        for tool in _group_tools(group, user_id, guest, conversation, vault, vision):
            registry.add(tool)
    return registry


def default_tools(user_id: Optional[int] = None, *, conversation: Optional[dict] = None,
                  vision: bool = False) -> ToolRegistry:
    """
    The tools enabled by the configuration (see tool_group_unavailable_reason()),
    without the opt-in groups (OPT_IN_GROUPS).

    Args:
        user_id: The user the agent answers for.
        conversation: The conversation it answers in (id); the file tools only see
            this user's files of this conversation (without either: none at all).
        vision: The model takes images (read_file then gives it images themselves).
    """
    registry = _enabled_tools((group for group in TOOL_GROUPS if group not in OPT_IN_GROUPS), user_id,
                              conversation=conversation, vision=vision)
    log.debug(f"Default tools: {', '.join(registry.names())}")
    return registry


def tools_for_groups(groups: Optional[Iterable[str]], user_id: Optional[int] = None, *, guest: bool = False,
                     conversation: Optional[dict] = None, vault: int = 0, vision: bool = False) -> ToolRegistry:
    """
    The enabled tools of the given tool groups, e.g. a persona's selection.

    Args:
        groups: Keys of TOOL_GROUPS; None for every enabled tool except the
            opt-in groups (default_tools()). Unknown groups are ignored.
        user_id: The user the agent answers for; the file tools only see this
            user's files of the conversation, the knowledge base tools only this
            user's notes (None: no files and no knowledge base).
        guest: The user is a guest: no knowledge base (a guest's data is
            deleted when the session ends).
        conversation: The conversation the agent answers in (id, persona_id):
            the one the file tools see the files of, and recorded with the
            knowledge base changes.
        vault: The knowledge base: 0 for the user's shared one, else the
            agent's own (backend.catalog.resolver.persona_vault()).
        vision: The model takes images (read_file then gives it images themselves).

    Returns:
        The tools; empty for an empty selection.
    """
    if groups is None:
        return default_tools(user_id, conversation=conversation, vision=vision)
    groups = list(groups)
    unknown = [group for group in groups if group not in TOOL_GROUPS]
    if unknown:
        log.warning(f"Ignoring unknown tool group(s): {', '.join(map(str, unknown))}")
    selected = _enabled_tools(groups, user_id, guest, conversation, vault, vision)
    log.debug(f"Tools for groups {groups}: {', '.join(selected.names()) or 'none'}")
    return selected
