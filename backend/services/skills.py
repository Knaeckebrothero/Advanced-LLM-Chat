"""
Skills (docs/skills.md): texts that tell an agent how to do one kind of work well, in the SKILL.md
format (agentskills.io). Admins write them and attach them to agents (personas.skills, a list of
names); the agent sees their names and descriptions in its prompt (with_skills() in
backend/llm/prompts.py) and loads one with use_skill (skill_tools() in backend/llm/tools.py).

This module stores them (table skills), keeps the agents' lists in step when a skill is renamed or
deleted, and reads and writes SKILL.md files. Errors are SkillError subclasses with an HTTP status.
"""
import logging
import re
from typing import Iterable, Optional

import yaml
from pydantic import ValidationError
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from backend.database import db
from backend.database.tables import personas, skills
from backend.models.catalog import SKILL_NAME_MAX, SkillCreate, SkillUpdate

log = logging.getLogger(__name__)


class SkillError(Exception):
    """Invalid skill input (HTTP 400)."""
    status_code = 400


class SkillNotFound(SkillError):
    """The skill does not exist (HTTP 404)."""
    status_code = 404


class SkillConflict(SkillError):
    """The name is taken (HTTP 409)."""
    status_code = 409


NAME_RULE = (f"a skill's name has lowercase letters, digits and single hyphens between them, "
             f"at most {SKILL_NAME_MAX} characters, e.g. image-generation")


def validation_message(error: ValidationError) -> str:
    """A Pydantic error of SkillCreate or SkillUpdate in words, with the rule for names."""
    parts = []
    for item in error.errors():
        field = ".".join(str(part) for part in item["loc"]) or "skill"
        parts.append(NAME_RULE if field == "name" and item["type"] in ("string_pattern_mismatch", "string_too_long")
                     else f"{field}: {item['msg']}")
    return "; ".join(parts)


# =========================================================================
# Storage
# =========================================================================

def _clean(values: dict) -> dict:
    """The values with name, description and content stripped; an empty one is refused."""
    cleaned = {}
    for key, value in values.items():
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise SkillError(f"{key} must not be empty")
        cleaned[key] = value
    return cleaned


def _rows(conn, query) -> list[dict]:
    return [dict(row._mapping) for row in conn.execute(query)]


def _with_agents(rows: list[dict]) -> list[dict]:
    """The skill rows, each with "agents": the agents that have it ({"id", "name"}, higher sort order first, then name)."""
    with db.connection() as conn:
        agents = conn.execute(
            select(personas.c.id, personas.c.name, personas.c.skills)
            .where(personas.c.skills.is_not(None))
            .order_by(func.coalesce(personas.c.sort_order, 0).desc(), func.lower(personas.c.name), personas.c.id)
        ).all()
    by_name: dict[str, list[dict]] = {}
    for agent in agents:
        for name in agent.skills or []:
            by_name.setdefault(name, []).append({"id": agent.id, "name": agent.name})
    return [{**row, "agents": by_name.get(row["name"], [])} for row in rows]


def list_skills() -> list[dict]:
    """Every skill, disabled ones too, by name, with the agents that have it."""
    with db.connection() as conn:
        rows = _rows(conn, select(skills).order_by(skills.c.name))
    return _with_agents(rows)


def get_skill(skill_id: int) -> dict:
    """A skill with the agents that have it (raises SkillNotFound)."""
    with db.connection() as conn:
        row = conn.execute(select(skills).where(skills.c.id == skill_id)).first()
    if not row:
        raise SkillNotFound(f"Skill {skill_id} not found")
    return _with_agents([dict(row._mapping)])[0]


def get_skill_by_name(name: str) -> Optional[dict]:
    with db.connection() as conn:
        row = conn.execute(select(skills).where(skills.c.name == name)).first()
    return dict(row._mapping) if row else None


def skills_by_name(names: Iterable[str], enabled_only: bool = False) -> list[dict]:
    """The skills with these names, in the order of names (unknown ones, and with enabled_only disabled ones, left out)."""
    names = list(dict.fromkeys(names))
    if not names:
        return []
    query = select(skills).where(skills.c.name.in_(names))
    if enabled_only:
        query = query.where(skills.c.enabled.is_(True))
    with db.connection() as conn:
        found = {row["name"]: row for row in _rows(conn, query)}
    return [found[name] for name in names if name in found]


def _taken(name: str, error: IntegrityError) -> SkillError:
    if getattr(error.orig, "pgcode", None) == "23505":
        return SkillConflict(f"A skill named '{name}' already exists")
    return SkillError(f"The skill could not be saved: {error.orig}")


def create_skill(data: SkillCreate) -> dict:
    """Create a skill (raises SkillConflict when the name is taken)."""
    values = _clean(data.model_dump())
    try:
        with db.connection() as conn:
            row = conn.execute(insert(skills).values(**values).returning(skills)).first()
    except IntegrityError as e:
        raise _taken(values["name"], e) from e
    log.info(f"Created skill {row.id} ({row.name})")
    return get_skill(row.id)


def update_skill(skill_id: int, data: SkillUpdate) -> dict:
    """
    Change the fields of a skill that were sent (null leaves a field as it is). A new name is
    also changed in the lists of the agents that have the skill, in the same transaction.
    """
    values = _clean({key: value for key, value in data.model_dump(exclude_unset=True).items() if value is not None})
    try:
        with db.connection() as conn:
            old = conn.execute(select(skills.c.name).where(skills.c.id == skill_id)).scalar()
            if old is None:
                raise SkillNotFound(f"Skill {skill_id} not found")
            if values:
                conn.execute(update(skills).where(skills.c.id == skill_id).values(**values))
            new = values.get("name", old)
            if new != old:
                conn.execute(text(
                    "UPDATE personas SET skills = (SELECT jsonb_agg(CASE WHEN s = :old THEN :new ELSE s END "
                    "ORDER BY n) FROM jsonb_array_elements_text(skills) WITH ORDINALITY AS t(s, n)) "
                    "WHERE skills ? :old"), {"old": old, "new": new})
    except IntegrityError as e:
        raise _taken(values.get("name", ""), e) from e
    log.info(f"Updated skill {skill_id}: {sorted(values)}")
    return get_skill(skill_id)


def delete_skill(skill_id: int) -> None:
    """Delete a skill and take it off the agents that have it, in one transaction."""
    with db.connection() as conn:
        name = conn.execute(delete(skills).where(skills.c.id == skill_id).returning(skills.c.name)).scalar()
        if name is None:
            raise SkillNotFound(f"Skill {skill_id} not found")
        # jsonb_agg over no rows is NULL: an agent whose only skill this was has none
        conn.execute(text(
            "UPDATE personas SET skills = (SELECT jsonb_agg(s ORDER BY n) "
            "FROM jsonb_array_elements_text(skills) WITH ORDINALITY AS t(s, n) WHERE s <> :name) "
            "WHERE skills ? :name"), {"name": name})
    log.info(f"Deleted skill {skill_id} ({name})")


# =========================================================================
# Agents
# =========================================================================

def check_agent_skills(names: Optional[list]) -> Optional[list[str]]:
    """An agent's skills: known names without duplicates, in the given order (raises SkillError)."""
    if names is None:
        return None
    names = list(dict.fromkeys(str(name).strip() for name in names))
    known = {row["name"] for row in skills_by_name(names)}
    unknown = [name for name in names if name not in known]
    if unknown:
        raise SkillError(f"Unknown skill(s): {', '.join(unknown)}")
    return names


def agent_skills(names: Optional[list]) -> list[dict]:
    """The enabled skills of an agent's list (personas.skills), in its order."""
    return skills_by_name(names or [], enabled_only=True)


# =========================================================================
# SKILL.md
# =========================================================================

# Leading "---" line, the YAML, a closing "---" line, then the text
_FRONTMATTER = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)(.*)\Z", re.DOTALL)
SKILL_MD_KEYS = ("name", "description")


def parse_skill_md(source: str) -> tuple[dict, list[str]]:
    """
    A SKILL.md file as a skill.

    Returns:
        {"name", "description", "content"} (not validated yet), and the frontmatter keys the app
        doesn't use (license, metadata, allowed-tools, Claude Code's extensions, ...).

    Raises:
        SkillError: No frontmatter, invalid YAML, or not a mapping.
    """
    source = source.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    match = _FRONTMATTER.match(source)
    if not match:
        raise SkillError("A SKILL.md starts with YAML frontmatter between two '---' lines, "
                         "with the skill's name and description")
    try:
        front = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        raise SkillError(f"The frontmatter is not valid YAML: {e}") from e
    if not isinstance(front, dict):
        raise SkillError("The frontmatter must be keys with values, such as name: and description:")
    skill = {
        "name": str(front.get("name") or "").strip(),
        "description": str(front.get("description") or "").strip(),
        "content": match.group(2).strip(),
    }
    return skill, sorted(str(key) for key in front if key not in SKILL_MD_KEYS)


def format_skill_md(skill: dict) -> str:
    """A skill as a SKILL.md file: frontmatter with name and description, then the text."""
    front = yaml.safe_dump({"name": skill["name"], "description": skill["description"]},
                           allow_unicode=True, sort_keys=False, width=4096)
    return f"---\n{front}---\n\n{skill['content'].strip()}\n"


def import_skill_md(source: str, replace: bool = False) -> tuple[dict, bool, list[str]]:
    """
    Create a skill from a SKILL.md file, or with replace change the one of that name (its
    description and text; whether it's enabled stays).

    Returns:
        The skill, whether it was created, and the frontmatter keys left out.

    Raises:
        SkillError: The file is malformed or invalid; SkillConflict: the name is taken without replace.
    """
    fields, ignored = parse_skill_md(source)
    try:
        data = SkillCreate(**fields)
    except ValidationError as e:
        raise SkillError(validation_message(e)) from e
    existing = get_skill_by_name(data.name)
    if existing and not replace:
        raise SkillConflict(f"A skill named '{data.name}' already exists")
    if existing:
        return update_skill(existing["id"], SkillUpdate(description=data.description, content=data.content)), \
            False, ignored
    return create_skill(data), True, ignored
