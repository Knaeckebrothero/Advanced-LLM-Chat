"""
Offline test of the tool groups that personas select (no API keys or database needed).

    python -m backend.llm.tests.test_tools

Covers: tools_for_groups() with no selection, an empty one and single groups,
unavailable groups (NEO4J_ENABLED off, TAVILY_API_KEY unset) and their
reasons, the system prompt sections for the selected tools, and the tools
stream-generate sends for a conversation's persona (_agent_tools, with a fake
database).
"""
import asyncio
import sys
import traceback
from contextlib import contextmanager
from dataclasses import replace
from typing import get_args

from backend.api import messages
from backend.catalog import resolver
from backend.llm import tools as tools_module
from backend.llm.prompts import FILE_ACCESS_PROMPT, GRAPH_PROMPT, WEB_SEARCH_PROMPT, build_system_prompt
from backend.llm.tools import TOOL_GROUPS, default_tools, tool_group_status, tools_for_groups
from backend.llm.types import ModelConfig
from backend.models.catalog import ToolGroup
from backend.services.tools import web_search_tools

GRAPH_TOOLS = ["get_graph_schema", "search_graph", "query_graph"]


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
        assert sorted(everything) == sorted(["get_file_content", "web_search", *GRAPH_TOOLS]), everything
        assert tools_for_groups(None).names() == everything
        assert len(tools_for_groups([])) == 0
        assert tools_for_groups(["files"]).names() == ["get_file_content"]
        assert tools_for_groups(["web_search"]).names() == ["web_search"]
        assert tools_for_groups(["knowledge_graph"]).names() == GRAPH_TOOLS
        assert sorted(tools_for_groups(["files", "knowledge_graph", "nonsense"]).names()) == \
            sorted(["get_file_content", *GRAPH_TOOLS])


async def test_unavailable_groups_stay_off():
    with configured(neo4j=False, tavily=False):
        assert default_tools().names() == ["get_file_content"]
        assert len(tools_for_groups(["web_search", "knowledge_graph"])) == 0
        status = {entry["id"]: entry for entry in tool_group_status()}
        assert list(status) == list(TOOL_GROUPS)
        assert status["files"] == {"id": "files", "available": True, "reason": None}
        assert status["web_search"] == {"id": "web_search", "available": False,
                                        "reason": "TAVILY_API_KEY is not set"}
        assert status["knowledge_graph"] == {"id": "knowledge_graph", "available": False,
                                             "reason": "NEO4J_ENABLED is off"}
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
        assert build_system_prompt("You translate.", None) == "You translate."


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
                          persona(4, [], enabled=False)])
    try:
        with configured(neo4j=True, tavily=True):
            def names(user, persona_id, config=config):
                tools = messages._agent_tools(user, {"persona_id": persona_id}, config)
                return None if tools is None else sorted(tools.names())

            everything = sorted(default_tools().names())
            assert names(user, 1) is None, "tools [] -> no tools at all"
            assert names(user, 2) == ["get_file_content"]
            assert names(user, 3) == everything, "tools null -> every enabled tool"
            assert names(user, None) == everything, "no persona -> every enabled tool"
            assert names(user, 4) == everything, "disabled persona is skipped"
            assert names(guest, 1) == everything, "persona not available to guests is skipped"
            assert names(user, 2, replace(config, supports_tools=False)) is None
        with configured(neo4j=False, tavily=False):
            # Only unavailable groups selected: no tools, not an empty tool list
            resolver.db = FakeDB([persona(5, ["web_search"])])
            assert messages._agent_tools(user, {"persona_id": 5}, config) is None
    finally:
        resolver.db = saved_db


TESTS = [test_groups_match_the_api_model, test_selection_filters_the_enabled_tools,
         test_unavailable_groups_stay_off, test_prompt_only_describes_selected_tools,
         test_stream_generate_tools_follow_the_persona]


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
