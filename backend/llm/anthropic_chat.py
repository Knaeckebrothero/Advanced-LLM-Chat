"""
Anthropic Messages adapter.

The rest of the runtime uses OpenAI Chat Completions messages; this module
converts them to Claude's format (system prompt, image blocks, tool_use and
tool_result blocks) and Claude's responses back.

Claude specifics, as documented for the current models:
- Thinking: when the model reasons (config.reasoning is not "none"), requests
  send adaptive thinking with display "summarized"; without it, current models
  stream thinking blocks with empty text. Thinking blocks (with their
  signatures) are passed back unchanged in tool loops: the raw content blocks
  of each response are kept on the assistant message under ANTHROPIC_CONTENT_KEY.
  Older models without adaptive thinking need reasoning "none", or a thinking
  setting in extra_body, which wins over the computed one.
- Effort: config.reasoning_effort becomes output_config.effort (low, medium,
  high, xhigh, max; OpenAI's "none" and "minimal" map to "low").
- Sampling: the API version the SDK sends rejects temperature and top_p on
  every model, so they are never sent.
- Tool choice: forced tool use is rejected by current models; only "none" is
  sent (for the final call of the agent loop), otherwise the default auto.
- max_tokens is required: the model's max_output_tokens, else a default.
"""
import json
import logging
import re
from typing import Any, AsyncIterator, Optional

from anthropic import AsyncAnthropic

from .common import (
    ANTHROPIC_CONTENT_KEY,
    STOP_END,
    STOP_MAX_TOKENS,
    STOP_REFUSAL,
    STOP_TOOL_CALLS,
    TOOL_ERROR_KEY,
    ModelTurn,
    ToolCall,
)
from .tools import ToolRegistry
from .types import ModelConfig, Usage

log = logging.getLogger(__name__)

# Output limits when the model has no max_output_tokens. Every Claude 4 model
# accepts 32K; the non-streaming default stays below the SDK's long-request guard.
DEFAULT_MAX_TOKENS_STREAMING = 32000
DEFAULT_MAX_TOKENS = 16000

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
EFFORT_ALIASES = {"none": "low", "minimal": "low"}

# Shown in place of history that starts with an assistant message (Claude needs a user message first)
HISTORY_START_PLACEHOLDER = "[Earlier messages of this conversation are not included.]"

_DATA_URL = re.compile(r"^data:(?P<media_type>[^;,]+)(?P<base64>;base64)?,(?P<data>.*)$", re.DOTALL)

_STOP_REASONS = {
    "end_turn": STOP_END,
    "stop_sequence": STOP_END,
    "pause_turn": STOP_END,
    "tool_use": STOP_TOOL_CALLS,
    "max_tokens": STOP_MAX_TOKENS,
    "model_context_window_exceeded": STOP_MAX_TOKENS,
    "refusal": STOP_REFUSAL,
}


# =========================================================================
# Request settings
# =========================================================================

def effort_of(config: ModelConfig) -> Optional[str]:
    """The output_config.effort value for the config's reasoning_effort, or None."""
    if not config.reasoning_effort:
        return None
    effort = config.reasoning_effort.strip().lower()
    if effort in EFFORT_ALIASES:
        log.debug(f"Mapping reasoning_effort '{effort}' to Claude effort '{EFFORT_ALIASES[effort]}'")
        return EFFORT_ALIASES[effort]
    if effort not in EFFORT_LEVELS:
        log.warning(f"Unknown Claude effort '{effort}' for {config.model_id}; sending it unchanged")
    return effort


def request_options(config: ModelConfig, *, streaming: bool, max_output_tokens: Optional[int] = None,
                    with_thinking: bool = True) -> dict:
    """Request settings from the config (max_tokens, thinking, effort)."""
    default_limit = DEFAULT_MAX_TOKENS_STREAMING if streaming else DEFAULT_MAX_TOKENS
    options: dict[str, Any] = {"max_tokens": max_output_tokens or config.max_output_tokens or default_limit}
    if with_thinking and config.reasoning != "none":
        options["thinking"] = {"type": "adaptive", "display": "summarized"}
    effort = effort_of(config)
    if effort:
        options["output_config"] = {"effort": effort}
    if config.temperature is not None or config.top_p is not None:
        log.debug(f"Not sending temperature/top_p to {config.model_id}: Claude rejects sampling parameters")
    return options


def apply_extra_body(config: ModelConfig, kwargs: dict) -> dict:
    """Merge the config's extra_body into the request; its keys win over computed settings."""
    if config.extra_body:
        for key in config.extra_body:
            kwargs.pop(key, None)
        kwargs["extra_body"] = dict(config.extra_body)
    return kwargs


# =========================================================================
# Message conversion (OpenAI format -> Claude)
# =========================================================================

def _text_block(text: str) -> Optional[dict]:
    """A text block, or None for empty text (Claude rejects empty text blocks)."""
    return {"type": "text", "text": text} if text and text.strip() else None


def _image_block(part: dict) -> Optional[dict]:
    """Convert an OpenAI image_url part to a Claude image block."""
    image_url = part.get("image_url") or {}
    url = image_url.get("url") if isinstance(image_url, dict) else image_url
    if not url:
        return None
    match = _DATA_URL.match(url)
    if match:
        if not match.group("base64"):
            log.warning("Skipping an image data URL that is not base64-encoded")
            return None
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": match.group("media_type"), "data": match.group("data")},
        }
    return {"type": "image", "source": {"type": "url", "url": url}}


def _user_blocks(content: Any) -> list[dict]:
    """Convert OpenAI user content (a string or a list of parts) to Claude blocks."""
    if content is None:
        return []
    if isinstance(content, str):
        block = _text_block(content)
        return [block] if block else []
    blocks = []
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            block = _text_block(part.get("text", ""))
        elif part.get("type") == "image_url":
            block = _image_block(part)
        else:
            log.warning(f"Skipping unsupported content part for Claude: {part.get('type')}")
            block = None
        if block:
            blocks.append(block)
    return blocks


def _assistant_blocks(message: dict) -> list[dict]:
    """Claude blocks of an assistant message: the original response blocks if kept, else rebuilt."""
    original = message.get(ANTHROPIC_CONTENT_KEY)
    if original:
        return list(original)
    blocks = []
    content = message.get("content")
    if isinstance(content, str):
        block = _text_block(content)
        if block:
            blocks.append(block)
    elif isinstance(content, list):
        blocks.extend(block for block in _user_blocks(content) if block["type"] == "text")
    for call in message.get("tool_calls") or []:
        function = call.get("function", {})
        blocks.append({
            "type": "tool_use",
            "id": call.get("id"),
            "name": function.get("name"),
            "input": _parse_arguments(function.get("arguments")),
        })
    return blocks


def _parse_arguments(arguments: Any) -> dict:
    """Tool-call arguments as a dict (Claude's tool_use input)."""
    if isinstance(arguments, dict):
        return arguments
    if not arguments:
        return {}
    try:
        parsed = json.loads(arguments)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except (TypeError, ValueError):
        return {"raw": str(arguments)}


def _tool_result_block(message: dict) -> dict:
    """Convert an OpenAI tool message to a Claude tool_result block."""
    content = message.get("content")
    if isinstance(content, list):
        content = _user_blocks(content)
    elif not content:
        content = "(empty result)"
    block = {"type": "tool_result", "tool_use_id": message.get("tool_call_id"), "content": content}
    if message.get(TOOL_ERROR_KEY):
        block["is_error"] = True
    return block


def to_anthropic_messages(messages: list[dict], system_prompt: Optional[str] = None) -> tuple[Optional[str], list[dict]]:
    """
    Convert OpenAI-format messages to Claude's system prompt and messages.

    System messages are joined into the system prompt, tool results become
    tool_result blocks in a user message, and consecutive messages of the same
    role are merged so every tool result of a call ends up in one user message.
    """
    system_parts = [system_prompt] if system_prompt else []
    converted: list[dict] = []

    for message in messages:
        role = message.get("role")
        if role == "system":
            content = message.get("content")
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            if content:
                system_parts.append(content)
            continue
        if role == "assistant":
            claude_role, blocks = "assistant", _assistant_blocks(message)
        elif role == "tool":
            claude_role, blocks = "user", [_tool_result_block(message)]
        else:
            claude_role, blocks = "user", _user_blocks(message.get("content"))
        if not blocks:
            continue
        if converted and converted[-1]["role"] == claude_role:
            converted[-1]["content"].extend(blocks)
        else:
            converted.append({"role": claude_role, "content": blocks})

    if converted and converted[0]["role"] == "assistant":
        converted.insert(0, {"role": "user", "content": [{"type": "text", "text": HISTORY_START_PLACEHOLDER}]})

    system = "\n\n".join(system_parts) if system_parts else None
    return system, converted


# =========================================================================
# Response conversion (Claude -> OpenAI format)
# =========================================================================

def _block_param(block: Any) -> Optional[dict]:
    """A response content block as a request block, to send it back unchanged."""
    block_type = getattr(block, "type", None)
    if block_type == "text":
        return _text_block(block.text)
    if block_type == "thinking":
        return {"type": "thinking", "thinking": block.thinking, "signature": block.signature}
    if block_type == "redacted_thinking":
        return {"type": "redacted_thinking", "data": block.data}
    if block_type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return block.to_dict() if hasattr(block, "to_dict") else None


def _usage_of(usage: Any) -> Usage:
    """Convert Claude's usage; input_tokens there excludes cache reads and writes, so add them."""
    if usage is None:
        return Usage()
    cache_read = getattr(usage, "cache_read_input_tokens", None) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", None) or 0
    details = getattr(usage, "output_tokens_details", None)
    return Usage(
        input_tokens=(usage.input_tokens or 0) + cache_read + cache_write,
        output_tokens=usage.output_tokens or 0,
        reasoning_tokens=getattr(details, "thinking_tokens", None),
        cached_input_tokens=cache_read or None,
    )


def turn_from_message(message: Any) -> ModelTurn:
    """Build the provider-neutral turn from a complete Claude message."""
    text = "".join(block.text for block in message.content if block.type == "text")
    reasoning = "".join(block.thinking or "" for block in message.content if block.type == "thinking")
    tool_calls = [
        ToolCall(id=block.id, name=block.name, arguments=_dump_input(block.input))
        for block in message.content if block.type == "tool_use"
    ]
    raw_blocks = [param for param in (_block_param(block) for block in message.content) if param]

    assistant_message: dict[str, Any] = {"role": "assistant", "content": text, ANTHROPIC_CONTENT_KEY: raw_blocks}
    if tool_calls:
        assistant_message["tool_calls"] = [
            {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
            for call in tool_calls
        ]

    stop_reason = _STOP_REASONS.get(message.stop_reason, STOP_END)
    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        log.warning(f"Claude declined the request (category: {getattr(details, 'category', None)})")
    return ModelTurn(
        text=text,
        reasoning=reasoning,
        tool_calls=tool_calls,
        assistant_message=assistant_message,
        usage=_usage_of(message.usage),
        stop_reason=stop_reason,
    )


def _dump_input(value: Any) -> str:
    """Claude's tool input as the JSON text of an OpenAI tool call."""
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


# =========================================================================
# Calls
# =========================================================================

async def stream_turn(
    client: AsyncAnthropic,
    config: ModelConfig,
    messages: list[dict],
    *,
    system_prompt: Optional[str],
    tools: Optional[ToolRegistry] = None,
    tool_choice: Optional[str] = None,
) -> AsyncIterator[tuple[str, Any]]:
    """
    Stream one Messages call.

    Yields ("reasoning", str), ("reasoning_end", None), ("text", str) and finally ("turn", ModelTurn).
    """
    system, claude_messages = to_anthropic_messages(messages, system_prompt)
    kwargs: dict[str, Any] = {
        "model": config.model_id,
        "messages": claude_messages,
        # Caches the longest stable prefix (system, tools, history) across the calls of a tool loop
        "cache_control": {"type": "ephemeral"},
        **request_options(config, streaming=True),
    }
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = tools.anthropic_schemas()
        if tool_choice == "none":
            kwargs["tool_choice"] = {"type": "none"}
    apply_extra_body(config, kwargs)

    log.debug(f"Anthropic request: model={config.model_id}, messages={len(claude_messages)}, "
              f"tools={len(tools) if tools else 0}, settings={[k for k in kwargs if k not in ('model', 'messages', 'tools', 'system')]}")

    block_types: dict[int, str] = {}
    async with client.messages.stream(**kwargs) as stream:
        async for event in stream:
            if event.type == "content_block_start":
                block_types[event.index] = event.content_block.type
            elif event.type == "content_block_delta":
                delta = event.delta
                if delta.type == "thinking_delta" and delta.thinking:
                    yield ("reasoning", delta.thinking)
                elif delta.type == "text_delta" and delta.text:
                    yield ("text", delta.text)
            elif event.type == "content_block_stop":
                if block_types.get(event.index) == "thinking":
                    yield ("reasoning_end", None)
        message = await stream.get_final_message()

    yield ("turn", turn_from_message(message))


async def complete_once(
    client: AsyncAnthropic,
    config: ModelConfig,
    messages: list[dict],
    *,
    system_prompt: Optional[str] = None,
    max_output_tokens: Optional[int] = None,
) -> tuple[str, Usage]:
    """One non-streaming call without tools; thinking is left at the model's default."""
    system, claude_messages = to_anthropic_messages(messages, system_prompt)
    kwargs: dict[str, Any] = {
        "model": config.model_id,
        "messages": claude_messages,
        **request_options(config, streaming=False, max_output_tokens=max_output_tokens, with_thinking=False),
    }
    if system:
        kwargs["system"] = system
    apply_extra_body(config, kwargs)
    message = await client.messages.create(**kwargs)
    turn = turn_from_message(message)
    return turn.text.strip(), turn.usage
