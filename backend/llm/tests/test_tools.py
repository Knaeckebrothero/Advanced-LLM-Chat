"""
Offline test of the tool groups that personas select (no API keys or database needed).

    python -m backend.llm.tests.test_tools

Covers: tools_for_groups() with no selection, an empty one and single groups,
unavailable groups (NEO4J_ENABLED off, TAVILY_API_KEY unset) and their
reasons, the opt-in knowledge base with the memory tools (only when selected,
only for signed-in users), the system prompt sections for the selected tools,
the memory in the prompt (with_memory, a fake memory store), the tools
stream-generate sends for a conversation's persona (_agent_tools, with a fake
database; the shared knowledge base, or the persona's own with own_memory), and
the file tools (fake file rows, temporary FILES_DIR): they only see the files of
the conversation and user they are built for, find a file by name or ID, give
a vision model an image itself (scaled) and a text-only model a description
(the vision helper's error is not cached as one), and show files to the user.
The knowledge base tools themselves need Postgres:
backend/services/tests/knowledge_base_test.py.
"""
import asyncio
import base64
import io
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
from backend.llm.prompts import (FILE_ACCESS_PROMPT, GRAPH_PROMPT, KB_PROMPT, MEMORY_EMPTY, MEMORY_HEADING,
                                 WEB_SEARCH_PROMPT, build_system_prompt, with_instructions, with_memory)
from backend.llm.tools import (OPT_IN_GROUPS, TOOL_GROUPS, ToolInputError, ToolText, default_tools,
                               tool_group_status, tool_message_content, tools_for_groups)
from backend.llm.types import ModelConfig
from backend.models.catalog import ToolGroup
from backend.services import file_store, file_utils
from backend.services.file_retrieval_service import get_file_retrieval_service
from backend.services.tools import web_search_tools

FILE_TOOLS = ["list_files", "read_file", "show_file"]
GRAPH_TOOLS = ["get_graph_schema", "search_graph", "query_graph"]
KB_TOOLS = ["kb_search", "kb_list", "kb_read", "kb_write", "kb_update", "kb_archive",
            "memory_add", "memory_replace", "memory_remove"]


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
    assert OPT_IN_GROUPS == {"knowledge_base", "user_mcp"} and TOOL_GROUPS["knowledge_base"] == tuple(KB_TOOLS)
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


async def test_unavailable_groups_stay_off():
    with configured(neo4j=False, tavily=False):
        assert default_tools().names() == FILE_TOOLS
        assert len(tools_for_groups(["web_search", "knowledge_graph"])) == 0
        status = {entry["id"]: entry for entry in tool_group_status()}
        assert list(status) == list(TOOL_GROUPS)
        assert status["files"] == {"id": "files", "available": True, "reason": None, "optIn": False}
        assert status["web_search"] == {"id": "web_search", "available": False,
                                        "reason": "TAVILY_API_KEY is not set", "optIn": False}
        assert status["knowledge_graph"] == {"id": "knowledge_graph", "available": False,
                                             "reason": "NEO4J_ENABLED is off", "optIn": False}
        assert status["knowledge_base"] == {"id": "knowledge_base", "available": True, "reason": None, "optIn": True}
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
    messages.kb.get_memory = lambda user_id, vault: asked.append((user_id, vault)) or {"content": f"- vault {vault}"}
    messages.persona_vault = lambda user, conversation: 8
    try:
        user = {"user_id": 1, "email": "a@example.com", "is_guest": False}
        with_kb = messages._memory_prompt("p", user, {"persona_id": 8}, tools_for_groups(["knowledge_base"], user_id=1))
        assert with_kb.endswith("<memory>\n- vault 8\n</memory>") and asked == [(1, 8)], (with_kb, asked)
        assert messages._memory_prompt("p", user, {"persona_id": 8}, tools_for_groups(["files"], user_id=1)) == "p"
        assert messages._memory_prompt("p", user, None, None) == "p" and len(asked) == 1
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
                          persona(9, ["knowledge_base"], own_memory=True, enabled=False)])
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
            # Its writes record the conversation and its agent; it is the shared knowledge base (vault 0)
            tools = messages._agent_tools(user, {"id": "conv-1", "persona_id": 6}, config)
            writer = tools.get("kb_write").func.__wrapped__.keywords["writer"]
            assert (writer.user_id, writer.conversation_id, writer.persona_id, writer.vault) == (1, "conv-1", 6, 0)
            assert tools.get("memory_add").func.__wrapped__.keywords["writer"] == writer
            assert tools.get("kb_search").func.__wrapped__.keywords == {"user_id": 1, "vault": 0}
            # An agent with its own memory reads and writes its own knowledge base (vault: its id)
            tools = messages._agent_tools(user, {"id": "conv-2", "persona_id": 8}, config)
            assert tools.get("kb_write").func.__wrapped__.keywords["writer"].vault == 8
            assert tools.get("memory_remove").func.__wrapped__.keywords["writer"].vault == 8
            assert tools.get("kb_read").func.__wrapped__.keywords == {"user_id": 1, "vault": 8}
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

        # show_file puts files into the answer: the result carries them for the chat
        shown = await mine.call("show_file", {"files": ["civitai-1.png", "nope.png", "civitai-1.png"]})
        assert shown.metadata == {"shownFiles": [{"fileId": "file_4_dd", "name": "civitai-1.png", "mimeType": "image/png",
                                                  "size": os.path.getsize(os.path.join(files_dir, "file_4_dd.png")),
                                                  "width": 3136, "height": 1568}]}, shown.metadata
        assert shown.startswith("Shown to the user above your answer: civitai-1.png.") and "Not shown: No file 'nope.png'" in shown
        # Models send a list as its JSON text, or just the one name: both are taken as the list
        for files in ("notes.txt", '["notes.txt"]'):
            one = await mine.call("show_file", {"files": files})
            assert [ref["name"] for ref in one.metadata["shownFiles"]] == ["notes.txt"], files
        try:
            await mine.call("read_file", {"file": "notes.txt", "pages": "first"})
            raise AssertionError("took a word as a list of pages")
        except ToolInputError as e:
            assert "must be of type array" in str(e), e
        assert await mine.call("read_file", {"file": "notes.txt", "pages": "[1, 2]"}) == "My notes"
        for missing in ({"files": ["other.txt"]}, {"files": []}):
            try:
                await mine.call("show_file", missing)
                raise AssertionError(f"showed {missing}")
            except ToolInputError:
                pass

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


TESTS = [test_groups_match_the_api_model, test_selection_filters_the_enabled_tools,
         test_knowledge_base_is_opt_in, test_unavailable_groups_stay_off, test_prompt_only_describes_selected_tools,
         test_memory_follows_the_tool_sections, test_stream_generate_tools_follow_the_persona,
         test_file_tools_see_only_the_conversation, test_vision_helper_errors_are_not_cached]


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
