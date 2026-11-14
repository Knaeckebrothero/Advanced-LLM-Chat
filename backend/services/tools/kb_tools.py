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

Notes keep files, e.g. images (docs/knowledge_base.md, "Files"): kb_write and kb_update take files
of the conversation (files), and the results that show notes name the files they keep. Those
results carry the files ({"kbFiles": [...]}, as file_store.file_ref()), so the chat finds one the
answer places in its text by its name.
"""
import logging
from datetime import datetime
from typing import List, Optional

from backend.llm.tools import ToolInputError, ToolText
from backend.services import file_store
from backend.services import knowledge_base as kb
from backend.services.file_store import FileStoreError
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


def _about(note: dict, text: str, vault: int = 0, files: Optional[List[dict]] = None) -> ToolText:
    """A result about one note: its step in the chat links to the note, and knows the files it names."""
    return ToolText(text, {"kbNote": note["slug"], **({"kbVault": vault} if vault else {}), **_known(files)})


def _known(files: Optional[List[dict]]) -> dict:
    """The kept files a result names, for its step: the chat finds one the answer places by its name."""
    return {"kbFiles": [file_store.file_ref(row) for row in files]} if files else {}


def _file(row: dict, size: bool = False) -> str:
    """A kept file for the model: name (type, pixels), with size also its size."""
    facts = [file_store.file_type(row)]
    if row.get("width") and row.get("height"):
        facts.append(f"{row['width']}×{row['height']} px")
    if size:
        facts.append(file_store.format_size(file_store.file_size(row)))
    return f"{row['name']} ({', '.join(facts)})"


def _show_hint(files: List[dict]) -> str:
    """How to show a kept file, with the first of the files as the example."""
    return (f"To show a file a note keeps, place it in your answer by its name: "
            f"![what it shows]({files[0]['name']}).")


def _files(references: Optional[List[str]], writer: Writer) -> List[dict]:
    """
    The stored files a write keeps, for the names or file IDs the model gives: files of the
    conversation it answers in, or files the knowledge base keeps already.

    Raises:
        ToolInputError: A file is neither.
    """
    rows = []
    for reference in references or []:
        try:
            rows.append(file_store.find_file(writer.conversation_id, writer.user_id, str(reference)))
        except FileStoreError as e:
            kept = kb.find_file(writer.user_id, writer.vault, str(reference), family_mode=writer.family_mode)
            if kept is None:
                raise ToolInputError(f"{e}. files takes files of this conversation (list_files shows them); "
                                     f"nothing was written")
            rows.append(kept)
    return rows


def _kept(note: dict) -> str:
    """What a write did with the files it was given, for the model."""
    lines = []
    if note.get("kept"):
        names = ", ".join(note["kept"])
        lines.append(f" The note keeps {names}: {'it stays' if len(note['kept']) == 1 else 'they stay'} in the "
                     f"knowledge base when this conversation is gone. Show it in an answer, in any conversation, by "
                     f"placing it by that name: ![what it shows]({note['kept'][0]}).")
    for name, slug in (note.get("kept_already") or {}).items():
        lines.append(f" {name} is kept already" + (f" by the note [[{slug}]]" if slug != note["slug"] else "")
                     + "; this note shows it.")
    return "".join(lines)


def _clamp(value: Optional[int], default: int, maximum: int) -> int:
    return default if value is None else max(1, min(int(value), maximum))


def kb_search(query: Optional[str] = None, exact: Optional[List[str]] = None, tags: Optional[List[str]] = None,
              max_results: Optional[int] = None, *, user_id: int, vault: int = 0, family_mode: bool = False) -> str:
    """Search the active notes; see knowledge_base.search_notes()."""
    try:
        hits = kb.search_notes(user_id, query=query, exact=exact, tags=tags,
                               limit=_clamp(max_results, 10, MAX_SEARCH_RESULTS), vault=vault, family_mode=family_mode)
    except KBError as e:
        raise _refused(e)
    if not hits:
        return "No notes found. Try other words, an exact text or kb_list for an overview."
    lines = [f"{len(hits)} note(s) found, best first:"]
    files = []
    for i, hit in enumerate(hits, 1):
        lines.append(f"{i}. **{hit['slug']}**: {hit['title']} [matched: {'+'.join(hit['matched'])}] "
                     f"(tags: {_tags(hit['tags'])}; updated {_date(hit['updated_at'])})")
        if hit["description"]:
            lines.append(f"   {hit['description']}")
        lines.append(f"   > {hit['snippet']}")
        if hit["files"]:
            lines.append("   Keeps: " + ", ".join(_file(row) for row in hit["files"]))
            files += hit["files"]
    lines.append("Read a note in full with kb_read.")
    if files:
        lines.append(_show_hint(files))
    text = "\n".join(lines)
    return ToolText(text, _known(files)) if files else text


def kb_list(tag: Optional[str] = None, max_results: Optional[int] = None, *, user_id: int, vault: int = 0,
            family_mode: bool = False) -> str:
    """List the active notes, newest first, and the tags in use."""
    try:
        result = kb.list_notes(user_id, tag=tag, limit=_clamp(max_results, 50, MAX_LIST_RESULTS), vault=vault,
                               family_mode=family_mode)
    except KBError as e:
        raise _refused(e)
    notes, total = result["notes"], result["total"]
    if total == 0:
        return (f"No notes with the tag '{tag}'." if tag
                else "The knowledge base is empty. Create the first note with kb_write.")
    shown = f"the {len(notes)} most recently updated" if len(notes) < total else "most recently updated first"
    lines = [f"{total} note(s){f' with the tag {tag!r}' if tag else ''}, {shown}:"]
    files = []
    for note in notes:
        description = f": {note['description']}" if note["description"] else ""
        keeps = f"; keeps {', '.join(row['name'] for row in note['files'])}" if note["files"] else ""
        lines.append(f"- **{note['slug']}**: {note['title']}{description} "
                     f"(tags: {_tags(note['tags'])}; updated {_date(note['updated_at'])}{keeps})")
        files += note["files"]
    if result["tags"]:
        lines.append("Tags in use: " + ", ".join(f"{name} ({count})" for name, count in result["tags"]))
    if files:
        lines.append(_show_hint(files))
    text = "\n".join(lines)
    return ToolText(text, _known(files)) if files else text


def kb_read(note: str, *, user_id: int, vault: int = 0, family_mode: bool = False, reads_files: bool = False) -> str:
    """
    A note in full, with the notes it links to, the notes that link to it and the files it keeps
    (reads_files: the agent has read_file, and is told that it reads them).
    """
    try:
        found = kb.get_note(user_id, note, vault=vault, family_mode=family_mode)
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
    files = found["files"] + found["placed_files"]
    if found["files"]:
        lines.append("Files this note keeps:")
        for row in found["files"]:
            origin = (f"created by {row['origin']}" if row.get("origin") else "created by a tool") \
                if row.get("source") == file_store.SOURCE_TOOL else "uploaded by the user"
            made_with = f". Made with these arguments: {row['details']}" if row.get("details") else ""
            lines.append(f"- {_file(row, size=True)}: {origin}, {_date(row.get('created_at'))}{made_with}")
    if found["placed_files"]:
        lines.append("It also shows: " + "; ".join(f"{_file(row)}, kept by [[{row['note_slug']}]]"
                                                   for row in found["placed_files"]))
    if files:
        look = f" To look at one yourself: read_file(file=\"{files[0]['name']}\")." if reads_files else ""
        lines.append(_show_hint(files) + look)
    return _about(found, "\n".join(lines).rstrip(), vault, files)


def _length_hint(content: str) -> str:
    if len(content) > kb.LONG_NOTE_CHARS:
        return (f" The note is long ({len(content)} characters); consider splitting it into notes on single "
                f"topics that link to each other.")
    return ""


def _kept_rows(note: dict, writer: Writer) -> List[dict]:
    """The files of a write as the knowledge base keeps them, for the step of its result."""
    names = list(note.get("kept") or []) + list(note.get("kept_already") or {})
    rows = (kb.find_file(writer.user_id, writer.vault, name, family_mode=writer.family_mode) for name in names)
    return [row for row in rows if row is not None]


def kb_write(title: str, content: str, description: Optional[str] = None, tags: Optional[List[str]] = None,
             hidden: Optional[bool] = None, files: Optional[List[str]] = None, *, writer: Writer) -> str:
    """Create a note (hidden: the note is hidden; files: files of the conversation it keeps)."""
    rows = _files(files, writer)
    try:
        note = kb.create_note(writer, title, content, description=description, tags=tags, hidden_note=bool(hidden),
                              files=rows)
    except KBError as e:
        raise _refused(e)
    return _about(note, f"Created note **{note['slug']}** (\"{note['title']}\", tags: {_tags(note['tags'])}). "
                        f"Link to it with [[{note['slug']}]].{_kept(note)}{_length_hint(note['content'])} If it "
                        f"matters beyond this conversation, give it a short line in the memory that points to it: "
                        f"memory_add(\"<what it is about> → [[{note['slug']}]]\").", writer.vault,
                  _kept_rows(note, writer))


def kb_update(note: str, content: Optional[str] = None, append: Optional[str] = None, title: Optional[str] = None,
              description: Optional[str] = None, tags: Optional[List[str]] = None, hidden: Optional[bool] = None,
              files: Optional[List[str]] = None, *, writer: Writer) -> str:
    """
    Change a note (hidden: hide it or take the mark back, unless the user decided; files: files of
    the conversation it keeps from now on).
    """
    rows = _files(files, writer)
    try:
        updated, changes = kb.update_note(writer, note, content=content, append=append, title=title,
                                          description=description, tags=tags, hidden_note=hidden, files=rows)
    except KBError as e:
        raise _refused(e)
    if not changes:
        return _about(updated, f"Note **{updated['slug']}** already has these values; nothing was changed."
                               f"{_kept(updated)}", writer.vault, _kept_rows(updated, writer))
    return _about(updated, f"Updated note **{updated['slug']}**: {', '.join(changes)}.{_kept(updated)}"
                           f"{_length_hint(updated['content'])}", writer.vault, _kept_rows(updated, writer))


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


def memory_add(text: str, section: Optional[str] = None, hidden: Optional[bool] = None, *, writer: Writer) -> str:
    """Add a line to the memory (hidden: the line is hidden and gets the tag #hidden)."""
    try:
        memory, changed = kb.memory_add(writer, text, section=section, hidden_line=hidden)
    except KBError as e:
        raise _refused(e)
    if not changed:
        return _about(memory, "The memory has this line already; nothing was changed.", writer.vault)
    where = f" under \"{' '.join(section.split()).lstrip('#').strip()}\"" if section and section.strip() else ""
    return _about(memory, f"Added the line{where}. {kb.memory_status(memory['content'])}", writer.vault)


def memory_replace(line: str, text: str, hidden: Optional[bool] = None, *, writer: Writer) -> str:
    """Replace a line of the memory (hidden: whether the new line is hidden; left out, it keeps the old line's mark)."""
    try:
        memory = kb.memory_replace(writer, line, text, hidden_line=hidden)
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
