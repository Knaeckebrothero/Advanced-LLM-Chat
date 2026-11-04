# backend/services/tools/kb_tools.py
"""
Knowledge base tools for the agent: search, list, read, write, update and archive the notes of the
user it answers for, and add, replace and remove lines of the memory (backend/services/knowledge_base.py,
docs/knowledge_base.md).

The schemas the model sees are defined in backend/llm/tools.py, which binds the user and vault (and,
for writes, the conversation and its agent) so the model can't choose another knowledge base. The
functions block on the database; the registry runs them in a worker thread. A refused request
raises ToolInputError with a message for the model, so the step shows as failed and nothing claims
a write that didn't happen. The results of kb_read, kb_write, kb_update, kb_archive and the memory
tools carry the note's slug ({"kbNote": slug}, and {"kbVault": vault} for an agent's own knowledge
base), so the chat can open the note on the Knowledge base page.
"""
import logging
from datetime import datetime
from typing import List, Optional

from backend.llm.tools import ToolInputError, ToolText
from backend.services import knowledge_base as kb
from backend.services.knowledge_base import KBError, Writer

log = logging.getLogger(__name__)

MAX_SEARCH_RESULTS = 25
MAX_LIST_RESULTS = 200


def _date(value: Optional[datetime]) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "?"


def _tags(tags: List[str]) -> str:
    return ", ".join(tags) if tags else "none"


def _refused(error: KBError) -> ToolInputError:
    return ToolInputError(str(error))


def _about(note: dict, text: str, vault: int = 0) -> ToolText:
    """A result about one note: its step in the chat links to the note."""
    return ToolText(text, {"kbNote": note["slug"], **({"kbVault": vault} if vault else {})})


def _clamp(value: Optional[int], default: int, maximum: int) -> int:
    return default if value is None else max(1, min(int(value), maximum))


def kb_search(query: Optional[str] = None, exact: Optional[List[str]] = None, tags: Optional[List[str]] = None,
              max_results: Optional[int] = None, *, user_id: int, vault: int = 0) -> str:
    """Search the active notes; see knowledge_base.search_notes()."""
    try:
        hits = kb.search_notes(user_id, query=query, exact=exact, tags=tags,
                               limit=_clamp(max_results, 10, MAX_SEARCH_RESULTS), vault=vault)
    except KBError as e:
        raise _refused(e)
    if not hits:
        return "No notes found. Try other words, an exact text or kb_list for an overview."
    lines = [f"{len(hits)} note(s) found, best first:"]
    for i, hit in enumerate(hits, 1):
        lines.append(f"{i}. **{hit['slug']}**: {hit['title']} [matched: {'+'.join(hit['matched'])}] "
                     f"(tags: {_tags(hit['tags'])}; updated {_date(hit['updated_at'])})")
        if hit["description"]:
            lines.append(f"   {hit['description']}")
        lines.append(f"   > {hit['snippet']}")
    lines.append("Read a note in full with kb_read.")
    return "\n".join(lines)


def kb_list(tag: Optional[str] = None, max_results: Optional[int] = None, *, user_id: int, vault: int = 0) -> str:
    """List the active notes, newest first, and the tags in use."""
    try:
        result = kb.list_notes(user_id, tag=tag, limit=_clamp(max_results, 50, MAX_LIST_RESULTS), vault=vault)
    except KBError as e:
        raise _refused(e)
    notes, total = result["notes"], result["total"]
    if total == 0:
        return (f"No notes with the tag '{tag}'." if tag
                else "The knowledge base is empty. Create the first note with kb_write.")
    shown = f"the {len(notes)} most recently updated" if len(notes) < total else "most recently updated first"
    lines = [f"{total} note(s){f' with the tag {tag!r}' if tag else ''}, {shown}:"]
    for note in notes:
        description = f": {note['description']}" if note["description"] else ""
        lines.append(f"- **{note['slug']}**: {note['title']}{description} "
                     f"(tags: {_tags(note['tags'])}; updated {_date(note['updated_at'])})")
    if result["tags"]:
        lines.append("Tags in use: " + ", ".join(f"{name} ({count})" for name, count in result["tags"]))
    return "\n".join(lines)


def kb_read(note: str, *, user_id: int, vault: int = 0) -> str:
    """A note in full, with the notes it links to and the notes that link to it."""
    try:
        found = kb.get_note(user_id, note, vault=vault)
    except KBError as e:
        raise _refused(e)
    lines = [f"# {found['title']}",
             f"slug: {found['slug']} | tags: {_tags(found['tags'])} | updated {_date(found['updated_at'])}, "
             f"created {_date(found['created_at'])}"]
    if found["status"] == "archived":
        lines.append("Archived: it doesn't show up in kb_list or kb_search; kb_update restores it.")
    if found["description"]:
        lines.append(f"Description: {found['description']}")
    lines += ["", found["content"], ""]
    if found["links"]:
        links = []
        for link in found["links"]:
            if link["title"] is None:
                links.append(f"[[{link['slug']}]] (no such note yet)")
            else:
                archived = " (archived)" if link["status"] == "archived" else ""
                links.append(f"[[{link['slug']}]] {link['title']}{archived}")
        lines.append("Links to: " + "; ".join(links))
    if found["backlinks"]:
        lines.append("Linked from: " + "; ".join(f"[[{link['slug']}]] {link['title']}" for link in found["backlinks"]))
    return _about(found, "\n".join(lines).rstrip(), vault)


def _length_hint(content: str) -> str:
    if len(content) > kb.LONG_NOTE_CHARS:
        return (f" The note is long ({len(content)} characters); consider splitting it into notes on single "
                f"topics that link to each other.")
    return ""


def kb_write(title: str, content: str, description: Optional[str] = None, tags: Optional[List[str]] = None,
             *, writer: Writer) -> str:
    """Create a note."""
    try:
        note = kb.create_note(writer, title, content, description=description, tags=tags)
    except KBError as e:
        raise _refused(e)
    return _about(note, f"Created note **{note['slug']}** (\"{note['title']}\", tags: {_tags(note['tags'])}). "
                        f"Link to it with [[{note['slug']}]].{_length_hint(note['content'])} If it matters beyond "
                        f"this conversation, give it a short line in the memory that points to it: "
                        f"memory_add(\"<what it is about> → [[{note['slug']}]]\").", writer.vault)


def kb_update(note: str, content: Optional[str] = None, append: Optional[str] = None, title: Optional[str] = None,
              description: Optional[str] = None, tags: Optional[List[str]] = None, *, writer: Writer) -> str:
    """Change a note."""
    try:
        updated, changes = kb.update_note(writer, note, content=content, append=append, title=title,
                                          description=description, tags=tags)
    except KBError as e:
        raise _refused(e)
    if not changes:
        return _about(updated, f"Note **{updated['slug']}** already has these values; nothing was changed.",
                      writer.vault)
    return _about(updated, f"Updated note **{updated['slug']}**: {', '.join(changes)}.{_length_hint(updated['content'])}",
                  writer.vault)


def kb_archive(note: str, reason: Optional[str] = None, *, writer: Writer) -> str:
    """Archive a note."""
    try:
        archived, changed = kb.archive_note(writer, note, reason=reason)
    except KBError as e:
        raise _refused(e)
    if not changed:
        return _about(archived, f"Note **{archived['slug']}** was archived already.", writer.vault)
    return _about(archived, f"Archived note **{archived['slug']}**. It no longer shows up in kb_list or kb_search; "
                            f"kb_read still shows it and kb_update restores it. If a line of the memory points "
                            f"to it, change or remove that line.", writer.vault)


def memory_add(text: str, section: Optional[str] = None, *, writer: Writer) -> str:
    """Add a line to the memory."""
    try:
        memory, changed = kb.memory_add(writer, text, section=section)
    except KBError as e:
        raise _refused(e)
    if not changed:
        return _about(memory, "The memory has this line already; nothing was changed.", writer.vault)
    where = f" under \"{' '.join(section.split()).lstrip('#').strip()}\"" if section and section.strip() else ""
    return _about(memory, f"Added the line{where}. {kb.memory_status(memory['content'])}", writer.vault)


def memory_replace(line: str, text: str, *, writer: Writer) -> str:
    """Replace a line of the memory."""
    try:
        memory = kb.memory_replace(writer, line, text)
    except KBError as e:
        raise _refused(e)
    return _about(memory, f"Replaced the line. {kb.memory_status(memory['content'])}", writer.vault)


def memory_remove(line: str, *, writer: Writer) -> str:
    """Remove a line of the memory."""
    try:
        memory, removed = kb.memory_remove(writer, line)
    except KBError as e:
        raise _refused(e)
    return _about(memory, f"Removed the line \"{removed}\". {kb.memory_status(memory['content'])}", writer.vault)
