"""
OpenAI-compatible Chat Completions adapter.

Every provider except Anthropic speaks this API. Reasoning arrives in one of
three places depending on the provider: a reasoning_content field (Kimi,
DeepSeek, Qwen), a reasoning field (some routers), or <think> tags at the start
of the content. The SDK keeps unknown fields in model_extra, and extra keys on
outgoing messages are sent as-is, which is how reasoning_content is passed back.
"""
import logging
import uuid
from typing import Any, AsyncIterator, Optional

from openai import AsyncOpenAI

from .common import (
    STOP_END,
    STOP_MAX_TOKENS,
    STOP_REFUSAL,
    STOP_TOOL_CALLS,
    ModelTurn,
    ThinkTagParser,
    ToolCall,
    split_think_tags,
)
from .tools import ToolRegistry
from .types import ModelConfig, Usage

log = logging.getLogger(__name__)

# Delta and message fields that carry reasoning text, in order of preference
REASONING_FIELDS = ("reasoning_content", "reasoning")

_STOP_REASONS = {
    "stop": STOP_END,
    "tool_calls": STOP_TOOL_CALLS,
    "function_call": STOP_TOOL_CALLS,
    "length": STOP_MAX_TOKENS,
    "content_filter": STOP_REFUSAL,
}


def max_tokens_param(config: ModelConfig) -> str:
    """
    Name of the output limit parameter.

    OpenAI's own API rejects max_tokens on reasoning models and wants
    max_completion_tokens; other OpenAI-compatible servers expect max_tokens.
    """
    if not config.base_url or "api.openai.com" in config.base_url:
        return "max_completion_tokens"
    return "max_tokens"


def request_options(config: ModelConfig, max_output_tokens: Optional[int] = None) -> dict:
    """Request settings from the config; only the ones that are set, plus extra_body."""
    options: dict[str, Any] = {}
    if config.temperature is not None:
        options["temperature"] = config.temperature
    if config.top_p is not None:
        options["top_p"] = config.top_p
    limit = max_output_tokens or config.max_output_tokens
    if limit:
        options[max_tokens_param(config)] = limit
    if config.reasoning_effort:
        options["reasoning_effort"] = config.reasoning_effort
    return options


def apply_extra_body(config: ModelConfig, kwargs: dict) -> dict:
    """Merge the config's extra_body into the request; its keys win over computed settings."""
    if config.extra_body:
        for key in config.extra_body:
            kwargs.pop(key, None)
        kwargs["extra_body"] = dict(config.extra_body)
    return kwargs


def prepare_messages(config: ModelConfig, messages: list[dict], system_prompt: Optional[str]) -> list[dict]:
    """
    The messages as sent: system prompt first, runtime-only keys removed, and
    reasoning_content only when the model wants it passed back.
    """
    prepared = []
    if system_prompt:
        prepared.append({"role": "system", "content": system_prompt})
    for message in messages:
        clean = {key: value for key, value in message.items() if not key.startswith("_")}
        if not config.reasoning_passback:
            clean.pop("reasoning_content", None)
        prepared.append(clean)
    return prepared


def _reasoning_of(obj: Any) -> Optional[str]:
    """Reasoning text on a delta or message, wherever the provider put it."""
    if obj is None:
        return None
    extra = getattr(obj, "model_extra", None) or {}
    for name in REASONING_FIELDS:
        value = getattr(obj, name, None)
        if value is None:
            value = extra.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def _usage_of(usage: Any) -> Usage:
    """Convert an OpenAI usage object."""
    if usage is None:
        return Usage()
    completion_details = getattr(usage, "completion_tokens_details", None)
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    return Usage(
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        reasoning_tokens=getattr(completion_details, "reasoning_tokens", None),
        cached_input_tokens=getattr(prompt_details, "cached_tokens", None),
    )


class _ToolCallAssembler:
    """Collect streamed tool-call deltas into complete calls, keyed by their index."""

    def __init__(self):
        self._slots: dict[int, dict] = {}

    def add(self, delta_call: Any) -> None:
        index = getattr(delta_call, "index", None)
        call_id = getattr(delta_call, "id", None)
        if index is None:
            # Some providers leave out the index: match by id, else start a new call or continue the last
            index = next((i for i, slot in self._slots.items() if call_id and slot["id"] == call_id), None)
            if index is None:
                index = len(self._slots) if (call_id or not self._slots) else max(self._slots)
        slot = self._slots.setdefault(index, {"id": None, "name": "", "arguments": ""})
        if call_id:
            slot["id"] = call_id
        function = getattr(delta_call, "function", None)
        if function is not None:
            name = getattr(function, "name", None)
            if name and name != slot["name"]:
                slot["name"] += name
            arguments = getattr(function, "arguments", None)
            if arguments:
                slot["arguments"] += arguments

    def calls(self) -> list[ToolCall]:
        calls = []
        for index in sorted(self._slots):
            slot = self._slots[index]
            if not slot["name"]:
                log.warning(f"Dropping a streamed tool call without a name (index {index})")
                continue
            calls.append(ToolCall(
                id=slot["id"] or f"call_{uuid.uuid4().hex[:24]}",
                name=slot["name"],
                arguments=slot["arguments"] or "{}",
            ))
        return calls


def build_assistant_message(config: ModelConfig, text: str, reasoning: str, tool_calls: list[ToolCall]) -> dict:
    """The assistant message to append to the history after a model call."""
    message: dict[str, Any] = {"role": "assistant", "content": text}
    if tool_calls:
        message["tool_calls"] = [
            {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
            for call in tool_calls
        ]
    if config.reasoning_passback and reasoning:
        message["reasoning_content"] = reasoning
    return message


async def stream_turn(
    client: AsyncOpenAI,
    config: ModelConfig,
    messages: list[dict],
    *,
    system_prompt: Optional[str],
    tools: Optional[ToolRegistry] = None,
    tool_choice: Optional[str] = None,
) -> AsyncIterator[tuple[str, Any]]:
    """
    Stream one Chat Completions call.

    Yields ("reasoning", str), ("text", str) and finally ("turn", ModelTurn).
    """
    kwargs: dict[str, Any] = {
        "model": config.model_id,
        "messages": prepare_messages(config, messages, system_prompt),
        "stream": True,
        "stream_options": {"include_usage": True},
        **request_options(config),
    }
    if tools:
        kwargs["tools"] = tools.openai_schemas()
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
    apply_extra_body(config, kwargs)

    log.debug(f"OpenAI-compatible request: model={config.model_id}, messages={len(kwargs['messages'])}, "
              f"tools={len(tools) if tools else 0}, settings={[k for k in kwargs if k not in ('model', 'messages', 'tools')]}")

    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    assembler = _ToolCallAssembler()
    think_parser = ThinkTagParser()
    usage = None
    finish_reason = None

    def route(parts: list[tuple[str, str]]):
        for kind, part in parts:
            (reasoning_parts if kind == "reasoning" else text_parts).append(part)
            yield (kind, part)

    stream = await client.chat.completions.create(**kwargs)
    async for chunk in stream:
        if getattr(chunk, "usage", None):
            usage = chunk.usage
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        delta = choice.delta
        if delta is not None:
            reasoning = _reasoning_of(delta)
            if reasoning:
                reasoning_parts.append(reasoning)
                yield ("reasoning", reasoning)
            if delta.content:
                for event in route(think_parser.feed(delta.content)):
                    yield event
            for delta_call in delta.tool_calls or []:
                assembler.add(delta_call)
        if choice.finish_reason:
            finish_reason = choice.finish_reason
    for event in route(think_parser.flush()):
        yield event

    text = "".join(text_parts)
    reasoning = "".join(reasoning_parts)
    tool_calls = assembler.calls()
    stop_reason = _STOP_REASONS.get(finish_reason, STOP_END)
    if tool_calls and stop_reason == STOP_END:
        stop_reason = STOP_TOOL_CALLS   # some providers report "stop" with tool calls

    yield ("turn", ModelTurn(
        text=text,
        reasoning=reasoning,
        tool_calls=tool_calls,
        assistant_message=build_assistant_message(config, text, reasoning, tool_calls),
        usage=_usage_of(usage),
        stop_reason=stop_reason,
    ))


async def complete_once(
    client: AsyncOpenAI,
    config: ModelConfig,
    messages: list[dict],
    *,
    system_prompt: Optional[str] = None,
    max_output_tokens: Optional[int] = None,
) -> tuple[str, Usage, str]:
    """One non-streaming call without tools; returns the answer text (reasoning removed), usage and stop reason."""
    kwargs: dict[str, Any] = {
        "model": config.model_id,
        "messages": prepare_messages(config, messages, system_prompt),
        **request_options(config, max_output_tokens),
    }
    apply_extra_body(config, kwargs)
    response = await client.chat.completions.create(**kwargs)
    content = ""
    finish_reason = None
    if response.choices:
        content = response.choices[0].message.content or ""
        finish_reason = response.choices[0].finish_reason
    _, answer = split_think_tags(content)
    return answer.strip(), _usage_of(response.usage), _STOP_REASONS.get(finish_reason, STOP_END)
