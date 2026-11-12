"""
System prompt for the agent.

The prompt is the identity paragraph (or a persona's prompt in its place),
followed by one section per enabled tool group, so the file access, graph and
knowledge base instructions stay when a persona is used. With the knowledge
base, the agent's memory follows (with_memory()). A conversation's system
messages come last (with_instructions()).
"""
import logging
from datetime import date, datetime, timezone, tzinfo
from typing import Iterable, Optional, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..config import MEMORY_TIME_ZONE
from .tools import TOOL_GROUPS, ToolRegistry

log = logging.getLogger(__name__)

# Who the assistant is; a persona prompt replaces this paragraph
IDENTITY_PROMPT = (
    "You are a helpful and knowledgeable assistant. Answer clearly and accurately, and say so honestly "
    "when you don't know something. Respond in the same language as the user."
)

# Added when the model has any tools
TOOLS_PROMPT = "Use your tools when they help you give a better answer."

# Added when web search is enabled
WEB_SEARCH_PROMPT = "Use web search for current events or facts you are unsure about."

# Added when the file tools are enabled (docs/files.md)
FILE_ACCESS_PROMPT = """## Files:
This conversation has its own files: what the user attached, and what your tools created in it (e.g. generated images). You only see the files of this conversation.
- What the user attaches to their latest message is in that message. In later messages it appears as a placeholder like [Attachment: report.pdf (fileId: abc123) - 5 pages, PDF document].
- list_files() lists the conversation's files. Use it when the user refers to a file you can't find, e.g. an image from an earlier answer.
- read_file(file="report.pdf") gives you a file's content; for an image, the image itself or a description of it. read_file(file="report.pdf", query="What is the revenue?") asks a question about a file you can't see yourself, read_file(file="report.pdf", pages=[1, 3]) reads some pages of a PDF.
- show_file(files=["fox-1.png"]) shows files to the user above the text of your answer, images large. An image a tool created is only a small preview for the user until you show it: show the ones worth looking at, and never say you showed a file unless show_file confirmed it.
Name a file by its name, or by its fileId when several have the same name. The chat can't display images from web addresses: don't put image links or Markdown images into your answer, show the file instead."""

FILE_TOOL_NAMES = set(TOOL_GROUPS["files"])

# Added when the Neo4j knowledge graph tools are enabled
GRAPH_PROMPT = """## Knowledge Graph:
You have read access to a Neo4j knowledge graph. Call get_graph_schema first to learn which node labels, relationship types and properties exist. Then use search_graph to find nodes by text, or query_graph to run a read-only Cypher query."""

GRAPH_TOOL_NAMES = {"get_graph_schema", "search_graph", "query_graph"}

# Added when the knowledge base tools are enabled (an agent that selects the group, a signed-in user).
# The parts on what to save and how are also the instructions of the memory review
# (backend/services/memory_review.py).
KB_SAVE_RULES = """When to save something (right away, in the same answer):
- The user tells you something about themselves, their work, the people in their life, their plans, projects, feelings or health that could matter in later conversations. Personal and sensitive topics included: the user wants everything kept.
- The user corrects you or says how they want you to answer or work: keep it as a preference.
- A decision is made, a goal is set, or something is agreed on, started or finished.
- The user asks you to remember something. When they ask you to forget something, remove the line (memory_remove) or archive the note (kb_archive).
- You worked something out that took effort, such as research, a plan or a result: write a note.
When in doubt, save it: a line too many costs little, a forgotten detail can't be brought back."""

KB_HOW_RULES = """How to save it:
- A fact that fits on one line goes into the memory (memory_add). Details, lists, numbers and anything longer go into a note (kb_write), plus a short line in the memory that points to it, e.g. "Trip to Lisbon in May: dates, budget, hotel → [[lisbon-trip]]". Before writing a note, search for one on the topic (kb_search) and change it (kb_update) instead of writing a second one. Link related notes with [[slug]].
- Keep the memory short and current: one fact per line, under headings such as "About the user", "Preferences", "Ongoing" and "Where things are". When something changes, replace its line (memory_replace) rather than adding another one, and remove what is no longer true (memory_remove).
- Write down only what the user said or what you found out, never details you assumed or added. Leave out only what matters for nothing beyond the current conversation."""

KB_PROMPT = f"""## Knowledge Base and Memory:
You keep two things for this user that last across all of your conversations with them:
- Your memory: short lines, shown below under "Your memory", that are part of every conversation. It holds what you should always have in mind about the user, and where the details are.
- The knowledge base: Markdown notes with the details, like a notebook. You see a note only when you search for it (kb_search, kb_list) or read it (kb_read).

{KB_SAVE_RULES}

{KB_HOW_RULES}

When to look something up:
- Start from your memory: it tells you what you know and which note has the details. Read that note (kb_read) when you need them.
- When the user refers to an earlier conversation or asks about something you may have written down, search the knowledge base before you say you don't know.
- Lines and notes carry their dates and can be outdated; if something seems to have changed, ask.

Mention briefly when you save or change something. Never say you saved something unless the tool confirmed it."""

# Heads the agent's memory (with_memory())
MEMORY_HEADING = "## Your memory:"
MEMORY_INTRO = "Your notes about this user from earlier conversations, which they can read and change. Follow the preferences in them."
MEMORY_EMPTY = "Your memory of this user is still empty."

KB_TOOL_NAMES = set(TOOL_GROUPS["knowledge_base"])

# Heads a conversation's system messages, after the rest of the prompt
INSTRUCTIONS_HEADING = "## Instructions for this conversation:"

# The section of the MCP servers an answer has tools from (docs/mcp.md)
MCP_HEADING = "## Tools from MCP servers:"
MCP_INTRO = ("Some of your tools come from MCP servers, external services connected to this chat. Their names "
             "start with the server's prefix. Mind what a tool changes outside this chat before you call it.")
MCP_INSTRUCTIONS_CHARS = 2000
MCP_UNAVAILABLE_INTRO = ("Not available in this answer (their tools may appear in earlier answers of this conversation, "
                         "they just can't be used now; tell the user what to do if they ask for them):")


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
    if names & FILE_TOOL_NAMES:
        sections.append(FILE_ACCESS_PROMPT)
    if names & GRAPH_TOOL_NAMES:
        sections.append(GRAPH_PROMPT)
    if names & KB_TOOL_NAMES:
        sections.append(KB_PROMPT)

    return "\n\n".join(sections)


def memory_time_zone() -> tzinfo:
    """The time zone of the memory's dates (MEMORY_TIME_ZONE; UTC for an unknown name)."""
    try:
        return ZoneInfo(MEMORY_TIME_ZONE)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning(f"Unknown MEMORY_TIME_ZONE {MEMORY_TIME_ZONE!r}, using UTC")
        return timezone.utc


def memory_today() -> date:
    """Today in the memory's time zone: the date of a new memory line and of "today" in the prompt."""
    return datetime.now(memory_time_zone()).date()


def with_memory(system_prompt: str, memory: Optional[str], today: Optional[date] = None) -> str:
    """
    The system prompt followed by the agent's memory of the user (the memory note of its knowledge
    base), for an agent with the knowledge base tools. Comes before the conversation's instructions.

    It starts with today's date (memory_today() unless given), so the model dates what it saves and
    can tell how old a line is, also when the persona's prompt has no {{date}}.
    """
    day = today or memory_today()
    text = (memory or "").strip()
    body = f"{MEMORY_INTRO}\n<memory>\n{text}\n</memory>" if text else MEMORY_EMPTY
    return f"{system_prompt}\n\n{MEMORY_HEADING}\nToday is {day:%A}, {day.isoformat()}. {body}"


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


def with_mcp_servers(system_prompt: str, servers: Iterable[dict], unavailable: Iterable[dict] = ()) -> str:
    """
    The system prompt with a section on the MCP servers of the answer: the ones it has tools from,
    and the ones that give none this time (the model would otherwise take tool results of earlier
    answers for made up).

    Args:
        servers: {"name", "prefix", "description", "instructions"} per server.
        unavailable: {"name", "prefix", "reason"} per server without tools this time.
    """
    lines = []
    for server in servers:
        line = f"- **{server['name']}** (tools `{server['prefix']}__*`)"
        if server.get("description"):
            line += f": {server['description'].strip()}"
        instructions = (server.get("instructions") or "").strip()
        if instructions:
            if len(instructions) > MCP_INSTRUCTIONS_CHARS:
                instructions = instructions[:MCP_INSTRUCTIONS_CHARS].rstrip() + " [...]"
            line += "\n  The server's instructions:\n  " + instructions.replace("\n", "\n  ")
        lines.append(line)
    missing = [f"- **{server['name']}** (tools `{server['prefix']}__*`): {server['reason']}" for server in unavailable]
    if not lines and not missing:
        return system_prompt
    section = f"{system_prompt}\n\n{MCP_HEADING}\n{MCP_INTRO}"
    if lines:
        section += "\n" + "\n".join(lines)
    if missing:
        section += f"\n{MCP_UNAVAILABLE_INTRO}\n" + "\n".join(missing)
    return section
