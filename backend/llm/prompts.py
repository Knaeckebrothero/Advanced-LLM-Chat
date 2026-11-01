"""
System prompt for the agent.

The prompt is the identity paragraph (or a persona's prompt in its place),
followed by one section per enabled tool group, so the file access and graph
instructions stay when a persona is used. A conversation's system messages
come last (with_instructions()).
"""
from typing import Iterable, Optional, Union

from .tools import ToolRegistry

# Who the assistant is; a persona prompt replaces this paragraph
IDENTITY_PROMPT = (
    "You are a helpful and knowledgeable assistant. Answer clearly and accurately, and say so honestly "
    "when you don't know something. Respond in the same language as the user."
)

# Added when the model has any tools
TOOLS_PROMPT = "Use your tools when they help you give a better answer."

# Added when web search is enabled
WEB_SEARCH_PROMPT = "Use web search for current events or facts you are unsure about."

# Added when get_file_content is enabled
FILE_ACCESS_PROMPT = """## File Access:
When users share files (images, PDFs, documents), you see full content in the current message.
In follow-up messages, files appear as placeholders like:
[Attachment: report.pdf (fileId: abc123) - 5 pages, PDF document]

To access previously shared files, use the get_file_content tool:
- get_file_content(file_id="abc123") - retrieve full content
- get_file_content(file_id="abc123", query="What is the revenue?") - ask specific question
- get_file_content(file_id="abc123", pages=[1, 3]) - retrieve specific pages"""

# Added when the Neo4j knowledge graph tools are enabled
GRAPH_PROMPT = """## Knowledge Graph:
You have read access to a Neo4j knowledge graph. Call get_graph_schema first to learn which node labels, relationship types and properties exist. Then use search_graph to find nodes by text, or query_graph to run a read-only Cypher query."""

GRAPH_TOOL_NAMES = {"get_graph_schema", "search_graph", "query_graph"}

# Heads a conversation's system messages, after the rest of the prompt
INSTRUCTIONS_HEADING = "## Instructions for this conversation:"


def build_system_prompt(
    persona_prompt: Optional[str],
    tools: Union[ToolRegistry, Iterable[str], None],
) -> str:
    """
    Build the agent's system prompt.

    Args:
        persona_prompt: A rendered persona prompt that replaces the identity paragraph, or None.
        tools: The tools the model gets (a registry or tool names); None or empty for no tools.

    Returns:
        The system prompt.
    """
    if tools is None:
        names = set()
    elif isinstance(tools, ToolRegistry):
        names = set(tools.names())
    else:
        names = set(tools)

    identity = persona_prompt.strip() if persona_prompt and persona_prompt.strip() else IDENTITY_PROMPT
    sections = [identity]

    if names:
        tool_paragraph = TOOLS_PROMPT
        if "web_search" in names:
            tool_paragraph += " " + WEB_SEARCH_PROMPT
        sections.append(tool_paragraph)
    if "get_file_content" in names:
        sections.append(FILE_ACCESS_PROMPT)
    if names & GRAPH_TOOL_NAMES:
        sections.append(GRAPH_PROMPT)

    return "\n\n".join(sections)


def with_instructions(system_prompt: str, instructions: Iterable[str]) -> str:
    """
    The system prompt followed by a conversation's instructions (its system messages, oldest first).

    They go here rather than in their place in the history: many chat templates of
    open models accept a system message only at the start.
    """
    texts = [text.strip() for text in instructions if text and text.strip()]
    if not texts:
        return system_prompt
    return f"{system_prompt}\n\n{INSTRUCTIONS_HEADING}\n" + "\n\n".join(texts)
