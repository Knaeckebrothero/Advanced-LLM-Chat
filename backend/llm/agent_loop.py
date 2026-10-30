"""
The agent loop: stream a completion, run the requested tools, repeat.

run_agent() streams one answer as events for the SSE endpoint:
- ("step", AgentStep): a new step, or a replacement for a step with the same id
- ("step_delta", {"id": str, "delta": str}): text appended to an earlier step (live reasoning)
- ("token", str): text of the answer
- ("usage", Usage): exactly once, last, summed over all model calls

Reasoning becomes a "Thinking" step: sent once empty when it starts, grown
through step_delta events, and sent again complete (same id) when it ends.
Tool calls become a tool_call and a tool_result step, linked by the model's
tool call id in their callId.

complete() is one call without tools or streaming, for titles, speech
preprocessing and the non-streaming endpoints.
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator, Optional

from ..config import AGENT_MAX_STEPS
from ..models.message import AgentStep
from . import anthropic_chat, openai_chat
from .client import get_client
from .common import STOP_MAX_TOKENS, STOP_REFUSAL, TOOL_ERROR_KEY, ModelTurn, ToolCall
from .tools import ToolInputError, ToolRegistry, format_tool_output
from .types import KIND_ANTHROPIC, ModelConfig, Usage

log = logging.getLogger(__name__)

THINKING_TITLE = "Thinking"

# Longest step content shown for a tool result
MAX_RESULT_STEP_LENGTH = 1000

# Added before the last allowed model call when the model still wants tools
STEP_LIMIT_NOTE = (
    "[The limit of tool calls for this answer has been reached. Answer now with the information "
    "you have, without calling any more tools.]"
)
TRUNCATED_NOTE = "\n\n[The answer was cut off at the output token limit.]"
REFUSAL_NOTE = "[The model declined to answer this request.]"


class LoopStep(AgentStep):
    """
    An AgentStep with the model's tool call id, which links a tool_call step to its
    tool_result step. None for other steps.
    """
    callId: Optional[str] = None


def _now_ms() -> int:
    return int(time.time() * 1000)


class _ReasoningStep:
    """A Thinking step that grows while the model reasons."""

    def __init__(self):
        self.id = str(uuid.uuid4())
        self.started = _now_ms()
        self.parts: list[str] = []

    def start(self) -> LoopStep:
        return LoopStep(id=self.id, type="thought", title=THINKING_TITLE, content="", timestamp=self.started)

    def finish(self) -> LoopStep:
        return LoopStep(
            id=self.id,
            type="thought",
            title=THINKING_TITLE,
            content="".join(self.parts),
            timestamp=self.started,
            duration=_now_ms() - self.started,
        )


def _stream_turn(client: Any, config: ModelConfig, messages: list[dict], **kwargs) -> AsyncIterator[tuple[str, Any]]:
    """Stream one model call with the adapter for the config's provider kind."""
    adapter = anthropic_chat if config.kind == KIND_ANTHROPIC else openai_chat
    return adapter.stream_turn(client, config, messages, **kwargs)


def _parse_arguments(call: ToolCall) -> tuple[Any, Optional[str]]:
    """The call's arguments as JSON, or an error message when they don't parse."""
    try:
        return json.loads(call.arguments or "{}"), None
    except (TypeError, ValueError) as e:
        return None, f"The arguments are not valid JSON ({e}): {call.arguments}"


def _json_safe(value: Any) -> Any:
    """A copy of a tool output that json.dumps can always serialize (for step metadata)."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


async def _run_tool(registry: ToolRegistry, call: ToolCall, arguments: Any, error: Optional[str]) -> tuple[Any, bool, int]:
    """Run one tool call; errors become the result so the model can react. Returns (output, is_error, ms)."""
    started = time.monotonic()
    if error is None:
        try:
            output = await registry.call(call.name, arguments)
            return output, False, int((time.monotonic() - started) * 1000)
        except ToolInputError as e:
            error = str(e)
        except Exception as e:
            log.error(f"Tool {call.name} failed: {e}", exc_info=True)
            error = f"{type(e).__name__}: {e}"
    log.warning(f"Tool call {call.name} ({call.id}) returned an error: {error}")
    return f"Error: {error}", True, int((time.monotonic() - started) * 1000)


async def _run_tools(
    registry: ToolRegistry,
    calls: list[ToolCall],
    history: list[dict],
) -> AsyncIterator[tuple[str, Any]]:
    """
    Announce the tool calls, run them concurrently, and append their results to
    the history in the order the model requested them.
    """
    parsed = [_parse_arguments(call) for call in calls]
    for call, (arguments, error) in zip(calls, parsed):
        content = json.dumps(arguments, indent=2, ensure_ascii=False) if error is None else call.arguments
        yield ("step", LoopStep(
            id=str(uuid.uuid4()),
            type="tool_call",
            title=registry.title(call.name),
            content=content,
            timestamp=_now_ms(),
            callId=call.id,
        ))

    async def run(index: int):
        arguments, error = parsed[index]
        return index, await _run_tool(registry, calls[index], arguments, error)

    results: list[Optional[tuple[Any, bool]]] = [None] * len(calls)
    tasks = [asyncio.create_task(run(index)) for index in range(len(calls))]
    try:
        for next_done in asyncio.as_completed(tasks):
            index, (output, is_error, duration) = await next_done
            results[index] = (output, is_error)
            call = calls[index]
            if isinstance(output, (dict, list)):
                content = json.dumps(output, indent=2, ensure_ascii=False, default=str)
            else:
                content = str(output)
            if len(content) > MAX_RESULT_STEP_LENGTH:
                content = content[:MAX_RESULT_STEP_LENGTH] + "..."
            yield ("step", LoopStep(
                id=str(uuid.uuid4()),
                type="tool_result",
                title=f"Result: {registry.title(call.name)}",
                content=content,
                timestamp=_now_ms(),
                duration=duration,
                metadata=_json_safe(output) if isinstance(output, dict) else None,
                callId=call.id,
            ))
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

    for call, (output, is_error) in zip(calls, results):
        message = {"role": "tool", "tool_call_id": call.id, "content": format_tool_output(output)}
        if is_error:
            message[TOOL_ERROR_KEY] = True
        history.append(message)


async def run_agent(
    config: ModelConfig,
    messages: list[dict],
    *,
    system_prompt: str,
    tools: Optional[ToolRegistry] = None,
    max_steps: int = AGENT_MAX_STEPS,
    client: Any = None,
) -> AsyncIterator[tuple[str, Any]]:
    """
    Stream an answer with tool use.

    Args:
        config: The model to call.
        messages: The conversation in the OpenAI Chat Completions format (not modified).
        system_prompt: The system prompt (see build_system_prompt).
        tools: The tools the model may call; only sent when config.supports_tools is set.
        max_steps: Maximum number of model calls. The last one is made without
            tools, so the model answers with what it has.
        client: An SDK client to use instead of the shared one (tests, smoke test).

    Yields:
        ("step", AgentStep), ("step_delta", dict), ("token", str), and ("usage", Usage)
        exactly once at the end. If a model call fails, the usage so far is yielded
        and then the exception propagates.
    """
    client = client or get_client(config)
    registry = tools if tools and config.supports_tools else None
    if tools and not config.supports_tools:
        log.info(f"{config.display_name} does not support tools; answering without them")
    max_steps = max(1, max_steps)

    history = list(messages)
    total = Usage()
    answered = False            # any answer text streamed yet
    separate_next_text = False  # put a blank line before the next answer text (text before and after tools)

    log.info(f"Agent run: model={config.model_id} ({config.provider_name}), messages={len(history)}, "
             f"tools={registry.names() if registry else []}, max_steps={max_steps}")

    try:
        for step_index in range(max_steps):
            last_call = step_index == max_steps - 1
            if last_call and registry and step_index > 0:
                log.info(f"Agent reached the step limit ({max_steps}); final call without tools")
                history.append({"role": "user", "content": STEP_LIMIT_NOTE})

            reasoning: Optional[_ReasoningStep] = None
            turn: Optional[ModelTurn] = None
            async for kind, data in _stream_turn(
                client, config, history,
                system_prompt=system_prompt,
                tools=registry,
                tool_choice="none" if (last_call and registry) else None,
            ):
                if kind == "reasoning":
                    if reasoning is None:
                        reasoning = _ReasoningStep()
                        yield ("step", reasoning.start())
                    reasoning.parts.append(data)
                    yield ("step_delta", {"id": reasoning.id, "delta": data})
                elif kind == "text":
                    if reasoning is not None:
                        yield ("step", reasoning.finish())
                        reasoning = None
                    if separate_next_text:
                        yield ("token", "\n\n")
                        separate_next_text = False
                    answered = True
                    yield ("token", data)
                elif kind == "reasoning_end":
                    if reasoning is not None:
                        yield ("step", reasoning.finish())
                        reasoning = None
                elif kind == "turn":
                    turn = data
            if reasoning is not None:
                yield ("step", reasoning.finish())

            if turn is None:
                raise RuntimeError("The model stream ended without a response")
            total.add(turn.usage)
            log.debug(f"Model call {step_index + 1}: stop={turn.stop_reason}, tool_calls={len(turn.tool_calls)}, "
                      f"text={len(turn.text)} chars, reasoning={len(turn.reasoning)} chars")

            if turn.stop_reason == STOP_REFUSAL:
                if not answered:
                    yield ("token", REFUSAL_NOTE)
                break
            if turn.stop_reason == STOP_MAX_TOKENS:
                # A tool call cut off at the limit has incomplete arguments; don't run it
                log.warning(f"{config.model_id} hit the output token limit")
                yield ("token", TRUNCATED_NOTE)
                break
            if not turn.tool_calls or registry is None:
                break
            if last_call:
                log.warning(f"{config.model_id} requested tools on the final call; ignoring them")
                break

            history.append(turn.assistant_message)
            async for event in _run_tools(registry, turn.tool_calls, history):
                yield event
            separate_next_text = answered
    except Exception:
        yield ("usage", total)
        raise

    log.info(f"Agent run finished: input={total.input_tokens}, output={total.output_tokens} tokens")
    yield ("usage", total)


async def complete(
    config: ModelConfig,
    messages: list[dict],
    *,
    system_prompt: Optional[str] = None,
    max_output_tokens: Optional[int] = None,
    client: Any = None,
) -> tuple[str, Usage]:
    """
    One model call without tools or streaming.

    Args:
        config: The model to call.
        messages: The conversation in the OpenAI Chat Completions format.
        system_prompt: Optional system prompt.
        max_output_tokens: Output limit for this call; defaults to the model's.
            Keep it generous for thinking models, whose reasoning counts toward it.
        client: An SDK client to use instead of the shared one.

    Returns:
        The answer text (reasoning removed) and the usage.
    """
    client = client or get_client(config)
    adapter = anthropic_chat if config.kind == KIND_ANTHROPIC else openai_chat
    text, usage = await adapter.complete_once(
        client, config, messages, system_prompt=system_prompt, max_output_tokens=max_output_tokens
    )
    log.debug(f"Completion from {config.model_id}: {len(text)} chars, input={usage.input_tokens}, "
              f"output={usage.output_tokens} tokens")
    return text, usage
