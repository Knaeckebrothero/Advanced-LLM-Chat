"""
System prompt for the agent.

The prompt is the identity paragraph (or a persona's prompt in its place),
followed by one section per enabled tool group, so the file access, graph and
knowledge base and past chat instructions stay when a persona is used. The agent's
skills (with_skills()) and MCP servers (with_mcp_servers()) come next. With the
knowledge base, the agent's memory follows (with_memory()). A conversation's system
messages come last (with_instructions()).
"""
import logging
import re
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
- To show a file to the user, place it in your answer as a Markdown image with the file's name as the address: ![A red fox in the snow](fox-1.png). It appears at that place in your text: an image as the picture, any other file as a card to open. Put it on a line of its own, next to what you say about it; several in a row appear side by side. An image a tool created is only a small preview for the user until you place it: place the ones worth looking at.
Name a file by its name, or by its fileId when several have the same name. Only files of this conversation can be placed. The chat can't display images from web addresses: give those as links, never as Markdown images."""

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

# Added when the past chat tools are enabled (docs/past_chats.md); they come only with the knowledge base
CHAT_PROMPT = r"""## Past Chats:
You can search and read your earlier conversations with this user: the ones that belong to your memory, this one included. Your memory and notes are summaries; the chats are the source, word for word.
- Search them when the user refers to an earlier conversation ("like we discussed", "last time", "you said"), asks what you talked about, or you need a detail your memory and notes don't have.
- chat_search takes a regular expression, case-insensitive. Put alternatives and both languages into one pattern, e.g. "\bmother\b|\bmom\b|mutter|mama"; a part of a word also finds longer words. With many hits, make the pattern more specific or limit it with after and before; with none, try other words before you give up.
- chat_list shows the conversations by date, e.g. for "what did we talk about last week".
- Read around a hit with chat_read before you rely on a single line.
- Say which conversation and date something comes from. If you find nothing, say so instead of guessing.
- An earlier chat may have been roleplay or fiction, or with another agent: what was said in character is not a fact about the user.
- What you find that matters beyond this conversation belongs in your memory or a note, as usual."""

CHAT_TOOL_NAMES = set(TOOL_GROUPS["past_chats"])

# Added with the tool hide_chat (the tool group auto_hide); HIDE_KB_PROMPT also with the knowledge base
HIDE_PROMPT = """## Hidden content:
The user's devices have a family mode, which hides some content, for example when someone else may see the screen. You mark that content, so family mode can hide it. What to hide, in the user's words:
<what-to-hide>
{definition}
</what-to-hide>
Anything else stays visible.
- Once this conversation turns to such content, hide it with hide_chat, once; it stays hidden. Not for a single passing word.
- If the user says it shouldn't be hidden, or the tool says the user decided, leave it as it is.
- Hiding only decides what family mode shows: don't comment on it, and don't let it change how you answer."""

HIDE_KB_PROMPT = """- What you save about such content is hidden too: write such a note with hidden: true and save such a line of the memory with hidden: true; in a note that isn't hidden, end such a line with the tag #hidden. In a hidden conversation, what you save is hidden on its own; pass hidden: false for a line that needn't be, such as the user's name."""


def hide_prompt(definition: str, with_knowledge_base: bool) -> str:
    """The section on hidden content: what to hide (the user's text) and, with the knowledge base, how to save it."""
    prompt = HIDE_PROMPT.format(definition=definition.strip())
    return prompt + "\n" + HIDE_KB_PROMPT if with_knowledge_base else prompt


# The section in a system prompt: from its heading to the next section, or to the end
_HIDE_SECTION = re.compile(r"(?:\A|\n\n)(" + re.escape(HIDE_PROMPT.split("\n", 1)[0]) + r"\n.*?)(?=\n\n## |\Z)", re.S)


def hide_section(system_prompt: str) -> str:
    """The section on hidden content in a system prompt, '' if it has none."""
    found = _HIDE_SECTION.search(system_prompt or "")
    return found.group(1) if found else ""


def without_hide_section(system_prompt: str) -> str:
    """A system prompt without its section on hidden content: what a device in family mode is shown of it."""
    return _HIDE_SECTION.sub("", system_prompt or "").lstrip("\n")

# The section of the agent's skills (docs/skills.md), with the tool use_skill
SKILLS_HEADING = "## Skills:"
SKILLS_INTRO = ("You have skills: instructions for particular kinds of work, with what you would otherwise miss. "
                "Before every answer, go through the list below and decide for each skill whether the request falls "
                "under its description. If one does, your first action is to call use_skill with its name, before you "
                "write anything, even if you think you know how; then follow it. Skip this only for a skill whose text "
                "is already in this conversation.")


def with_skills(system_prompt: str, skills: Iterable[dict]) -> str:
    """
    The system prompt with a section that lists the agent's skills by name and description,
    for an answer that has the tool use_skill (skill_tools() in backend/llm/tools.py).

    Args:
        skills: The agent's enabled skills ({"name", "description"}); none leaves the prompt as it is.
    """
    lines = [f"- {skill['name']}: {' '.join(skill['description'].split())}" for skill in skills]
    if not lines:
        return system_prompt
    return f"{system_prompt}\n\n{SKILLS_HEADING}\n{SKILLS_INTRO}\n" + "\n".join(lines)


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
    hide_definition: Optional[str] = None,
) -> str:
    """
    Build the agent's system prompt.

    Args:
        persona_prompt: A rendered persona prompt that replaces the identity paragraph, or None.
        tools: The tools the model gets (a registry or tool names); None or empty for no tools.
        hide_definition: What the agent hides on its own (with hide_chat); the section is left out without it.

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
    if names & CHAT_TOOL_NAMES:
        sections.append(CHAT_PROMPT)
    if "hide_chat" in names:
        if hide_definition and hide_definition.strip():
            sections.append(hide_prompt(hide_definition, bool(names & KB_TOOL_NAMES)))

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
    section = f"{INSTRUCTIONS_HEADING}\n" + "\n\n".join(texts)
    # A conversation can have no system prompt of its own (manual editing): then they are all of it
    return f"{system_prompt}\n\n{section}" if system_prompt else section


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
