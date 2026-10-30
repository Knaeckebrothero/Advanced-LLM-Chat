"""
LLM runtime: clients, agent loop and tools on the official openai and anthropic SDKs.
"""
from .types import ModelConfig, Usage, model_from_env
from .agent_loop import complete, run_agent
from .client import ModelConfigError, create_client, get_client
from .prompts import build_system_prompt
from .tools import TOOL_GROUPS, Tool, ToolRegistry, default_tools, tool_group_status, tools_for_groups

__all__ = [
    "ModelConfig",
    "Usage",
    "model_from_env",
    "run_agent",
    "complete",
    "create_client",
    "get_client",
    "ModelConfigError",
    "build_system_prompt",
    "Tool",
    "ToolRegistry",
    "default_tools",
    "tools_for_groups",
    "tool_group_status",
    "TOOL_GROUPS",
]
