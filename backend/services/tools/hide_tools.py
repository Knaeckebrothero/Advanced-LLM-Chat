# backend/services/tools/hide_tools.py
"""
The tool hide_chat (the tool group auto_hide): the agent hides its conversation, so
that devices in family mode hide it, or takes its own mark back. A mark the user set stays.

backend/llm/tools.py binds the conversation, so the model can't mark another one. A changed mark
comes back with {"hiddenChat": true|false}, so the chat can tell the user at once and offer Undo.
"""
from backend.llm.tools import ToolText
from backend.services import hidden_content as hidden_content


def hide_chat(hidden: bool = True, *, conversation_id: str) -> ToolText | str:
    """Hide the conversation (or take the agent's own mark back with hidden=False)."""
    changed, message = hidden_content.mark_conversation(conversation_id, bool(hidden))
    return ToolText(message, {"hiddenChat": bool(hidden)}) if changed else message
