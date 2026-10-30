"""
Tool registry for the agent loop.

A tool is an async function plus an explicit JSON schema of its arguments. The
registry renders the schemas for both APIs (OpenAI function tools, Anthropic
tools), checks the arguments the model sends, and runs the function.

The implementations live in backend/services/tools/; this module only describes
them to the model. default_tools() returns the tools that are enabled by the
configuration.
"""
import asyncio
import functools
import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Iterator, Optional

from ..config import NEO4J_ENABLED

log = logging.getLogger(__name__)

# English step titles per tool; the frontend translates them by these strings
TOOL_TITLES = {
    "get_file_content": "Retrieving File Content",
    "web_search": "Searching the Web",
    "get_graph_schema": "Inspecting Knowledge Graph",
    "search_graph": "Searching Knowledge Graph",
    "query_graph": "Querying Knowledge Graph",
}

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
        expected = _JSON_TYPES.get(schema.get("type"))
        # bool is an int subclass; don't accept true/false for numbers
        if expected and (not isinstance(value, expected) or (isinstance(value, bool) and schema.get("type") != "boolean")):
            # Models sometimes send numbers as strings
            if schema.get("type") == "integer" and isinstance(value, str) and value.strip().lstrip("-").isdigit():
                value = int(value)
            else:
                raise ToolInputError(f"Argument '{key}' for {tool.name} must be of type {schema.get('type')}")
        if schema.get("type") == "array" and schema.get("items", {}).get("type") == "integer":
            try:
                value = [int(item) for item in value]
            except (TypeError, ValueError):
                raise ToolInputError(f"Argument '{key}' for {tool.name} must be a list of integers")
        kwargs[key] = value
    return kwargs


def format_tool_output(output: Any) -> str:
    """Render a tool's return value as the text the model receives."""
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    return json.dumps(output, ensure_ascii=False, default=str)


def _in_thread(func: Callable[..., Any]) -> Callable[..., Awaitable[Any]]:
    """Wrap a blocking function (database, Neo4j, files) so it runs in a worker thread."""
    @functools.wraps(func)
    async def wrapper(**kwargs):
        return await asyncio.to_thread(func, **kwargs)
    return wrapper


# =========================================================================
# Tool definitions
# =========================================================================

def file_content_tool() -> Tool:
    """get_file_content: read files shared earlier in the conversation."""
    from ..services.tools.file_tools import get_file_content
    return Tool(
        name="get_file_content",
        description=(
            "Retrieve content from a file shared earlier in this conversation. Call this when the user asks "
            "about a file that appears as a placeholder like [Attachment: report.pdf (fileId: abc123) ...] "
            "and its content is not in the current message. Always returns text: the content of text files, "
            "a visual description of images, the extracted text plus page descriptions of PDFs, and the "
            "transcript of audio files. Use 'query' to ask a specific question about an image or PDF; it is "
            "answered by a vision model."
        ),
        parameters={
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "string",
                    "description": "The fileId shown in the attachment placeholder, e.g. \"abc123\"",
                },
                "query": {
                    "type": "string",
                    "description": "Optional question about the file, e.g. \"What is the total revenue?\"",
                },
                "pages": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "For PDFs: the pages to retrieve, starting at 1, e.g. [1, 3]",
                },
            },
            "required": ["file_id"],
        },
        func=get_file_content,
    )


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


def default_tools() -> ToolRegistry:
    """
    The tools enabled by the configuration.

    get_file_content is always available; the graph tools need NEO4J_ENABLED,
    web search needs TAVILY_API_KEY.
    """
    from ..services.tools.web_search_tools import is_web_search_available

    registry = ToolRegistry([file_content_tool()])
    if NEO4J_ENABLED:
        for tool in graph_tools():
            registry.add(tool)
    if is_web_search_available():
        registry.add(web_search_tool())
    else:
        log.debug("TAVILY_API_KEY not set - web search tool disabled")
    log.debug(f"Default tools: {', '.join(registry.names())}")
    return registry
