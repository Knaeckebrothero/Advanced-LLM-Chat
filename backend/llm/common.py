"""
Types shared by the provider adapters and the agent loop.

The adapters (openai_chat.py, anthropic_chat.py) stream one model call as
provider-neutral events:
- ("reasoning", str): reasoning text
- ("reasoning_end", None): a reasoning block ended (Anthropic; more may follow)
- ("text", str): answer text
- ("turn", ModelTurn): the complete call, always last
"""
from dataclasses import dataclass, field
from typing import Optional

from .types import Usage

# Keys on OpenAI-format messages that only the runtime reads. The OpenAI
# adapter strips every key that starts with an underscore before sending.
ANTHROPIC_CONTENT_KEY = "_anthropic_content"   # assistant: the raw Claude content blocks (thinking with signatures)
TOOL_ERROR_KEY = "_is_error"                   # tool: the tool failed

# Why a model call stopped, normalized across providers
STOP_END = "end"
STOP_TOOL_CALLS = "tool_calls"
STOP_MAX_TOKENS = "max_tokens"
STOP_REFUSAL = "refusal"


@dataclass
class ToolCall:
    """One tool call requested by the model."""

    id: str
    name: str
    arguments: str              # the JSON text as the model wrote it


@dataclass
class ModelTurn:
    """The result of one model call."""

    text: str
    reasoning: str
    tool_calls: list[ToolCall]
    assistant_message: dict     # OpenAI-format message to append to the history
    usage: Usage = field(default_factory=Usage)
    stop_reason: Optional[str] = None   # one of the STOP_* values


class ThinkTagParser:
    """
    Split streamed content into reasoning and answer text for models that put
    their reasoning in <think>...</think> tags at the start of the content.

    Only a <think> tag before any answer text counts, so an answer that talks
    about the tag isn't cut apart. Tags split across chunks are handled.
    """

    OPEN = "<think>"
    CLOSE = "</think>"

    def __init__(self):
        self._state = "start"   # start -> think -> answer, or start -> answer
        self._buffer = ""
        self._strip_next = False

    def feed(self, text: str) -> list[tuple[str, str]]:
        """Add a chunk; returns ("reasoning" | "text", part) pairs that are ready."""
        out: list[tuple[str, str]] = []
        self._buffer += text

        if self._state == "start":
            stripped = self._buffer.lstrip()
            if stripped.startswith(self.OPEN):
                self._buffer = stripped[len(self.OPEN):]
                self._state = "think"
            elif self.OPEN.startswith(stripped):
                return out      # could still become <think>; wait for more
            else:
                self._state = "answer"

        if self._state == "think":
            index = self._buffer.find(self.CLOSE)
            if index >= 0:
                if self._buffer[:index]:
                    out.append(("reasoning", self._buffer[:index]))
                self._buffer = self._buffer[index + len(self.CLOSE):]
                self._state = "answer"
                self._strip_next = True
            else:
                keep = _partial_suffix(self._buffer, self.CLOSE)
                ready = self._buffer[:len(self._buffer) - keep]
                if ready:
                    out.append(("reasoning", ready))
                self._buffer = self._buffer[len(ready):]
                return out

        if self._state == "answer" and self._buffer:
            answer = self._buffer
            if self._strip_next:
                answer = answer.lstrip()
                if not answer:
                    self._buffer = ""
                    return out
                self._strip_next = False
            out.append(("text", answer))
            self._buffer = ""
        return out

    def flush(self) -> list[tuple[str, str]]:
        """Return whatever is still buffered at the end of the stream."""
        if not self._buffer:
            return []
        kind = "reasoning" if self._state == "think" else "text"
        rest, self._buffer = self._buffer, ""
        return [(kind, rest)]


def split_think_tags(content: str) -> tuple[str, str]:
    """Split a complete content string into (reasoning, answer)."""
    parser = ThinkTagParser()
    parts = parser.feed(content) + parser.flush()
    reasoning = "".join(part for kind, part in parts if kind == "reasoning")
    answer = "".join(part for kind, part in parts if kind == "text")
    return reasoning, answer


def _partial_suffix(text: str, tag: str) -> int:
    """Length of the longest end of text that is a start of tag (a tag split across chunks)."""
    for length in range(min(len(tag) - 1, len(text)), 0, -1):
        if text.endswith(tag[:length]):
            return length
    return 0
