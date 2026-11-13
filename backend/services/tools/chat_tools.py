# backend/services/tools/chat_tools.py
"""
Past chat tools for the agent: search, list and read the user's earlier conversations of its
memory (backend/services/past_chats.py, docs/past_chats.md).

The schemas the model sees are defined in backend/llm/tools.py, which binds the user and the memory
so the model can't reach other chats. The functions block on the database; the registry runs them
in a worker thread. A refused request raises ToolInputError with a message for the model. The
result of chat_read carries the conversation ({"chat": id, "chatMessage": id}), so the chat can
open it.
"""
from typing import Optional

from backend.llm.tools import ToolInputError, ToolText
from backend.services import past_chats
from backend.services.past_chats import ChatSearchError, Scope, when

MAX_SEARCH_MATCHES = 100
MAX_LIST_RESULTS = 30


def _clamp(value: Optional[int], default: int, maximum: int) -> int:
    return default if value is None else max(1, min(int(value), maximum))


def _heading(conversation: dict) -> str:
    """A conversation as a result names it: id, title, agent, dates, messages."""
    agent = f" with {conversation['agent']}" if conversation["agent"] else " (no agent)"
    first, last = when(conversation["first"]), when(conversation["last"])
    dates = first if first == last else f"{first} to {last[11:]}" if first[:10] == last[:10] else f"{first} to {last}"
    return (f"Conversation {conversation['id']}: \"{conversation['title']}\"{agent}, {dates}, "
            f"{conversation['message_count']} message(s)")


def chat_search(pattern: str, literal: Optional[bool] = None, after: Optional[str] = None,
                before: Optional[str] = None, max_matches: Optional[int] = None, *, scope: Scope) -> str:
    """Search the lines of the past chats; see past_chats.search()."""
    try:
        result = past_chats.search(scope, pattern, literal=bool(literal), after=after, before=before,
                                   limit=_clamp(max_matches, 30, MAX_SEARCH_MATCHES))
    except ChatSearchError as e:
        raise ToolInputError(str(e))
    if not result["lines"]:
        return ("No messages match. Try other words, alternatives (\"word1|word2\"), the other language, a part of "
                "a word, or no period; chat_list shows the conversations by date.")
    shown = f"{result['lines']} matching line(s)"
    if result["lines"] < result["messages"]:
        shown += (f"; {result['messages']} message(s) in {result['matching_conversations']} conversation(s) match "
                  f"in all, so make the pattern more specific or use after/before to see others")
    lines = [f"{shown}. Newest first; matching lines start with >:"]
    for conversation in result["conversations"]:
        lines += ["", _heading(conversation)]
        hits = conversation["hits"]
        for start in range(len(hits)):
            if start and hits[start - 1]["id"] == hits[start]["id"]:
                continue  # Shown with the message's first hit
            message_hits = [hit for hit in hits[start:] if hit["id"] == hits[start]["id"]]
            lines.append(f"- message {hits[start]['id']} ({hits[start]['role']}, {when(hits[start]['id'])}):")
            lines += _message_lines(message_hits)
    lines += ["", "Read the messages around a hit with chat_read(conversation, message) before relying on it."]
    return "\n".join(lines)


def _message_lines(hits: list[dict]) -> list[str]:
    """The matching lines of one message with the lines around them, merged like grep -C1: each line once."""
    entries: dict[int, tuple[str, bool]] = {}
    for hit in hits:
        entries[hit["k"]] = (hit["line"], True)
    for hit in hits:
        for k, context in ((hit["k"] - 1, hit["before"]), (hit["k"] + 1, hit["after"])):
            if context and k not in entries:
                entries[k] = (context, False)
    lines, previous = [], None
    for k in sorted(entries):
        if previous is not None and k > previous + 1:
            lines.append("    …")
        text, match = entries[k]
        lines.append(f"  > {text}" if match else f"    {text}")
        previous = k
    return lines


def chat_list(after: Optional[str] = None, before: Optional[str] = None, max_results: Optional[int] = None,
              *, scope: Scope) -> str:
    """List the past chats, most recent first; see past_chats.list_chats()."""
    try:
        result = past_chats.list_chats(scope, after=after, before=before,
                                       limit=_clamp(max_results, 10, MAX_LIST_RESULTS))
    except ChatSearchError as e:
        raise ToolInputError(str(e))
    conversations, total = result["conversations"], result["total"]
    if not total:
        return ("No conversations in this period." if after or before
                else "There are no past chats in your memory yet.")
    shown = f"the {len(conversations)} most recent" if len(conversations) < total else "most recent first"
    lines = [f"{total} conversation(s){' in this period' if after or before else ''}, {shown}:"]
    for conversation in conversations:
        lines.append(f"- {_heading(conversation)}")
        if conversation.get("summary"):
            lines.append(f"  Summary of its earlier part: {conversation['summary']}")
        elif conversation.get("opening"):
            lines.append(f"  Starts: {conversation['opening']}")
    lines.append("Read one with chat_read(conversation), or search them with chat_search.")
    return "\n".join(lines)


def chat_read(conversation: str, message: Optional[int] = None, messages_before: Optional[int] = None,
              messages_after: Optional[int] = None, *, scope: Scope) -> str:
    """Messages of a past chat; see past_chats.read_chat()."""
    try:
        result = past_chats.read_chat(scope, conversation, message=message, messages_before=messages_before,
                                      messages_after=messages_after)
    except ChatSearchError as e:
        raise ToolInputError(str(e))
    shown = result["messages"]
    end = result["position"] + len(shown) - 1
    lines = [_heading(result), f"Messages {result['position']} to {end} of {result['message_count']}:"]
    for item in shown:
        attachments = "".join(f" [Attachment: {name}]" for name in item["attachments"])
        lines += ["", f"[message {item['id']}, {item['role']}, {when(item['id'])}]{attachments}",
                  item["text"] or "(no text)"]
        if item["cut"]:
            lines.append(f"[… cut; the message has {item['length']} characters: chat_read with message={item['id']}, "
                         f"messages_before=0, messages_after=0 shows it alone, at more length]")
    more = []
    if result["earlier"]:
        more.append(f"{result['earlier']} earlier message(s): chat_read with message={shown[0]['id']}, "
                    f"messages_after=0 and messages_before up to 29")
    if result["later"]:
        more.append(f"{result['later']} later message(s): chat_read with message={shown[-1]['id']}, "
                    f"messages_before=0")
    if more:
        lines += [""] + more
    return ToolText("\n".join(lines), {"chat": result["id"], "chatMessage": (message or shown[0]["id"])})
