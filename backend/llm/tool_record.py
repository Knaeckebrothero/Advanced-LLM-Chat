"""
The tool record of an answer: what the model and its tools exchanged while the answer was written.

The agent loop's additions to the history (the model's tool calls, their results, the text
between them) are kept with the stored answer, and later answers get them back as real tool
calls and results, not only the answer's text. Without them a model can't tell what it did in
earlier turns: asked "did you really look at the image?", it finds no tool call in its history
and says it never looked (seen with Kimi K3, 2026-11-12).

A record is a list of messages in the OpenAI format, as run_agent() had them, except:
- only complete rounds: a call without its results (the run broke off there) is left out
- Claude's raw content blocks are dropped: thinking is only passed back within one answer
- the images of a tool result become a note (images_note()); they are not sent again in later turns
- it ends with the answer's last text as an assistant message, if there is any

An answer that called no tool has no record: its text is all there is.
"""
from .common import TOOL_ERROR_KEY

def images_note(count: int) -> str:
    """Stands in for the images of a tool result (e.g. read_file on an image, for a vision model)."""
    if count == 1:
        return ("[This result came with the image itself: you saw it when this tool ran. It is not sent "
                "again in later turns; call the tool again to look at it once more.]")
    return (f"[This result came with {count} images: you saw them when this tool ran. They are not sent "
            "again in later turns; call the tool again to look at them once more.]")


def _stored(message: dict) -> dict:
    """A message as kept in a record: without runtime-only keys, images replaced by the note."""
    kept = {key: value for key, value in message.items() if not key.startswith("_") or key == TOOL_ERROR_KEY}
    content = kept.get("content")
    if message.get("role") == "tool" and isinstance(content, list):
        parts = [part for part in content if isinstance(part, dict)]
        texts = [part.get("text", "") for part in parts if part.get("type") == "text"]
        images = sum(1 for part in parts if part.get("type") != "text")
        if images:
            texts.append(images_note(images))
        kept["content"] = "\n\n".join(text for text in texts if text)
    return kept


def record(messages: list[dict], final_text: str = "") -> list[dict]:
    """
    The tool record of an answer.

    Args:
        messages: What the agent loop added to the history for this answer, in order.
        final_text: The text of the model call that ended the answer.

    Returns:
        The record, or [] when no tool call was completed.
    """
    kept: list[dict] = []
    called = False
    index = 0
    while index < len(messages):
        message = messages[index]
        role = message.get("role")
        calls = message.get("tool_calls") if role == "assistant" else None
        if calls:
            ids = [call.get("id") for call in calls]
            results = messages[index + 1:index + 1 + len(ids)]
            if [result.get("tool_call_id") for result in results if result.get("role") == "tool"] != ids:
                break  # The run broke off before the results of these calls
            kept.append(_stored(message))
            kept.extend(_stored(result) for result in results)
            called = True
            index += 1 + len(ids)
        elif role == "tool":
            break  # A result without its call
        else:
            kept.append(_stored(message))  # The note before the last allowed model call
            index += 1
    if not called:
        return []
    if final_text and final_text.strip():
        kept.append({"role": "assistant", "content": final_text})
    return kept


def with_text(tool_record: list[dict], text: str) -> list[dict]:
    """
    A record after the answer's text was edited: the calls and their results stay, and the
    new text is the answer's only text (the text between the calls was part of the old one).
    """
    kept = []
    for message in tool_record:
        if message.get("role") == "assistant":
            if not message.get("tool_calls"):
                continue  # The old last text
            message = {**message, "content": ""}
        kept.append(message)
    if text and text.strip():
        kept.append({"role": "assistant", "content": text})
    return kept
