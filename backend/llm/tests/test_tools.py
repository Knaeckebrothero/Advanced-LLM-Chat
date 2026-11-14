"""
Offline test of the tool groups that personas select (no API keys or database needed).

    python -m backend.llm.tests.test_tools

Covers: tools_for_groups() with no selection, an empty one and single groups,
unavailable groups (NEO4J_ENABLED off, TAVILY_API_KEY unset) and their
reasons, the opt-in knowledge base with the memory tools (only when selected,
only for signed-in users), web addresses (web_fetch: opt-in, never for guests,
bound to the answer; the tool itself: test_web_fetch.py), the past chat tools (opt-in, only with the knowledge
base, the user and memory bound; the regular expressions translated for
Postgres), the system prompt sections for the selected tools,
the memory in the prompt (with_memory, a fake memory store), the tools
stream-generate sends for a conversation's persona (_agent_tools, with a fake
database; the shared knowledge base, or the persona's own with own_memory), and
the file tools (fake file rows, temporary FILES_DIR): they only see the files of
the conversation and user they are built for, find a file by name or ID, give
a vision model an image itself (scaled) and a text-only model a description
(the vision helper's error is not cached as one), and show files to the user.
Looking closer at an image (read_file's region): a part at the image's own
resolution, in every way an image can be turned, for both kinds of model.
The knowledge base tools themselves need Postgres:
backend/services/tests/knowledge_base_test.py.
"""
import asyncio
import base64
import io
import json
import os
import sys
import tempfile
import traceback
from contextlib import contextmanager
from dataclasses import replace
from typing import get_args

from backend.api import messages
from backend.catalog import resolver
from backend.llm import tools as tools_module
from backend.llm.prompts import (_ALSO_KEPT_FILES, CHAT_PROMPT, FILE_ACCESS_PROMPT, GRAPH_PROMPT, KB_PROMPT, MEMORY_EMPTY,
                                 MEMORY_HEADING, WEB_FETCH_PROMPT, WEB_SEARCH_PROMPT, build_system_prompt,
                                 with_instructions, with_memory)
from backend.llm.tools import (OPT_IN_GROUPS, TOOL_GROUPS, ToolInputError, ToolText, default_tools,
                               knowledge_base_tools,
                               tool_group_status, tool_message_content, tools_for_groups)
from backend.llm.types import ModelConfig
from backend.models.catalog import ToolGroup
from backend.services import file_store, file_utils, past_chats
from backend.services.file_retrieval_service import get_file_retrieval_service
from backend.services.tools import web_search_tools

FILE_TOOLS = ["list_files", "read_file"]
GRAPH_TOOLS = ["get_graph_schema", "search_graph", "query_graph"]
KB_TOOLS = ["kb_search", "kb_list", "kb_read", "kb_write", "kb_update", "kb_archive",
            "memory_add", "memory_replace", "memory_remove"]
CHAT_TOOLS = ["chat_search", "chat_list", "chat_read"]


@contextmanager
def configured(neo4j: bool, tavily: bool):
    """Switch the graph and web search tools on or off for the duration of a test."""
    saved = tools_module.NEO4J_ENABLED, web_search_tools.is_web_search_available
    tools_module.NEO4J_ENABLED = neo4j
    web_search_tools.is_web_search_available = lambda: tavily
    try:
        yield
    finally:
        tools_module.NEO4J_ENABLED, web_search_tools.is_web_search_available = saved


async def test_groups_match_the_api_model():
    assert list(TOOL_GROUPS) == list(get_args(ToolGroup)), (list(TOOL_GROUPS), get_args(ToolGroup))


async def test_selection_filters_the_enabled_tools():
    with configured(neo4j=True, tavily=True):
        everything = default_tools().names()
        assert sorted(everything) == sorted([*FILE_TOOLS, "web_search", *GRAPH_TOOLS]), everything
        assert tools_for_groups(None).names() == everything
        assert len(tools_for_groups([])) == 0
        assert tools_for_groups(["files"]).names() == FILE_TOOLS
        assert tools_for_groups(["web_search"]).names() == ["web_search"]
        assert tools_for_groups(["knowledge_graph"]).names() == GRAPH_TOOLS
        assert sorted(tools_for_groups(["files", "knowledge_graph", "nonsense"]).names()) == \
            sorted([*FILE_TOOLS, *GRAPH_TOOLS])


async def test_knowledge_base_is_opt_in():
    assert OPT_IN_GROUPS == {"web_fetch", "knowledge_base", "past_chats", "user_mcp"}
    assert TOOL_GROUPS["knowledge_base"] == tuple(KB_TOOLS)
    # The users' own MCP servers: no static tools, backend/services/mcp/tools.py adds theirs per answer
    assert TOOL_GROUPS["user_mcp"] == () and len(tools_for_groups(["user_mcp"], user_id=1)) == 0
    with configured(neo4j=True, tavily=True):
        # Never part of "every enabled tool"
        assert not set(KB_TOOLS) & set(default_tools(user_id=1).names())
        assert not set(KB_TOOLS) & set(tools_for_groups(None, user_id=1).names())
        # Selected: for a signed-in user only
        assert tools_for_groups(["knowledge_base"], user_id=1).names() == KB_TOOLS
        assert tools_for_groups(["files", "knowledge_base"], user_id=1).names() == [*FILE_TOOLS, *KB_TOOLS]
        assert len(tools_for_groups(["knowledge_base"], user_id=1, guest=True)) == 0
        assert len(tools_for_groups(["knowledge_base"])) == 0
        # The user is bound, not a schema argument
        for tool in tools_for_groups(["knowledge_base"], user_id=1):
            assert tool.parameters["type"] == "object"
            assert not {"user_id", "writer"} & set(tool.parameters["properties"]), tool.name


async def test_web_addresses_are_opt_in():
    with configured(neo4j=True, tavily=True):
        # Never part of "every enabled tool": an agent that may open any web address is picked for it
        assert "web_fetch" not in default_tools(user_id=1).names()
        assert "web_fetch" not in tools_for_groups(None, user_id=1).names()
        assert tools_for_groups(["web_fetch"], user_id=1).names() == ["web_fetch"]
        assert tools_for_groups(["web_fetch", "files", "web_search"], user_id=1).names() == \
            [*FILE_TOOLS, "web_search", "web_fetch"]
        # Not for a guest: the server would fetch whatever an anonymous visitor names
        assert len(tools_for_groups(["web_fetch"], user_id=1, guest=True)) == 0
        assert len(tools_for_groups(["web_fetch"])) == 0
        assert tools_for_groups(["files", "web_fetch"], user_id=1, guest=True).names() == FILE_TOOLS
        # The user, the conversation and the answer are bound, not arguments
        tool = tools_for_groups(["web_fetch"], user_id=3, conversation={"id": "conv-7"}, vision=True,
                                answer_id=99).get("web_fetch")
        assert tool.func.keywords == {"user_id": 3, "conversation_id": "conv-7", "answer_id": 99, "vision": True}
        assert set(tool.parameters["properties"]) == {"url", "start"}
        # The prompt mentions it only for an agent that has it
        assert WEB_FETCH_PROMPT in build_system_prompt(None, tools_for_groups(["web_fetch"], user_id=1))
        assert WEB_FETCH_PROMPT not in build_system_prompt(None, tools_for_groups(None, user_id=1))
    with configured(neo4j=False, tavily=False):
        # Needs no key and no service
        assert tools_for_groups(["web_fetch"], user_id=1).names() == ["web_fetch"]


async def test_unavailable_groups_stay_off():
    with configured(neo4j=False, tavily=False):
        assert default_tools().names() == FILE_TOOLS
        assert len(tools_for_groups(["web_search", "knowledge_graph"])) == 0
        status = {entry["id"]: entry for entry in tool_group_status()}
        assert list(status) == list(TOOL_GROUPS)
        assert status["files"] == {"id": "files", "available": True, "reason": None, "optIn": False, "requires": None}
        assert status["web_search"] == {"id": "web_search", "available": False,
                                        "reason": "TAVILY_API_KEY is not set", "optIn": False, "requires": None}
        assert status["web_fetch"] == {"id": "web_fetch", "available": True, "reason": None, "optIn": True,
                                       "requires": None}
        assert status["knowledge_graph"] == {"id": "knowledge_graph", "available": False,
                                             "reason": "NEO4J_ENABLED is off", "optIn": False, "requires": None}
        assert status["knowledge_base"] == {"id": "knowledge_base", "available": True, "reason": None, "optIn": True,
                                            "requires": None}
        assert status["past_chats"] == {"id": "past_chats", "available": True, "reason": None, "optIn": True,
                                        "requires": "knowledge_base"}
    with configured(neo4j=True, tavily=True):
        assert all(entry["available"] and entry["reason"] is None for entry in tool_group_status())


async def test_prompt_only_describes_selected_tools():
    with configured(neo4j=True, tavily=True):
        files_only = build_system_prompt("You are a pirate.", tools_for_groups(["files"]))
        assert files_only.startswith("You are a pirate.")
        assert FILE_ACCESS_PROMPT in files_only and GRAPH_PROMPT not in files_only
        assert WEB_SEARCH_PROMPT not in files_only
        everything = build_system_prompt(None, tools_for_groups(None))
        assert FILE_ACCESS_PROMPT in everything and GRAPH_PROMPT in everything and WEB_SEARCH_PROMPT in everything
        assert KB_PROMPT not in everything and KB_PROMPT not in files_only
        notebook = build_system_prompt("You keep notes.", tools_for_groups(["knowledge_base"], user_id=1))
        assert notebook.startswith("You keep notes.") and notebook.endswith(KB_PROMPT)
        assert FILE_ACCESS_PROMPT not in notebook
        assert build_system_prompt("You translate.", None) == "You translate."


async def test_past_chats_need_the_knowledge_base():
    assert TOOL_GROUPS["past_chats"] == tuple(CHAT_TOOLS)
    with configured(neo4j=True, tavily=True):
        # Opt-in: never part of "every enabled tool"
        assert not set(CHAT_TOOLS) & set(tools_for_groups(None, user_id=1).names())
        # Only with the knowledge base: without it the agent has no memory, so no chats to search
        assert len(tools_for_groups(["past_chats"], user_id=1)) == 0
        assert len(tools_for_groups(["files", "past_chats"], user_id=1)) == len(FILE_TOOLS)
        assert tools_for_groups(["knowledge_base", "past_chats"], user_id=1).names() == [*KB_TOOLS, *CHAT_TOOLS]
        # For signed-in users only
        assert len(tools_for_groups(["knowledge_base", "past_chats"], user_id=1, guest=True)) == 0
        assert len(tools_for_groups(["knowledge_base", "past_chats"])) == 0
        # The user and the memory are bound, not schema arguments
        selected = tools_for_groups(["knowledge_base", "past_chats"], user_id=1, vault=8)
        for name in CHAT_TOOLS:
            tool = selected.get(name)
            assert not {"user_id", "vault", "scope"} & set(tool.parameters["properties"]), name
            assert tool.func.__wrapped__.keywords["scope"] == past_chats.Scope(user_id=1, vault=8), name
        # A device in family mode can't find hidden chats
        hiding = tools_for_groups(["knowledge_base", "past_chats"], user_id=1, vault=8, family_mode=True)
        assert hiding.get("chat_read").func.__wrapped__.keywords["scope"].family_mode
        # The prompt section comes with the tools, after the knowledge base's
        prompt = build_system_prompt("You remember.", selected)
        assert prompt.index(KB_PROMPT) < prompt.index(CHAT_PROMPT)
        assert CHAT_PROMPT not in build_system_prompt("You keep notes.", KB_TOOLS)
    # Postgres reads \b as a backspace: the search translates it outside brackets, keeps escaped backslashes
    assert past_chats.postgres_regex(r"\bcat\b|\Bdog") == r"\ycat\y|\Ydog"
    assert past_chats.postgres_regex(r"a\\b [\b] []\b] [[:alpha:]\b]\b") == r"a\\b [\b] []\b] [[:alpha:]\b]\y"
    assert past_chats.postgres_regex("(?i)lisbon") == "lisbon"
    assert past_chats.literal_regex("C++ (what?) a.b \\x") == r"C\+\+ \(what\?\) a\.b \\x"


async def test_memory_follows_the_tool_sections():
    # The memory comes after the knowledge base section, the conversation's instructions last
    prompt = with_instructions(with_memory(build_system_prompt("You keep notes.", KB_TOOLS),
                                           "## About the user\n- Likes tea (2026-11-04)"), ["Be brief."])
    assert prompt.index(KB_PROMPT) < prompt.index(MEMORY_HEADING) < prompt.index("Be brief.")
    assert "<memory>\n## About the user\n- Likes tea (2026-11-04)\n</memory>" in prompt
    from datetime import date
    assert with_memory("x", None, date(2026, 11, 4)).endswith(
        f"{MEMORY_HEADING}\nToday is Wednesday, 2026-11-04. {MEMORY_EMPTY}")
    assert with_memory("x", "  \n ").endswith(MEMORY_EMPTY)
    # stream-generate adds the memory of the vault the tools write to, only with the memory tools
    saved = messages.kb.get_memory, messages.persona_vault
    asked = []
    messages.kb.get_memory = lambda user_id, vault, family_mode=False: (asked.append((user_id, vault, family_mode))
                                                                      or {"content": f"- vault {vault}"})
    messages.persona_vault = lambda user, conversation: 8
    try:
        user = {"user_id": 1, "email": "a@example.com", "is_guest": False}
        with_kb, note = messages._memory_prompt("p", user, {"persona_id": 8},
                                                tools_for_groups(["knowledge_base"], user_id=1))
        assert with_kb.endswith("<memory>\n- vault 8\n</memory>") and asked == [(1, 8, False)], (with_kb, asked)
        assert note is None, "without a conversation id there is no snapshot, so nothing to note"
        # A device in family mode gets the memory without its hidden lines
        messages._memory_prompt("p", user, {"persona_id": 8}, tools_for_groups(["knowledge_base"], user_id=1), True)
        assert asked.pop() == (1, 8, True)
        assert messages._memory_prompt("p", user, {"persona_id": 8}, tools_for_groups(["files"], user_id=1)) == ("p", None)
        assert messages._memory_prompt("p", user, None, None) == ("p", None) and len(asked) == 1
    finally:
        messages.kb.get_memory, messages.persona_vault = saved


class FakeDB:
    """The persona lookup of the resolver."""

    def __init__(self, personas):
        self.personas = {persona["id"]: persona for persona in personas}

    def get_persona_by_id(self, persona_id):
        return self.personas.get(persona_id)


def persona(persona_id, tools, **extra):
    return {"id": persona_id, "name": f"P{persona_id}", "system_prompt": "x", "tools": tools,
            "enabled": True, "available_to_guests": False, **extra}


async def test_stream_generate_tools_follow_the_persona():
    user = {"user_id": 1, "email": "a@example.com", "is_guest": False}
    guest = {"user_id": 0, "email": "guest@guest.com", "is_guest": True}
    config = ModelConfig(id=1, display_name="Test", model_id="test", provider_id=1, provider_name="Test",
                         kind="openai_compatible", base_url=None, supports_tools=True)
    saved_db = resolver.db
    resolver.db = FakeDB([persona(1, []), persona(2, ["files"]), persona(3, None),
                          persona(4, [], enabled=False), persona(6, ["files", "knowledge_base"]),
                          persona(7, ["knowledge_base"], available_to_guests=True),
                          persona(8, ["knowledge_base"], own_memory=True),
                          persona(9, ["knowledge_base"], own_memory=True, enabled=False),
                          persona(12, ["files", "web_fetch"], available_to_guests=True)])
    try:
        with configured(neo4j=True, tavily=True):
            def names(user, persona_id, config=config):
                tools = messages._agent_tools(user, {"persona_id": persona_id}, config)
                return None if tools is None else sorted(tools.names())

            everything = sorted(default_tools().names())
            assert names(user, 1) is None, "tools [] -> no tools at all"
            assert names(user, 2) == FILE_TOOLS
            assert names(user, 3) == everything, "tools null -> every enabled tool"
            assert names(user, None) == everything, "no persona -> every enabled tool"
            assert names(user, 4) == everything, "disabled persona is skipped"
            assert names(guest, 1) == everything, "persona not available to guests is skipped"
            assert names(user, 2, replace(config, supports_tools=False)) is None
            # The knowledge base only with a selection, never for guests
            assert names(user, 6) == sorted([*FILE_TOOLS, *KB_TOOLS])
            assert names(user, 7) == sorted(KB_TOOLS)
            assert names(guest, 7) is None, "a guest gets no knowledge base, and here no tools at all"
            # Web addresses the same; what the agent fetches is recorded with the answer being written
            assert names(user, 12) == sorted([*FILE_TOOLS, "web_fetch"]) and names(guest, 12) == FILE_TOOLS
            fetch = messages._agent_tools(user, {"id": "conv-1", "persona_id": 12}, config, answer_id=42).get("web_fetch")
            assert fetch.func.keywords == {"user_id": 1, "conversation_id": "conv-1", "answer_id": 42, "vision": False}
            # Its writes record the conversation and its agent; it is the shared knowledge base (vault 0)
            tools = messages._agent_tools(user, {"id": "conv-1", "persona_id": 6}, config)
            writer = tools.get("kb_write").func.__wrapped__.keywords["writer"]
            assert (writer.user_id, writer.conversation_id, writer.persona_id, writer.vault) == (1, "conv-1", 6, 0)
            assert tools.get("memory_add").func.__wrapped__.keywords["writer"] == writer
            assert tools.get("kb_search").func.__wrapped__.keywords == {"user_id": 1, "vault": 0, "family_mode": False}
            assert not writer.from_hidden and not writer.family_mode
            # Its notes keep files of the conversation (the parameter files), and the file tools read the kept
            # ones, of the same knowledge base. Neither without the other group, nor for the memory review
            assert "files" in tools.get("kb_write").parameters["properties"]
            assert "files" in tools.get("kb_update").parameters["properties"]
            assert tools.get("read_file").func.keywords["knowledge_base"] == (0, False)
            assert tools.get("kb_read").func.__wrapped__.keywords["reads_files"] is True
            assert "knowledge base" in tools.get("read_file").description
            assert _ALSO_KEPT_FILES in build_system_prompt(None, tools)
            only_files = messages._agent_tools(user, {"id": "conv-1", "persona_id": 2}, config)
            assert only_files.get("read_file").func.keywords["knowledge_base"] is None
            assert "knowledge base" not in only_files.get("read_file").description
            assert FILE_ACCESS_PROMPT in build_system_prompt(None, only_files)
            only_notes = messages._agent_tools(user, {"id": "conv-1", "persona_id": 7}, config)
            assert only_notes.get("kb_read").func.__wrapped__.keywords["reads_files"] is False
            assert "Images and other files" in build_system_prompt(None, only_notes)
            review = knowledge_base_tools(1, {"id": "conv-1"}, author="review")
            assert "files" not in next(tool for tool in review if tool.name == "kb_write").parameters["properties"]
            # Family mode: a device in it binds family_mode to every tool that reads or writes;
            # what is written in a hidden chat (marked, or of a hidden agent) is marked, unless it goes into
            # a hidden agent's own knowledge base
            tools = messages._agent_tools(user, {"id": "conv-1", "persona_id": 6}, config, hide=True)
            assert tools.get("kb_read").func.__wrapped__.keywords == {"user_id": 1, "vault": 0, "family_mode": True,
                                                                      "reads_files": True}
            assert tools.get("read_file").func.keywords["knowledge_base"] == (0, True)
            assert tools.get("kb_update").func.__wrapped__.keywords["writer"].family_mode
            assert messages._agent_tools(user, {"id": "c", "persona_id": 6, "hidden": True}, config) \
                .get("memory_add").func.__wrapped__.keywords["writer"].from_hidden
            resolver.db.personas[10] = persona(10, ["knowledge_base"], hidden=True)
            resolver.db.personas[11] = persona(11, ["knowledge_base"], own_memory=True, hidden=True)
            assert messages._agent_tools(user, {"id": "c", "persona_id": 10}, config) \
                .get("kb_write").func.__wrapped__.keywords["writer"].from_hidden, "the agent is hidden"
            assert not messages._agent_tools(user, {"id": "c", "persona_id": 11, "hidden": True}, config) \
                .get("kb_write").func.__wrapped__.keywords["writer"].from_hidden, "its own knowledge base is hidden anyway"
            # An agent with its own memory reads and writes its own knowledge base (vault: its id)
            tools = messages._agent_tools(user, {"id": "conv-2", "persona_id": 8}, config)
            assert tools.get("kb_write").func.__wrapped__.keywords["writer"].vault == 8
            assert tools.get("memory_remove").func.__wrapped__.keywords["writer"].vault == 8
            assert tools.get("kb_read").func.__wrapped__.keywords == {"user_id": 1, "vault": 8, "family_mode": False,
                                                                      "reads_files": False}
            assert resolver.persona_vault(user, {"persona_id": 8}) == 8
            assert resolver.persona_vault(user, {"persona_id": 6}) == 0
            assert resolver.persona_vault(user, {"persona_id": 9}) == 0, "a disabled persona counts as none"
            assert resolver.persona_vault(user, None) == 0
        with configured(neo4j=False, tavily=False):
            # Only unavailable groups selected: no tools, not an empty tool list
            resolver.db = FakeDB([persona(5, ["web_search"])])
            assert messages._agent_tools(user, {"persona_id": 5}, config) is None
    finally:
        resolver.db = saved_db


class FakeFileDB:
    """The rows of uploaded_files the file store reads."""

    def __init__(self, rows):
        self.rows = rows

    def get_conversation_files(self, conversation_id, user_id):
        return [row for row in self.rows if row["conversation_id"] == conversation_id and row["user_id"] == user_id]


def file_row(file_id, user_id, conversation_id, name, mime_type="text/plain", **extra):
    return {"file_id": file_id, "user_id": user_id, "conversation_id": conversation_id, "name": name,
            "mime_type": mime_type, "source": "upload", **extra}


def png(width, height) -> bytes:
    from PIL import Image
    output = io.BytesIO()
    Image.new("RGB", (width, height), (200, 120, 40)).save(output, "PNG")
    return output.getvalue()


async def test_file_tools_see_only_the_conversation():
    files_dir = tempfile.mkdtemp(prefix="file-tool-test-")
    for name, data in (("file_1_aa.txt", b"My notes"), ("file_2_bb.txt", b"Their notes"),
                       ("file_3_cc.txt", b"Another chat"), ("file_4_dd.png", png(3136, 1568)),
                       ("file_5_ee.txt", b"First"), ("file_6_ff.txt", b"Second")):
        with open(os.path.join(files_dir, name), "wb") as f:
            f.write(data)
    saved = file_utils.FILES_DIR, file_store.db
    file_utils.FILES_DIR = files_dir
    file_store.db = FakeFileDB([
        file_row("file_1_aa", 1, "conv-1", "notes.txt", size_bytes=8),
        file_row("file_2_bb", 2, "conv-9", "theirs.txt"),
        file_row("file_3_cc", 1, "conv-2", "other.txt"),
        file_row("file_4_dd", 1, "conv-1", "civitai-1.png", "image/png", width=3136, height=1568, source="tool",
                 origin="Civitai: Run step", details='{"prompt": "a fox knight"}'),
        file_row("file_5_ee", 1, "conv-3", "a.txt"),
        file_row("file_6_ff", 1, "conv-3", "a.txt"),
    ])
    service = get_file_retrieval_service()
    saved_describe = service._get_image_description
    asked = []

    async def describe(file_id, file_path, mime_type, query=None):
        asked.append((file_id, query))
        return f"A fox ({query or 'described'})"

    service._get_image_description = describe
    try:
        mine = tools_for_groups(["files"], user_id=1, conversation={"id": "conv-1"})
        listing = await mine.call("list_files", {})
        assert listing.startswith("2 files in this conversation"), listing
        assert "1. notes.txt (text/plain, 8 B): uploaded by the user" in listing, listing
        assert "2. civitai-1.png (image/png, 3136×1568 px, " in listing, listing
        assert "created by Civitai: Run step" in listing and "other.txt" not in listing, listing
        assert "fileId" not in listing, "IDs only where names repeat"

        # By name (also without its case) or by file ID
        assert await mine.call("read_file", {"file": "notes.txt"}) == "My notes"
        assert await mine.call("read_file", {"file": "NOTES.TXT"}) == "My notes"
        assert await mine.call("read_file", {"file": "file_1_aa"}) == "My notes"
        # Another conversation's file, another user's and a missing one are all not found
        for reference in ("other.txt", "file_3_cc", "theirs.txt", "file_2_bb", "file_9_ff"):
            try:
                await mine.call("read_file", {"file": reference})
                raise AssertionError(f"read {reference}")
            except ToolInputError as e:
                assert str(e) == f"No file '{reference}' in this conversation. list_files shows the files it has", e
        # The model can't choose the user or the conversation: not in the schemas, dropped
        for tool in mine:
            assert not {"user_id", "conversation_id", "vision"} & set(tool.parameters["properties"]), tool.name
        try:
            await mine.call("read_file", {"file": "other.txt", "conversation_id": "conv-2", "user_id": 2})
            raise AssertionError("read another conversation's file")
        except ToolInputError:
            pass

        # A text-only model gets an image as a description, a question is answered
        described = await mine.call("read_file", {"file": "civitai-1.png"})
        assert described == 'A fox (described)\n[Made with these arguments: {"prompt": "a fox knight"}]', described
        assert not getattr(described, "images", None)
        assert (await mine.call("read_file", {"file": "civitai-1.png", "query": "Which animal?"})).startswith(
            "A fox (Which animal?)")
        assert asked == [("file_4_dd", None), ("file_4_dd", "Which animal?")], asked

        # A vision model gets the image itself, scaled down, and how it was made
        seeing = tools_for_groups(["files"], user_id=1, conversation={"id": "conv-1"}, vision=True)
        seen = await seeing.call("read_file", {"file": "civitai-1.png"})
        assert isinstance(seen, ToolText) and len(seen.images) == 1 and len(asked) == 2, seen
        assert seen.startswith("civitai-1.png (image/png, 3136×1568 px, ") and "The image follows." in seen, seen
        assert '[Made with these arguments: {"prompt": "a fox knight"}]' in seen, seen
        url = seen.images[0]["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,"), url[:40]
        from PIL import Image
        assert Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).size == (1568, 784)
        content = tool_message_content(seen)
        assert content[0] == {"type": "text", "text": str(seen)} and content[1] == seen.images[0]
        # It needs nobody to answer a question about an image for it: the image again, no helper
        again = await seeing.call("read_file", {"file": "civitai-1.png", "query": "Colour?"})
        assert len(again.images) == 1 and len(asked) == 2, (again, asked)
        assert "query" in seeing.get("read_file").parameters["properties"], "still there for PDFs"

        # No tool shows a file: the agent places it in its answer's text, and is told how
        assert mine.get("show_file") is None
        assert "![A red fox in the snow](fox-1.png)" in FILE_ACCESS_PROMPT and "show_file" not in FILE_ACCESS_PROMPT
        # A file as the chat gets it (a step's metadata, the list of a conversation's files)
        assert file_store.file_ref(file_store.find_file("conv-1", 1, "civitai-1.png")) == {
            "fileId": "file_4_dd", "name": "civitai-1.png", "mimeType": "image/png",
            "size": os.path.getsize(os.path.join(files_dir, "file_4_dd.png")), "width": 3136, "height": 1568}
        # A PDF's preview is its first page as it was rendered at the upload; without one it has none
        from PIL import Image
        for name, data in (("file_7_aa.pdf", b"%PDF-1.4"), ("file_7_aa_page_1.png", png(1240, 1754)),
                           ("file_8_bb.pdf", b"%PDF-1.4")):
            with open(os.path.join(files_dir, name), "wb") as f:
                f.write(data)
        page = file_store.thumbnail("file_7_aa", "small")
        assert page is not None and page.name == "file_7_aa_thumb_small.webp" and Image.open(page).size == (181, 256), page
        assert file_store.thumbnail("file_8_bb", "small") is None
        assert Image.open(file_store.thumbnail("file_4_dd", "small")).size == (256, 128)
        try:
            await mine.call("read_file", {"file": "notes.txt", "pages": "first"})
            raise AssertionError("took a word as a list of pages")
        except ToolInputError as e:
            assert "must be of type array" in str(e), e
        assert await mine.call("read_file", {"file": "notes.txt", "pages": "[1, 2]"}) == "My notes"

        # Files with the same name: listed with their IDs, read by ID
        twins = tools_for_groups(["files"], user_id=1, conversation={"id": "conv-3"})
        listing = await twins.call("list_files", {})
        assert "[fileId: file_5_ee]" in listing and "[fileId: file_6_ff]" in listing, listing
        try:
            await twins.call("read_file", {"file": "a.txt"})
            raise AssertionError("read an ambiguous name")
        except ToolInputError as e:
            assert "Several files" in str(e) and "file_5_ee, file_6_ff" in str(e), e
        assert await twins.call("read_file", {"file": "file_6_ff"}) == "Second"

        # Without a conversation or a user the tools see no files
        for nobody in (tools_for_groups(["files"], user_id=1), tools_for_groups(["files"], conversation={"id": "conv-1"}),
                       default_tools(user_id=1)):
            assert await nobody.call("list_files", {}) == "This conversation has no files."
        # stream-generate builds the tools for the current user, conversation and model
        config = ModelConfig(id=1, display_name="Test", model_id="test", provider_id=1, provider_name="Test",
                             kind="openai_compatible", base_url=None, supports_tools=True, supports_vision=True)
        user = {"user_id": 1, "email": "a@example.com", "is_guest": False}
        tools = messages._agent_tools(user, {"id": "conv-2"}, config)
        assert await tools.call("read_file", {"file": "other.txt"}) == "Another chat"
        tools = messages._agent_tools(user, {"id": "conv-1"}, config)
        assert len((await tools.call("read_file", {"file": "civitai-1.png"})).images) == 1
    finally:
        file_utils.FILES_DIR, file_store.db = saved
        service._get_image_description = saved_describe


async def test_vision_helper_errors_are_not_cached():
    from backend.services import vision_helper
    from backend.services.file_retrieval_service import FileRetrievalService

    class Cache:
        def __init__(self):
            self.stored = {}

        async def get(self, file_id, query=None):
            return self.stored.get((file_id, query))

        async def set(self, file_id, description, query=None):
            self.stored[(file_id, query)] = description

    answers = ["[Error analyzing image: no credits remaining]", "A red circle"]

    class Helper:
        async def describe_image(self, image_data, mime_type, prompt=None):
            return answers.pop(0)

    path = os.path.join(tempfile.mkdtemp(prefix="vision-test-"), "file_1_aa.png")
    with open(path, "wb") as f:
        f.write(png(4, 4))
    saved = vision_helper.get_vision_helper
    vision_helper.get_vision_helper = lambda: Helper()
    try:
        from pathlib import Path
        service = FileRetrievalService(description_cache=Cache())
        # The helper's error goes to the model but is not kept: the next call asks again
        first = await service._get_image_description("file_1_aa", Path(path), "image/png")
        assert vision_helper.is_error(first) and not service.description_cache.stored, first
        assert await service._get_image_description("file_1_aa", Path(path), "image/png") == "A red circle"
        assert service.description_cache.stored == {("file_1_aa", None): "A red circle"}
        assert await service._get_image_description("file_1_aa", Path(path), "image/png") == "A red circle" and not answers
    finally:
        vision_helper.get_vision_helper = saved


def quarters(width: int, height: int):
    """An image whose four quarters have a colour each: red, green, blue, yellow (rows, left to right)."""
    from PIL import Image
    image = Image.new("RGB", (width, height))
    for index, colour in enumerate(((220, 30, 30), (30, 180, 30), (30, 30, 220), (230, 220, 40))):
        image.paste(colour, ((index % 2) * width // 2, (index // 2) * height // 2,
                             (index % 2 + 1) * width // 2, (index // 2 + 1) * height // 2))
    return image


def sent_image(result):
    """The image a tool result carries for the model, opened."""
    from PIL import Image
    (part,) = result.images
    return Image.open(io.BytesIO(base64.b64decode(part["image_url"]["url"].split(",", 1)[1])))


async def test_looking_closer_at_an_image():
    from PIL import Image, ImageChops, ImageOps
    from backend.services import vision_helper

    files_dir = tempfile.mkdtemp(prefix="region-test-")
    quarters(3000, 2000).save(os.path.join(files_dir, "file_7_gg.png"), "PNG")
    with open(os.path.join(files_dir, "file_1_aa.txt"), "wb") as f:
        f.write(b"My notes")
    saved = file_utils.FILES_DIR, file_store.db, vision_helper.get_vision_helper
    file_utils.FILES_DIR = files_dir
    file_store.db = FakeFileDB([
        file_row("file_7_gg", 1, "conv-1", "big.png", "image/png", width=3000, height=2000, size_bytes=9000),
        file_row("file_1_aa", 1, "conv-1", "notes.txt", size_bytes=8),
    ])
    service = get_file_retrieval_service()
    saved_cache = service.description_cache
    asked = []

    class Helper:
        async def describe_image(self, image_data, mime_type, prompt=None):
            with Image.open(io.BytesIO(image_data)) as image:
                asked.append((image.size, mime_type, prompt))
            return f"Described {len(asked)}"

    class Cache:
        stored = {}

        async def get(self, file_id, query=None):
            return self.stored.get((file_id, query))

        async def set(self, file_id, description, query=None):
            self.stored[(file_id, query)] = description

    vision_helper.get_vision_helper = lambda: Helper()
    service.description_cache = Cache()
    try:
        seeing = tools_for_groups(["files"], user_id=1, conversation={"id": "conv-1"}, vision=True)
        # The whole image reaches the model scaled down, and it is told how to look closer
        whole = await seeing.call("read_file", {"file": "big.png"})
        assert sent_image(whole).size == (1568, 1045)
        assert "You see it scaled down to 1568×1045 px. To look closer at a part of it, call read_file with " \
               'region, e.g. {"left": 50, "top": 0, "right": 100, "bottom": 50}.' in whole, whole
        assert "scaled down" not in await seeing.call("read_file", {"file": "notes.txt"})

        # A part no larger than a model takes: the image's own pixels
        top_right = {"left": 50, "top": 0, "right": 100, "bottom": 50}
        part = await seeing.call("read_file", {"file": "big.png", "region": top_right})
        assert str(part) == ("big.png, the part from 50% to 100% of its width and 0% to 50% of its height: "
                             "1500×1000 px of 3000×2000 px, at the image's own resolution. It follows."), part
        closer = sent_image(part)
        assert closer.size == (1500, 1000) and closer.format == "JPEG"
        red, green, blue = closer.convert("RGB").getpixel((750, 500))
        assert green > 150 and red < 80 and blue < 80, "the green quarter"
        # A larger part is scaled like a whole image; edges past the image are the image's
        half = await seeing.call("read_file", {"file": "big.png", "region": {"left": -5, "top": 0, "right": 120, "bottom": 50}})
        assert sent_image(half).size == (1568, 523) and "3000×1000 px of 3000×2000 px, scaled down to 1568×523 px (52%)" in half
        # As shares of the image, and as the JSON text some models send for an object
        for spelled in ({"left": 0.5, "top": 0, "right": 1, "bottom": 0.5}, json.dumps(top_right)):
            assert str(await seeing.call("read_file", {"file": "big.png", "region": spelled})) == str(part), spelled
        small = await seeing.call("read_file", {"file": "big.png", "region": {"left": 10, "top": 60, "right": 12.5, "bottom": 62}})
        assert sent_image(small).size == (75, 40) and "from 10% to 12.5% of its width and 60% to 62%" in small, small
        blue_part = sent_image(small).convert("RGB").getpixel((30, 20))
        assert blue_part[2] > 150 and blue_part[0] < 80, "the blue quarter, bottom left"

        # What is no part of an image
        for arguments, reason in (
                ({"file": "notes.txt", "region": top_right}, "region is for images; notes.txt is text/plain"),
                ({"file": "big.png", "region": {"left": 60, "top": 0, "right": 40, "bottom": 50}}, "right must be greater than left"),
                ({"file": "big.png", "region": {"left": 10, "top": 10, "right": 10.5, "bottom": 50}}, "right must be greater"),
                ({"file": "big.png", "region": {"left": 0, "top": 0, "right": 50}}, "needs the four edges"),
                ({"file": "big.png", "region": {"left": "a", "top": 0, "right": 50, "bottom": 50}}, "needs the four edges"),
                ({"file": "big.png", "region": "the top right"}, "must be of type object")):
            try:
                await seeing.call("read_file", arguments)
                raise AssertionError(f"read {arguments}")
            except ToolInputError as e:
                assert reason in str(e), e
        assert not asked, "a vision model needs no helper"

        # A text-only model: the helper looks at the part, and answers a question about it. Kept per part
        reading = tools_for_groups(["files"], user_id=1, conversation={"id": "conv-1"})
        told = await reading.call("read_file", {"file": "big.png", "region": top_right})
        assert told == ("big.png, the part from 50% to 100% of its width and 0% to 50% of its height: 1500×1000 px "
                        "of 3000×2000 px, at the image's own resolution.\nDescribed 1"), told
        assert not getattr(told, "images", None) and asked == [((1500, 1000), "image/jpeg", None)]
        assert (await reading.call("read_file", {"file": "big.png", "region": top_right})).endswith("Described 1")
        answered = await reading.call("read_file", {"file": "big.png", "region": top_right, "query": "Which colour?"})
        other = await reading.call("read_file", {"file": "big.png", "region": {"left": 0, "top": 0, "right": 50, "bottom": 50}})
        assert answered.endswith("Described 2") and other.endswith("Described 3") and len(asked) == 3
        assert asked[1] == ((1500, 1000), "image/jpeg", "Which colour?")
        assert set(Cache.stored) == {("file_7_gg", "[part 50,0,100,50] "), ("file_7_gg", "[part 50,0,100,50] Which colour?"),
                                     ("file_7_gg", "[part 0,0,50,50] ")}, Cache.stored
        # The whole image goes to the helper scaled, as to a vision model: a file can have 30 MB
        assert await service._get_image_description("file_7_gg", file_utils.get_file_path("file_7_gg"), "image/png") \
            == "Described 4"
        assert asked[3] == ((1568, 1045), "image/jpeg", None)

        # However an image is stored turned (EXIF orientation), the part is the one of the image as shown
        picture = quarters(1200, 800)
        for orientation in range(1, 9):
            exif = Image.Exif()
            exif[0x0112] = orientation
            name = f"file_{20 + orientation}_aa"
            picture.save(os.path.join(files_dir, name + ".jpg"), "JPEG", quality=95, subsampling=0, exif=exif.tobytes())
            with Image.open(os.path.join(files_dir, name + ".jpg")) as stored:
                shown = ImageOps.exif_transpose(stored)
            for region in ((0.0, 0.0, 0.25, 0.5), (0.5, 0.25, 1.0, 0.75), (0.1, 0.6, 0.35, 0.95), (0.0, 0.0, 1.0, 1.0)):
                cut = file_store.image_part_for_model(name, region)
                box = tuple(round(share * (shown.width, shown.height)[index % 2]) for index, share in enumerate(region))
                with Image.open(io.BytesIO(cut.data)) as got:
                    want = shown.crop(box)
                    assert cut.box == box and got.size == want.size == (cut.width, cut.height), (orientation, region)
                    difference = ImageChops.difference(got.convert("RGB"), want).convert("L")
                    assert sum(difference.getdata()) / (got.width * got.height) < 4, (orientation, region)

        # A camera's photo with more pixels than are decoded at once: a part of it still is, decoded smaller
        huge = os.path.join(files_dir, "file_40_aa.jpg")
        quarters(8000, 6000).save(huge, "JPEG", quality=60)
        assert 8000 * 6000 > file_store.MAX_IMAGE_PIXELS
        cut = file_store.image_part_for_model("file_40_aa", (0.0, 0.0, 1.0, 1.0))
        assert (cut.width, cut.height) == (1568, 1176) and cut.box == (0, 0, 8000, 6000) and cut.scale < 0.2
        corner = file_store.image_part_for_model("file_40_aa", (0.9, 0.9, 1.0, 1.0))
        assert corner.box == (7200, 5400, 8000, 6000) and (corner.width, corner.height) == (400, 300), corner.box
        with Image.open(io.BytesIO(corner.data)) as got:
            red, green, blue = got.convert("RGB").getpixel((200, 150))
            assert red > 180 and green > 170 and blue < 110, "the yellow quarter, at half the photo's size"
        quarters(8000, 6000).save(os.path.join(files_dir, "file_41_aa.png"), "PNG", compress_level=1)
        assert file_store.image_part_for_model("file_41_aa", (0.0, 0.0, 0.1, 0.1)) is None, "a PNG is decoded whole"
        assert file_store.image_part_for_model("file_99_zz", (0.0, 0.0, 0.5, 0.5)) is None
    finally:
        file_utils.FILES_DIR, file_store.db, vision_helper.get_vision_helper = saved
        service.description_cache = saved_cache


async def test_agents_hide_content():
    """The tool group auto_hide: hide_chat and the parameter hidden, only with a text of what to hide; the prompt."""
    from backend.llm.prompts import HIDE_KB_PROMPT, hide_prompt
    conversation = {"id": "conv-n", "persona_id": None}
    what = "Surprise parties and the gifts for them"
    with configured(neo4j=False, tavily=False):
        # Part of "all tools", but only with a stored conversation and a text of what to hide
        assert "auto_hide" not in OPT_IN_GROUPS
        assert "hide_chat" in default_tools(1, conversation=conversation, hide_definition=what).names()
        assert "hide_chat" not in default_tools(1, conversation=conversation).names(), "no text: nothing hidden"
        assert "hide_chat" not in default_tools(1, hide_definition=what).names(), "no conversation to hide"
        tool = tools_for_groups(["auto_hide"], user_id=1, conversation=conversation, hide_definition=what).get("hide_chat")
        assert tool.func.__wrapped__.keywords == {"conversation_id": "conv-n"}
        assert not tool.parameters["required"] and "conversation_id" not in tool.parameters["properties"]
        # The knowledge base tools get the parameter hidden only with the group and a text
        marking = tools_for_groups(["knowledge_base", "auto_hide"], user_id=1, conversation=conversation,
                                   hide_definition=what)
        plain = tools_for_groups(["knowledge_base"], user_id=1, conversation=conversation, hide_definition=what)
        untold = tools_for_groups(["knowledge_base", "auto_hide"], user_id=1, conversation=conversation)
        for name in ("kb_write", "kb_update", "memory_add", "memory_replace"):
            assert "hidden" in marking.get(name).parameters["properties"], name
            assert "hidden" not in plain.get(name).parameters["properties"], name
            assert "hidden" not in untold.get(name).parameters["properties"], name
        assert "hidden" not in marking.get("kb_archive").parameters["properties"]
        assert "hide_chat" not in untold.names()
        # The prompt: the user's text in its block, how to save it only with the knowledge base
        prompt = build_system_prompt(None, marking, what)
        assert hide_prompt(what, True) in prompt and f"<what-to-hide>\n{what}\n</what-to-hide>" in prompt
        assert HIDE_KB_PROMPT in prompt
        only_chat = build_system_prompt(None, tools_for_groups(["auto_hide"], user_id=1, conversation=conversation,
                                                               hide_definition=what), what)
        assert "## Hidden content:" in only_chat and HIDE_KB_PROMPT not in only_chat
        assert "## Hidden content:" not in build_system_prompt(None, plain, what)
        assert "## Hidden content:" not in build_system_prompt(None, marking), "no text, no section"
        # Switched off on the server: no group, no parameter
        saved = tools_module.FAMILY_MODE_ENABLED
        tools_module.FAMILY_MODE_ENABLED = False
        try:
            assert tools_module.tool_group_unavailable_reason("auto_hide") == "FAMILY_MODE_ENABLED is off"
            off = tools_for_groups(["knowledge_base", "auto_hide"], user_id=1, conversation=conversation,
                                   hide_definition=what)
            assert "hide_chat" not in off.names() and "hidden" not in off.get("kb_write").parameters["properties"]
        finally:
            tools_module.FAMILY_MODE_ENABLED = saved
    # In a hidden conversation the answer hides nothing: its agent sees all of its memory
    assert resolver.conversation_hidden({"hidden": True}) and not resolver.conversation_hidden(None)



TESTS = [test_agents_hide_content, test_groups_match_the_api_model, test_selection_filters_the_enabled_tools,
         test_knowledge_base_is_opt_in, test_web_addresses_are_opt_in, test_unavailable_groups_stay_off,
         test_prompt_only_describes_selected_tools,
         test_past_chats_need_the_knowledge_base, test_memory_follows_the_tool_sections, test_stream_generate_tools_follow_the_persona,
         test_file_tools_see_only_the_conversation, test_vision_helper_errors_are_not_cached,
         test_looking_closer_at_an_image]


async def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            await test()
            print(f"PASS  {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL  {test.__name__}")
            traceback.print_exc()
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
