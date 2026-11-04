#!/usr/bin/env python3
"""
Test of the knowledge base against a real Postgres: the kb_* tools as the model calls them
(through the tool registry), the store underneath and its SQL (search, links, revisions).

Covers: slugs and link parsing; write and read back at once; a second note with the same slug
refused (also when archived); links and backlinks; update (replace, append, title, tags, nothing
to change, content and append together); search by words (German prefixes, title first), exact
text (LIKE wildcards are literal) and tags; archive and restore; two users who can't see each
other's notes and a model that can't choose the user; revisions with the conversation and agent;
parallel tool calls (the same title twice, two appends); deleting a user deletes their notes.
The Knowledge base page: tool results that link the step to their note; edits with a version
check, restoring a version or an archived note, deleting for good; the Obsidian export; the API
(backend/api/knowledge_base.py) through FastAPI's test client, also for guests and other users.

It creates the database <POSTGRES_DB>_kb_test if needed (or --database, whose name must contain
"test") and deletes its own test users, so it never touches the real database:

    python backend/services/tests/knowledge_base_test.py

Exit code 0 if every check passed.
"""
import argparse
import asyncio
import io
import logging
import sys
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

# Make the backend package importable when run as a script
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import delete, func, insert, select  # noqa: E402

from backend import config  # noqa: E402
from backend.database.db import Database  # noqa: E402
from backend.database.tables import kb_note_revisions, kb_notes, users  # noqa: E402
from backend.llm.tools import TOOL_GROUPS, ToolInputError, tools_for_groups  # noqa: E402
from backend.services import knowledge_base  # noqa: E402
from backend.services import knowledge_base_export  # noqa: E402
from backend.services.knowledge_base import KBConflict, KBNotFound, Writer, link_targets, note_slug, slugify  # noqa: E402

TEST_EMAILS = ("kb-test-1@example.com", "kb-test-2@example.com")
CONVERSATION = {"id": "kb-test-conversation", "persona_id": 42}

db: Database = None  # The test database, set in main()
user_ids: list[int] = []


def tools(user_index: int = 0):
    return tools_for_groups(["knowledge_base"], user_id=user_ids[user_index], conversation=CONVERSATION)


async def refused(registry, name: str, arguments: dict) -> str:
    """The message of a call the tool must refuse."""
    try:
        result = await registry.call(name, arguments)
    except ToolInputError as e:
        return str(e)
    raise AssertionError(f"{name}({arguments}) should have been refused, got: {result}")


def note_count(user_index: int = 0) -> int:
    with db.connection() as conn:
        return conn.execute(select(func.count()).select_from(kb_notes)
                            .where(kb_notes.c.user_id == user_ids[user_index])).scalar_one()


def reset() -> None:
    """Fresh test users (deleting a user deletes its notes, revisions and links)."""
    with db.connection() as conn:
        conn.execute(delete(users).where(users.c.email.in_(TEST_EMAILS)))
        user_ids[:] = [conn.execute(insert(users).values(email=email, name="KB test").returning(users.c.id)).scalar_one()
                       for email in TEST_EMAILS]


# =========================================================================
# Tests
# =========================================================================

async def test_slugs_and_links():
    assert slugify("Größe & Gewicht") == "groesse-gewicht"
    assert slugify("Café Münster_2026") == "cafe-muenster-2026"
    assert slugify("  --Project   Apollo!-- ") == "project-apollo"
    assert slugify("日本語") == "" and note_slug("日本語").startswith("note-")
    assert len(slugify("x" * 200)) == knowledge_base.MAX_SLUG_CHARS
    content = ("See [[Project Apollo]], [[budget|the budget]], [[plan#step 2]] and [[Budget]] again. "
               "[x](other-note.md) [y](https://example.org/a.md) [z](#heading) [w](folder/Some%20Note.md#part) "
               "[v](mailto:a@b.c)")
    assert link_targets(content) == ["project-apollo", "budget", "plan", "other-note", "some-note"], link_targets(content)
    # [[...]] in code is text, also in a code block that isn't closed
    assert link_targets("A `[[x]]` b\n```\n[[y]]\n```\n[[z]] ~~~\n[[w]]") == ["z"]


async def test_write_and_read_back():
    kb = tools()
    result = await kb.call("kb_write", {"title": "Project Apollo",
                                        "content": "# Project Apollo\nGoal: the moon. Costs are in [[Budget]].",
                                        "description": "The user's space project.", "tags": ["Work", "#space", "work"]})
    assert "**project-apollo**" in result and "[[project-apollo]]" in result, result
    read = await kb.call("kb_read", {"note": "project-apollo"})
    assert read.startswith("# Project Apollo\n"), read
    assert read.count("# Project Apollo") == 1, "the repeated title heading is dropped from the content"
    assert "tags: work, space" in read and "Description: The user's space project." in read, read
    assert "Goal: the moon." in read and "Links to: [[budget]] (no such note yet)" in read, read
    # By title, by a slug-like form and as a [[link]]
    for ref in ("Project Apollo", "project apollo", "[[project-apollo]]"):
        assert (await kb.call("kb_read", {"note": ref})).startswith("# Project Apollo"), ref


async def test_same_slug_is_refused():
    kb = tools()
    await kb.call("kb_write", {"title": "Project Apollo", "content": "First."})
    message = await refused(kb, "kb_write", {"title": "project apollo!", "content": "Second."})
    assert "exists already" in message and "kb_update" in message, message
    assert note_count() == 1
    await kb.call("kb_archive", {"note": "project-apollo"})
    message = await refused(kb, "kb_write", {"title": "Project Apollo", "content": "Third."})
    assert "(archived)" in message, message
    for arguments in ({"title": " ", "content": "x"}, {"title": "T", "content": "  "},
                      {"title": "T", "content": "x", "tags": [f"t{i}" for i in range(21)]},
                      {"title": "T", "content": "x" * (knowledge_base.MAX_CONTENT_CHARS + 1)}):
        await refused(kb, "kb_write", arguments)
    assert note_count() == 1


async def test_links_and_backlinks():
    kb = tools()
    await kb.call("kb_write", {"title": "Project Apollo", "content": "Costs: [[budget]]."})
    await kb.call("kb_write", {"title": "Budget", "content": "Money for [[Project Apollo|Apollo]]."})
    apollo = await kb.call("kb_read", {"note": "project-apollo"})
    assert "Links to: [[budget]] Budget" in apollo and "Linked from: [[budget]] Budget" in apollo, apollo
    # Replacing the content rebuilds the links; an archived note no longer counts as a backlink
    await kb.call("kb_update", {"note": "budget", "content": "No links any more."})
    assert "Linked from" not in await kb.call("kb_read", {"note": "project-apollo"})
    await kb.call("kb_update", {"note": "budget", "append": "Back to [[project-apollo]]."})
    assert "Linked from: [[budget]]" in await kb.call("kb_read", {"note": "project-apollo"})
    await kb.call("kb_archive", {"note": "budget"})
    apollo = await kb.call("kb_read", {"note": "project-apollo"})
    assert "Linked from" not in apollo and "[[budget]] Budget (archived)" in apollo, apollo


async def test_update():
    kb = tools()
    await kb.call("kb_write", {"title": "Groceries", "content": "- milk", "tags": ["home"]})
    result = await kb.call("kb_update", {"note": "groceries", "append": "- bread"})
    assert "appended 7 characters" in result, result
    assert "- milk\n\n- bread" in await kb.call("kb_read", {"note": "groceries"})
    result = await kb.call("kb_update", {"note": "groceries", "title": "Shopping list", "tags": [],
                                         "description": "What to buy."})
    assert "title → \"Shopping list\"" in result and "tags → []" in result and "description changed" in result, result
    read = await kb.call("kb_read", {"note": "groceries"})
    assert read.startswith("# Shopping list\nslug: groceries | tags: none"), read
    assert "nothing was changed" in await kb.call("kb_update", {"note": "groceries", "title": "Shopping list"})
    assert "either content" in await refused(kb, "kb_update", {"note": "groceries", "content": "a", "append": "b"})
    assert "Nothing to change" in await refused(kb, "kb_update", {"note": "groceries"})
    assert "There is no note" in await refused(kb, "kb_update", {"note": "nope", "append": "x"})


async def test_search():
    kb = tools()
    await kb.call("kb_write", {"title": "Katzenfutter", "content": "Die Katzen mögen Thunfisch, 100% sicher.",
                               "tags": ["haustiere"]})
    await kb.call("kb_write", {"title": "Holiday plans", "content": "Rome in May; the cat stays with the neighbours.",
                               "tags": ["travel"]})
    await kb.call("kb_write", {"title": "Cat vet", "content": "Dr. Weber, Tuesdays.", "tags": ["haustiere"]})

    result = await kb.call("kb_search", {"query": "katze"})
    assert "**katzenfutter**" in result and "[matched: words]" in result, result
    result = await kb.call("kb_search", {"query": "cat"})
    assert result.index("**cat-vet**") < result.index("**holiday-plans**"), "a title match ranks first: " + result
    result = await kb.call("kb_search", {"exact": ["thunfisch"]})
    assert "**katzenfutter**" in result and "> Die Katzen mögen Thunfisch" in result, result
    assert "**katzenfutter**" in await kb.call("kb_search", {"exact": ["100%"]})
    # LIKE wildcards are literal: "1_0" must not match "100", "%" alone matches no note without one
    assert (await kb.call("kb_search", {"exact": ["1_0"]})).startswith("No notes found")
    assert "**holiday-plans**" not in await kb.call("kb_search", {"exact": ["%"]})
    result = await kb.call("kb_search", {"tags": ["haustiere"]})
    assert "**katzenfutter**" in result and "**cat-vet**" in result and "holiday" not in result, result
    result = await kb.call("kb_search", {"query": "rome", "exact": ["neighbours"], "tags": ["travel"]})
    assert "[matched: words+exact+tags]" in result, result
    assert "at least one" in await refused(kb, "kb_search", {"query": "!?"})
    assert (await kb.call("kb_search", {"query": "zebra"})).startswith("No notes found")


async def test_list():
    kb = tools()
    assert "empty" in await kb.call("kb_list", {})
    for i in range(3):
        await kb.call("kb_write", {"title": f"Note {i}", "content": "x", "tags": ["a"] + (["b"] if i else [])})
    result = await kb.call("kb_list", {})
    assert result.startswith("3 note(s)") and result.index("note-2") < result.index("note-0"), result
    assert "Tags in use: a (3), b (2)" in result, result
    result = await kb.call("kb_list", {"tag": "b", "max_results": 1})
    assert result.startswith("2 note(s) with the tag 'b', the 1 most recently updated:"), result


async def test_archive_and_restore():
    kb = tools()
    await kb.call("kb_write", {"title": "Old idea", "content": "Something outdated."})
    assert "Archived note **old-idea**" in await kb.call("kb_archive", {"note": "old-idea", "reason": "Outdated"})
    assert "was archived already" in await kb.call("kb_archive", {"note": "old-idea"})
    assert "empty" in await kb.call("kb_list", {})
    assert (await kb.call("kb_search", {"query": "outdated"})).startswith("No notes found")
    assert "Archived:" in await kb.call("kb_read", {"note": "old-idea"})
    assert "restored from the archive" in await kb.call("kb_update", {"note": "old-idea", "append": "Still useful."})
    assert "**old-idea**" in await kb.call("kb_list", {})


async def test_users_are_separate():
    mine, theirs = tools(0), tools(1)
    await mine.call("kb_write", {"title": "Secret plan", "content": "Only mine."})
    assert "There is no note" in await refused(theirs, "kb_read", {"note": "secret-plan"})
    assert "empty" in await theirs.call("kb_list", {})
    assert (await theirs.call("kb_search", {"query": "secret"})).startswith("No notes found")
    # The other user may use the same title; the model can't pick the user
    await theirs.call("kb_write", {"title": "Secret plan", "content": "Mine too."})
    for tool in mine:
        assert "user_id" not in tool.parameters["properties"] and "writer" not in tool.parameters["properties"]
    await theirs.call("kb_update", {"note": "secret-plan", "append": "Hacked?", "user_id": user_ids[0]})
    assert "Hacked?" not in await mine.call("kb_read", {"note": "secret-plan"})
    assert note_count(0) == 1 and note_count(1) == 1
    # Guests and requests without a user get no knowledge base
    assert len(tools_for_groups(["knowledge_base"], user_id=user_ids[0], guest=True)) == 0
    assert len(tools_for_groups(["knowledge_base"])) == 0


async def test_revisions():
    kb = tools()
    await kb.call("kb_write", {"title": "Diary", "content": "Day 1."})
    await kb.call("kb_update", {"note": "diary", "append": "Day 2."})
    await kb.call("kb_update", {"note": "diary", "append": "Day 3."})
    await kb.call("kb_archive", {"note": "diary", "reason": "  Done   with it "})
    await kb.call("kb_update", {"note": "diary", "title": "Diary"})  # no change, but restores it
    with db.connection() as conn:
        rows = conn.execute(
            select(kb_note_revisions).join(kb_notes, kb_notes.c.id == kb_note_revisions.c.note_id)
            .where(kb_notes.c.user_id == user_ids[0]).order_by(kb_note_revisions.c.id)
        ).mappings().all()
    assert [row["action"] for row in rows] == ["create", "update", "update", "archive", "update"], rows
    assert rows[0]["content"] == "Day 1." and rows[2]["content"] == "Day 1.\n\nDay 2.\n\nDay 3."
    assert [row["status"] for row in rows][-2:] == ["archived", "active"]
    assert rows[3]["reason"] == "Done with it"
    assert all(row["author"] == "agent" and row["conversation_id"] == CONVERSATION["id"]
               and row["persona_id"] == CONVERSATION["persona_id"] for row in rows)


async def test_parallel_tool_calls():
    kb = tools()
    results = await asyncio.gather(*(kb.call("kb_write", {"title": "Race", "content": f"Writer {i}"}) for i in range(2)),
                                   return_exceptions=True)
    assert sum(isinstance(result, str) for result in results) == 1, results
    assert all(isinstance(result, str) or "exists already" in str(result) for result in results), results
    await asyncio.gather(*(kb.call("kb_update", {"note": "race", "append": f"Line {i}"}) for i in range(5)))
    read = await kb.call("kb_read", {"note": "race"})
    assert all(f"Line {i}" in read for i in range(5)), read


async def test_deleting_a_user_deletes_the_notes():
    kb = tools()
    await kb.call("kb_write", {"title": "A", "content": "[[b]]"})
    with db.connection() as conn:
        conn.execute(delete(users).where(users.c.id == user_ids[0]))
    assert note_count(0) == 0


async def test_tool_results_link_to_their_note():
    from backend.llm.agent_loop import _step_metadata
    from backend.llm.tools import format_tool_output
    kb = tools()
    result = await kb.call("kb_write", {"title": "Project Apollo", "content": "Goal: the moon."})
    assert result.metadata == {"kbNote": "project-apollo"} and _step_metadata(result) == {"kbNote": "project-apollo"}
    assert type(format_tool_output(result)) is str, "the model gets a plain string"
    for name, arguments in (("kb_read", {"note": "Project Apollo"}), ("kb_update", {"note": "project-apollo", "append": "x"}),
                            ("kb_archive", {"note": "project-apollo"})):
        assert (await kb.call(name, arguments)).metadata == {"kbNote": "project-apollo"}, name
    assert _step_metadata(await kb.call("kb_list", {})) is None


async def test_page_edits_and_versions():
    kb = tools()
    page = Writer(user_ids[0], author="user")
    await kb.call("kb_write", {"title": "Boat", "content": "Length 6 m.", "tags": ["boat"]})
    version = knowledge_base.get_note(user_ids[0], "boat")["version"]
    # The agent appends while the user edits: the user's save is refused, then saved on the new version
    await kb.call("kb_update", {"note": "boat", "append": "Made of oak."})
    try:
        knowledge_base.update_note(page, "boat", content="Length 7 m.", title="Boat", base_version=version)
        raise AssertionError("an edit on an old version must be refused")
    except KBConflict as e:
        assert e.version > version
        version = e.version
    note, changes = knowledge_base.update_note(page, "boat", content="Length 7 m.", title="Boat", description="",
                                               tags=["boat", "project"], base_version=version)
    assert changes and note["version"] > version and note["content"] == "Length 7 m."
    revisions = knowledge_base.list_revisions(user_ids[0], "boat")
    assert [r["action"] for r in revisions] == ["update", "update", "create"], revisions
    assert [r["author"] for r in revisions] == ["user", "agent", "agent"]
    assert revisions[1]["persona_id"] == CONVERSATION["persona_id"] and revisions[0]["conversation_id"] is None
    assert revisions[1]["conversation_name"] is None, "the test conversation doesn't exist"
    # Restoring the first version adds a new one with a reason; the history keeps everything
    first = knowledge_base.get_revision(user_ids[0], "boat", revisions[-1]["id"])
    assert first["content"] == "Length 6 m." and first["tags"] == ["boat"]
    note, changes = knowledge_base.restore_revision(page, "boat", first["id"], base_version=note["version"])
    assert note["content"] == "Length 6 m." and note["tags"] == ["boat"] and changes
    latest = knowledge_base.list_revisions(user_ids[0], "boat")[0]
    assert latest["reason"].startswith("Restored the version of ") and latest["author"] == "user", latest
    try:
        knowledge_base.get_revision(user_ids[1], "boat", first["id"])
        raise AssertionError("another user's note must not be found")
    except KBNotFound:
        pass
    # Archive and restore unchanged; deleting for good removes the note and its versions
    knowledge_base.archive_note(page, "boat")
    assert knowledge_base.list_notes(user_ids[0], status="archived")["total"] == 1
    assert knowledge_base.count_notes(user_ids[0]) == {"active": 0, "archived": 1}
    note, restored = knowledge_base.restore_note(page, "boat")
    assert restored and note["status"] == "active" and note["content"] == "Length 6 m."
    assert knowledge_base.list_revisions(user_ids[0], "boat")[0]["action"] == "restore"
    assert knowledge_base.restore_note(page, "boat")[1] is False
    assert knowledge_base.delete_note(user_ids[0], "boat") == "boat"
    with db.connection() as conn:
        assert conn.execute(select(func.count()).select_from(kb_note_revisions)).scalar_one() == 0
    assert note_count() == 0


async def test_obsidian_export():
    kb = tools()
    page = Writer(user_ids[0], author="user")
    await kb.call("kb_write", {"title": "Project Apollo", "description": 'The "moon" plan: yes',
                               "content": "# Project Apollo\nSee [[Budget Plan]], [[budget-plan#costs|costs]], "
                                          "[[budget-plan]], [old](Old%20Idea.md#top), [web](https://x.org/a.md) and ![i](pic.png).\n"
                                          "```\n[[Budget Plan]]\n```",
                               "tags": ["space", "2026", "a.b c"]})
    await kb.call("kb_write", {"title": "Old idea", "content": "Outdated."})
    await kb.call("kb_archive", {"note": "old-idea"})
    data, count = knowledge_base_export.export_vault(user_ids[0])
    assert count == 2
    archive = zipfile.ZipFile(io.BytesIO(data))
    assert sorted(archive.namelist()) == ["knowledge-base/", "knowledge-base/archive/old-idea.md",
                                          "knowledge-base/project-apollo.md"], archive.namelist()
    apollo = archive.read("knowledge-base/project-apollo.md").decode("utf-8")
    header, body = apollo.split("\n---\n", 1)
    assert header.startswith("---\ntitle: \"Project Apollo\"\naliases:\n  - \"Project Apollo\"\n"), header
    assert 'description: "The \\"moon\\" plan: yes"' in header, header
    assert 'tags:\n  - "space"\n  - "tag-2026"\n  - "a-b-c"' in header, header
    assert "\ncreated: 20" in header and "\nupdated: 20" in header, header
    assert body.startswith("\n# Project Apollo\n\nSee "), body
    assert body.count("# Project Apollo") == 1, body
    assert ("[[budget-plan|Budget Plan]], [[budget-plan#costs|costs]], [[budget-plan]], [old](old-idea.md#top), "
            "[web](https://x.org/a.md) and ![i](pic.png).\n```\n[[Budget Plan]]\n```") in body, body
    assert knowledge_base_export.obsidian_tag("1984") == "tag-1984" and knowledge_base_export.obsidian_tag("#!") is None
    assert knowledge_base_export.obsidian_tag("projekt/größe") == "projekt/größe"
    # Times in the user's time zone (Obsidian reads them as local time), UTC for an unknown zone
    berlin = knowledge_base_export.time_zone("Europe/Berlin")
    assert knowledge_base_export.time_zone("Mars/Olympus") is None and knowledge_base_export.time_zone("../etc") is None
    note = {"slug": "t", "title": "T", "content": "x", "status": "active", "tags": [],
            "created_at": datetime(2026, 1, 15, 12, 0, 5, 123), "updated_at": datetime(2026, 7, 1, 23, 30)}
    assert "created: 2026-01-15T13:00:05\nupdated: 2026-07-02T01:30:00" in knowledge_base_export.note_markdown(note, berlin)
    assert "created: 2026-01-15T12:00:05\n" in knowledge_base_export.note_markdown(note)
    # Another user's export has none of these notes, and an empty knowledge base is an empty vault
    data, count = knowledge_base_export.export_vault(user_ids[1])
    assert count == 0 and zipfile.ZipFile(io.BytesIO(data)).namelist() == ["knowledge-base/"]
    knowledge_base.delete_note(page.user_id, "old-idea")


async def test_api():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import knowledge_base as kb_api
    from backend.security.auth import get_current_user

    current = {"user": {"user_id": user_ids[0], "is_guest": False}}
    app = FastAPI()
    app.include_router(kb_api.router)
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    client = TestClient(app)

    assert client.get("/api/kb/notes").json() == {"notes": [], "total": 0, "tags": [],
                                                  "counts": {"active": 0, "archived": 0}}
    response = client.post("/api/kb/notes", json={"title": "Seeschwalbe", "content": "A boat. See [[sail]].",
                                                  "description": "The boat", "tags": ["Boat"]})
    assert response.status_code == 201, response.text
    note = response.json()
    assert note["slug"] == "seeschwalbe" and note["tags"] == ["boat"] and note["version"] > 0
    assert note["links"] == [{"slug": "sail", "title": None, "status": None}]
    assert note["revisions"][0]["author"] == "user" and note["revisions"][0]["action"] == "create"
    response = client.post("/api/kb/notes", json={"title": "seeschwalbe!", "content": "x"})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "exists", response.text
    assert response.json()["detail"]["slug"] == "seeschwalbe"
    assert client.post("/api/kb/notes", json={"title": " ", "content": "x"}).json()["detail"]["code"] == "invalid"

    # An edit on an old version: 409 conflict with the version now, then saved on it
    await tools().call("kb_update", {"note": "seeschwalbe", "append": "Agent was here."})
    edit = {"title": "Seeschwalbe", "content": "A boat, 6 m.", "description": None, "tags": ["boat"],
            "baseVersion": note["version"]}
    response = client.put("/api/kb/notes/seeschwalbe", json=edit)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "conflict", response.text
    edit["baseVersion"] = response.json()["detail"]["version"]
    note = client.put("/api/kb/notes/seeschwalbe", json=edit).json()
    assert note["content"] == "A boat, 6 m." and note["description"] is None and note["links"] == []
    assert [r["author"] for r in note["revisions"]] == ["user", "agent", "user"]

    hits = client.get("/api/kb/search", params={"q": "boa"}).json()
    assert [hit["slug"] for hit in hits] == ["seeschwalbe"] and hits[0]["matched"], hits
    assert client.get("/api/kb/search", params={"q": "?!"}).json() == []

    first = note["revisions"][-1]
    revision = client.get(f"/api/kb/notes/seeschwalbe/revisions/{first['id']}").json()
    assert revision["content"] == "A boat. See [[sail]]." and revision["description"] == "The boat"
    note = client.post(f"/api/kb/notes/seeschwalbe/revisions/{first['id']}/restore",
                       json={"baseVersion": note["version"]}).json()
    assert note["content"] == "A boat. See [[sail]]." and note["description"] == "The boat"
    assert note["revisions"][0]["reason"].startswith("Restored the version of ")

    note = client.post("/api/kb/notes/seeschwalbe/archive", json={"reason": "Sold"}).json()
    assert note["status"] == "archived" and note["revisions"][0]["reason"] == "Sold"
    listing = client.get("/api/kb/notes", params={"status": "archived"}).json()
    assert [n["slug"] for n in listing["notes"]] == ["seeschwalbe"] and listing["counts"] == {"active": 0, "archived": 1}
    assert client.get("/api/kb/search", params={"q": "boat"}).json() == []
    assert len(client.get("/api/kb/search", params={"q": "boat", "status": "archived"}).json()) == 1
    assert client.post("/api/kb/notes/seeschwalbe/restore").json()["status"] == "active"

    response = client.get("/api/kb/export", params={"tz": "Europe/Berlin"})
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    assert 'filename="knowledge-base-' in response.headers["content-disposition"]
    assert "knowledge-base/seeschwalbe.md" in zipfile.ZipFile(io.BytesIO(response.content)).namelist()

    # Another user and a guest don't reach the note
    current["user"] = {"user_id": user_ids[1], "is_guest": False}
    assert client.get("/api/kb/notes/seeschwalbe").status_code == 404
    assert client.delete("/api/kb/notes/seeschwalbe").status_code == 404
    current["user"] = {"user_id": user_ids[1], "is_guest": True}
    assert client.get("/api/kb/notes").status_code == 403
    current["user"] = {"user_id": user_ids[0], "is_guest": False}
    assert client.delete("/api/kb/notes/seeschwalbe").status_code == 204
    assert client.get("/api/kb/notes/seeschwalbe").json()["detail"]["code"] == "not_found"


TESTS = [test_slugs_and_links, test_write_and_read_back, test_same_slug_is_refused, test_links_and_backlinks,
         test_update, test_search, test_list, test_archive_and_restore, test_users_are_separate, test_revisions,
         test_parallel_tool_calls, test_deleting_a_user_deletes_the_notes, test_tool_results_link_to_their_note,
         test_page_edits_and_versions, test_obsidian_export, test_api]


async def run() -> int:
    failures = 0
    for test in TESTS:
        reset()
        try:
            await test()
            print(f"PASS  {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL  {test.__name__}")
            traceback.print_exc()
    with db.connection() as conn:
        conn.execute(delete(users).where(users.c.email.in_(TEST_EMAILS)))
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} passed")
    return 1 if failures else 0


def main() -> int:
    global db
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--database", default=f"{config.POSTGRES_DB}_kb_test",
                        help="Test database, created if needed (default: <POSTGRES_DB>_kb_test)")
    args = parser.parse_args()
    if "test" not in args.database:
        print(f"Refusing to run against '{args.database}': the name must contain 'test'")
        return 2

    logging.basicConfig(level=logging.WARNING)
    for name in ("backend", "crud", "httpx"):
        logging.getLogger(name).setLevel(logging.WARNING)
    from backend.database.db_init import create_database_if_not_exists
    create_database_if_not_exists(config.POSTGRES_HOST, config.POSTGRES_PORT, config.POSTGRES_USER,
                                  config.POSTGRES_PASSWORD, args.database, logging.getLogger("kb-test"))
    db = Database(database=args.database)
    db.init_tables()
    knowledge_base.db = db  # The store's database; the tools call the store
    assert TOOL_GROUPS["knowledge_base"]
    try:
        return asyncio.run(run())
    finally:
        db.close_all()


if __name__ == "__main__":
    sys.exit(main())
