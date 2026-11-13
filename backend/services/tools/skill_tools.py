"""
use_skill: the agent loads one of its skills (docs/skills.md).

The agent's prompt lists its skills by name and description (with_skills() in
backend/llm/prompts.py); this tool gives it a skill's text. It only knows the skills
of the agent it was built for (skill_tools() in backend/llm/tools.py binds them), so
an agent can't load a skill an admin didn't give it.
"""
from backend.llm.tools import ToolInputError


def use_skill(name: str, *, skills: dict[str, dict]) -> str:
    """
    The text of one of the agent's skills.

    Args:
        name: The skill's name as the prompt lists it.
        skills: The agent's skills by name ({"name", "description", "content"}); not an
            argument the model sees.

    Returns:
        The skill's instructions, introduced by its name.

    Raises:
        ToolInputError: The agent has no skill of that name.
    """
    skill = skills.get((name or "").strip())
    if skill is None:
        raise ToolInputError(f"You have no skill named {name!r}. Your skills: {', '.join(skills)}.")
    return f"The skill {skill['name']}. Follow these instructions for this task:\n\n{skill['content'].strip()}"
