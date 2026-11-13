#!/usr/bin/env python3
"""
Test of the agents' skills (docs/skills.md) against a real Postgres: storing and checking them,
the agents' lists, SKILL.md files, the catalog file, and what an answer gets.

Covers: creating a skill (names, empty and too long fields, a taken name); the agents' skills
(unknown names refused, duplicates dropped, [] stored as none, the order kept); the agents each
skill lists; renaming a skill (the agents' lists follow, in order) and deleting it (taken off
the agents, none left is NULL); reading SKILL.md (ignored keys, CRLF and a byte order mark, no
frontmatter, bad YAML, a frontmatter that isn't a mapping, a bad name) and writing it (round
trip with colons, quotes, umlauts and a long description); importing a file (created, a taken
name, replace keeps whether it's enabled); the catalog file (export, import of skills and an
agent that names them, seeding that keeps edits, a bad entry next to good ones); the skills of
an answer (enabled only, the agent's order, none for an agent the user may not use or a model
without tools), the prompt section, use_skill through the tool registry (a known and an
unknown name), and the whole answer context (_answer_context()).

It creates the database <POSTGRES_DB>_skills_test if needed (or --database, whose name must
contain "test") and deletes its own test data, so it never touches the real database:

    python backend/services/tests/skills_test.py

Exit code 0 if every check passed.
"""
import argparse
import asyncio
import dataclasses
import json
import logging
import sys
import tempfile
import traceback
from pathlib import Path

# Make the backend package importable when run as a script
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pydantic import ValidationError  # noqa: E402
from sqlalchemy import delete, insert, select  # noqa: E402

from backend import config  # noqa: E402
from backend.api import messages as messages_api  # noqa: E402
from backend.catalog import catalog_file, resolver, service  # noqa: E402
from backend.catalog.service import CatalogError  # noqa: E402
from backend.database.db import Database  # noqa: E402
from backend.database.tables import conversations, personas, skills as skills_table, users  # noqa: E402
from backend.llm.prompts import SKILLS_HEADING, with_skills  # noqa: E402
from backend.llm.tools import ToolInputError, ToolRegistry, skill_tools  # noqa: E402
from backend.llm.types import ModelConfig  # noqa: E402
from backend.models.catalog import PersonaCreate, PersonaUpdate, SkillCreate, SkillUpdate  # noqa: E402
from backend.services import hidden_content, skills  # noqa: E402
from backend.services.mcp import store as mcp_store  # noqa: E402
from backend.services.skills import SkillConflict, SkillError, SkillNotFound  # noqa: E402

PREFIX = "skilltest"  # Skill names and agent names of this test start with it
TEST_EMAIL = "skills-test@example.com"

db: Database = None  # The test database, set in main()


def skill(suffix: str, description: str = "Does a thing. Use when asked.", content: str = "Step 1.\nStep 2.",
          enabled: bool = True) -> dict:
    return skills.create_skill(SkillCreate(name=f"{PREFIX}-{suffix}", description=description, content=content,
                                           enabled=enabled))


def agent(name: str, skill_names=None, **fields):
    return service.create_persona(PersonaCreate(name=f"{PREFIX} {name}", systemPrompt="You help.",
                                                skills=skill_names, **fields))


def agent_skills_of(persona_id: int):
    with db.connection() as conn:
        return conn.execute(select(personas.c.skills).where(personas.c.id == persona_id)).scalar_one()


def refused(error_type, call, *args, **kwargs) -> str:
    try:
        result = call(*args, **kwargs)
    except error_type as e:
        return str(e)
    raise AssertionError(f"should have been refused, got: {result}")


def cleanup() -> None:
    with db.connection() as conn:
        conn.execute(delete(personas).where(personas.c.name.like(f"{PREFIX} %")))
        conn.execute(delete(skills_table).where(skills_table.c.name.like(f"{PREFIX}-%")))
        conn.execute(delete(conversations).where(conversations.c.id.like("skills-test-%")))
        conn.execute(delete(users).where(users.c.email == TEST_EMAIL))


# =========================================================================
# Checks
# =========================================================================

def check_create() -> None:
    created = skill("basics", description="  Writes things.  ", content="\n\n# Basics\n\nDo it.\n\n")
    assert created["description"] == "Writes things." and created["content"] == "# Basics\n\nDo it."
    assert created["enabled"] is True and created["agents"] == []
    assert "already exists" in refused(SkillConflict, skill, "basics")
    for bad in ("Image-Prompts", "image prompts", "-image", "image-", "image--prompts", "x" * 65, "bild_prompts"):
        try:
            SkillCreate(name=bad, description="d", content="c")
        except ValidationError as e:
            assert "lowercase letters, digits and single hyphens" in skills.validation_message(e), bad
        else:
            raise AssertionError(f"{bad!r} should not be a valid name")
    SkillCreate(name="a" * 64, description="d", content="c")
    for field, value in (("description", "x" * 1025), ("content", "x" * 20001), ("description", "")):
        try:
            SkillCreate(**{"name": "ok", "description": "d", "content": "c", field: value})
        except ValidationError:
            pass
        else:
            raise AssertionError(f"{field} of {len(value)} characters should be refused")
    assert "must not be empty" in refused(SkillError, skill, "blank", description="   ")
    assert "not found" in refused(SkillNotFound, skills.get_skill, 999_999_999)
    assert "not found" in refused(SkillNotFound, skills.update_skill, 999_999_999, SkillUpdate(enabled=False))
    assert "not found" in refused(SkillNotFound, skills.delete_skill, 999_999_999)


def check_agents_rename_delete() -> None:
    a, b, c = skill("alpha"), skill("beta"), skill("gamma")
    names = [a["name"], b["name"], c["name"]]
    first = agent("First", [names[2], names[0], names[2], names[1]])
    assert first.skills == [names[2], names[0], names[1]], first.skills  # Duplicates dropped, order kept
    second = agent("Second", [names[1]])
    assert agent("None", []).skills is None  # [] is stored as none
    assert "Unknown skill(s): nope" in refused(CatalogError, agent, "Bad", [names[0], "nope"])
    assert "Unknown skill(s)" in refused(CatalogError, service.update_persona, second.id,
                                         PersonaUpdate(skills=["nope"]))
    assert service.update_persona(second.id, PersonaUpdate(name=f"{PREFIX} Second")).skills == [names[1]]

    listed = {entry["name"]: [agent["name"] for agent in entry["agents"]] for entry in skills.list_skills()}
    assert listed[names[1]] == [f"{PREFIX} First", f"{PREFIX} Second"], listed[names[1]]
    assert listed[names[0]] == [f"{PREFIX} First"]

    renamed = skills.update_skill(a["id"], SkillUpdate(name=f"{PREFIX}-alpha-two", description="New."))
    assert renamed["name"] == f"{PREFIX}-alpha-two" and renamed["description"] == "New."
    assert agent_skills_of(first.id) == [names[2], f"{PREFIX}-alpha-two", names[1]]
    assert "already exists" in refused(SkillConflict, skills.update_skill, b["id"], SkillUpdate(name=names[2]))
    assert agent_skills_of(first.id) == [names[2], f"{PREFIX}-alpha-two", names[1]]  # Rolled back

    skills.delete_skill(b["id"])
    assert agent_skills_of(first.id) == [names[2], f"{PREFIX}-alpha-two"]
    assert agent_skills_of(second.id) is None  # Its only skill: none left is NULL
    skills.delete_skill(c["id"])
    skills.delete_skill(a["id"])
    assert agent_skills_of(first.id) is None


def check_skill_md() -> None:
    source = ("﻿---\r\nname: skilltest-md\r\ndescription: >\r\n  Folded text\r\n  over two lines.\r\n"
              "license: MIT\r\nallowed-tools: Read\r\nmetadata:\r\n  version: 2\r\n---\r\n\r\n# Title\r\n\r\nBody.\r\n")
    parsed, ignored = skills.parse_skill_md(source)
    assert parsed == {"name": "skilltest-md", "description": "Folded text over two lines.",
                      "content": "# Title\n\nBody."}, parsed
    assert ignored == ["allowed-tools", "license", "metadata"], ignored
    assert "starts with YAML frontmatter" in refused(SkillError, skills.parse_skill_md, "# No frontmatter\n")
    assert "not valid YAML" in refused(SkillError, skills.parse_skill_md, "---\nname: [unclosed\n---\nx")
    assert "keys with values" in refused(SkillError, skills.parse_skill_md, "---\n- a\n- b\n---\nx")
    # Frontmatter with nothing after it is a skill without text
    assert skills.parse_skill_md("---\nname: x\ndescription: y\n---")[0]["content"] == ""

    tricky = {"name": "skilltest-round", "content": "# Über\n\nKeys: values, \"quotes\" and 'apostrophes'.",
              "description": "Writes: things with \"quotes\", # hashes, äöü and a long tail " + "x" * 600 + "."}
    written = skills.format_skill_md(tricky)
    assert written.startswith("---\nname: skilltest-round\n") and written.endswith("apostrophes'.\n")
    again, ignored = skills.parse_skill_md(written)
    assert again == tricky and ignored == [], again

    created, was_created, ignored = skills.import_skill_md(source)
    assert was_created and ignored == ["allowed-tools", "license", "metadata"] and created["content"] == "# Title\n\nBody."
    assert "already exists" in refused(SkillConflict, skills.import_skill_md, source)
    skills.update_skill(created["id"], SkillUpdate(enabled=False))
    replaced, was_created, _ = skills.import_skill_md(source.replace("Body.", "New body."), replace=True)
    assert not was_created and replaced["id"] == created["id"] and replaced["content"] == "# Title\n\nNew body."
    assert replaced["enabled"] is False  # Whether it's enabled stays
    message = refused(SkillError, skills.import_skill_md, "---\nname: Bad Name\ndescription: d\n---\ntext")
    assert "lowercase letters" in message, message
    assert "content" in refused(SkillError, skills.import_skill_md, "---\nname: skilltest-empty\ndescription: d\n---\n")
    skills.delete_skill(created["id"])


def check_catalog_file() -> None:
    kept = skill("kept", description="Original.")
    agent("Exported", [kept["name"]])
    exported = catalog_file.export_catalog()
    entry = next(entry for entry in exported["skills"] if entry["name"] == kept["name"])
    assert entry == {"name": kept["name"], "description": "Original.", "content": "Step 1.\nStep 2.", "enabled": True}
    persona_entry = next(entry for entry in exported["personas"] if entry["name"] == f"{PREFIX} Exported")
    assert persona_entry["skills"] == [kept["name"]]
    assert list(exported).index("skills") < list(exported).index("personas")

    data = {
        "version": 1,
        "skills": [
            {"name": f"{PREFIX}-imported", "description": "From a file.", "content": "Text."},
            {"name": kept["name"], "description": "Changed by the import."},
            {"name": "Not A Name", "description": "d", "content": "c"},
            {"name": f"{PREFIX}-extra", "description": "d", "content": "c", "colour": "red"},
        ],
        "personas": [{"name": f"{PREFIX} Imported", "system_prompt": "You help.",
                      "skills": [f"{PREFIX}-imported", kept["name"]]}],
    }
    result = catalog_file.import_catalog(data)
    assert (result.skills.created, result.skills.updated) == (2, 1), result
    assert result.personas.created == 1, result
    assert any("Not A Name" in error and "lowercase letters" in error for error in result.errors), result.errors
    assert any("unknown key 'colour'" in error for error in result.errors), result.errors
    assert skills.get_skill_by_name(kept["name"])["description"] == "Changed by the import."
    imported_agent = next(p for p in service.list_personas() if p.name == f"{PREFIX} Imported")
    assert imported_agent.skills == [f"{PREFIX}-imported", kept["name"]]

    # Seeding only creates what's missing: the change made in the app stays
    seed = {"version": 1, "skills": [{"name": kept["name"], "description": "From the seed.", "content": "Seed."},
                                     {"name": f"{PREFIX}-seeded", "description": "New.", "content": "Seed."}]}
    seeded = catalog_file.seed_catalog(seed)
    assert (seeded.skills.created, seeded.skills.kept) == (1, 1), seeded
    assert skills.get_skill_by_name(kept["name"])["description"] == "Changed by the import."

    # A seed file names SKILL.md files next to it; never one outside its folder
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder) / "catalog"
        (root / "skills" / "from-file").mkdir(parents=True)
        (root / "skills" / "from-file" / "SKILL.md").write_text(
            f"---\nname: {PREFIX}-from-file\ndescription: Read from a file.\n---\n\n# From a file\n")
        (Path(folder) / "SKILL.md").write_text(f"---\nname: {PREFIX}-outside\ndescription: d\n---\ntext\n")
        (root / "catalog.json").write_text(json.dumps({"version": 1, "skills": [
            {"file": "skills/from-file/SKILL.md", "enabled": False},
            {"file": "../SKILL.md"},
            {"file": "skills/missing/SKILL.md"},
        ]}))
        from_files = catalog_file.seed_from_file(root / "catalog.json")
    assert from_files.skills.created == 1, from_files
    read = skills.get_skill_by_name(f"{PREFIX}-from-file")
    assert read["content"] == "# From a file" and read["description"] == "Read from a file." and not read["enabled"]
    assert skills.get_skill_by_name(f"{PREFIX}-outside") is None

    # The skills that ship with the app are valid
    shipped = json.loads((PROJECT_ROOT / "catalog" / "models.json").read_text())
    data = {"version": 1, "skills": [entry for entry in shipped.get("skills", []) if "file" in entry]}
    assert not catalog_file._read_skill_files(data, PROJECT_ROOT / "catalog"), "a shipped skill file can't be read"
    for entry in data["skills"]:
        SkillCreate(**{key: entry[key] for key in ("name", "description", "content")})


async def check_answer() -> None:
    on = skill("on", description="Paints\n  pictures.", content="Use warm colours.")
    off = skill("off", enabled=False)
    later = skill("later", description="Writes later.")
    names = [later["name"], off["name"], on["name"]]
    helper = agent("Helper", names)
    hidden_agent = agent("Disabled", [on["name"]], enabled=False)
    with db.connection() as conn:
        user_id = conn.execute(insert(users).values(email=TEST_EMAIL, name="Skill tester")
                               .returning(users.c.id)).scalar_one()
        conn.execute(insert(conversations).values(id="skills-test-1", userId=user_id, name="Chat",
                                                  persona_id=helper.id))
    user = {"user_id": user_id, "email": TEST_EMAIL, "is_guest": False}

    found = resolver.persona_skills(user, {"persona_id": helper.id})
    assert [s["name"] for s in found] == [later["name"], on["name"]]  # Enabled only, the agent's order
    assert resolver.persona_skills(user, {"persona_id": hidden_agent.id}) == []
    assert resolver.persona_skills(user, {"persona_id": None}) == []

    prompt = with_skills("You help.", found)
    assert prompt.startswith("You help.\n\n" + SKILLS_HEADING)
    assert f"- {on['name']}: Paints pictures." in prompt and off["name"] not in prompt
    assert with_skills("You help.", []) == "You help."

    registry = ToolRegistry(skill_tools(found))
    assert registry.names() == ["use_skill"] and registry.title("use_skill") == "Using Skill"
    schema = registry.openai_schemas()[0]["function"]["parameters"]["properties"]["name"]
    assert schema["enum"] == [later["name"], on["name"]]
    text = await registry.call("use_skill", {"name": on["name"]})
    assert text.endswith("Use warm colours.") and on["name"] in text
    try:
        await registry.call("use_skill", {"name": off["name"]})
    except ToolInputError as e:
        assert "no skill named" in str(e) and on["name"] in str(e)
    else:
        raise AssertionError("a disabled skill should not load")
    assert skill_tools([]) == []

    # The whole context of an answer, as stream-generate builds it
    config = ModelConfig(id=None, display_name="Fake", model_id="fake", provider_id=None, provider_name="Fake",
                         kind="openai_compatible", base_url="http://127.0.0.1:9", supports_tools=True)
    tools, _, system_prompt, _, _, _ = await messages_api._answer_context(user, "skills-test-1", config, mcp=False)
    assert "use_skill" in tools.names(), tools.names()
    assert SKILLS_HEADING in system_prompt and f"- {later['name']}: Writes later." in system_prompt
    no_tools = dataclasses.replace(config, supports_tools=False)
    tools, _, system_prompt, _, _, _ = await messages_api._answer_context(user, "skills-test-1", no_tools, mcp=False)
    assert tools is None and SKILLS_HEADING not in system_prompt
    # An agent without tool groups still gets use_skill
    service.update_persona(helper.id, PersonaUpdate(tools=[]))
    tools, _, _, _, _, _ = await messages_api._answer_context(user, "skills-test-1", config, mcp=False)
    assert tools.names() == ["use_skill"], tools.names()


# =========================================================================
# Runner
# =========================================================================

CHECKS = [check_create, check_agents_rename_delete, check_skill_md, check_catalog_file, check_answer]


async def run() -> int:
    failed = 0
    for check in CHECKS:
        cleanup()
        try:
            result = check()
            if asyncio.iscoroutine(result):
                await result
            print(f"PASS {check.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {check.__name__}")
            traceback.print_exc()
    cleanup()
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} passed")
    return 1 if failed else 0


def main() -> int:
    global db
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--database", default=f"{config.POSTGRES_DB}_skills_test",
                        help="Test database, created if needed (default: <POSTGRES_DB>_skills_test)")
    args = parser.parse_args()
    if "test" not in args.database:
        print(f"Refusing to run against '{args.database}': the name must contain 'test'")
        return 2

    logging.basicConfig(level=logging.WARNING)
    for name in ("backend", "httpx"):
        logging.getLogger(name).setLevel(logging.WARNING)
    from backend.database.db_init import create_database_if_not_exists, migrate_schema
    create_database_if_not_exists(config.POSTGRES_HOST, config.POSTGRES_PORT, config.POSTGRES_USER,
                                  config.POSTGRES_PASSWORD, args.database, logging.getLogger("skills-test"))
    db = Database(database=args.database)
    # As app_init --prod does: add the columns a test database from an older version lacks, then the schema
    migrate_schema(db.engine, logging.getLogger("skills-test"))
    db.init_tables()
    # The modules' database: the stores, the catalog, and what an answer reads
    for module in (skills, service, catalog_file, resolver, mcp_store, messages_api, hidden_content):
        module.db = db
    try:
        return asyncio.run(run())
    finally:
        db.close_all()


if __name__ == "__main__":
    sys.exit(main())
