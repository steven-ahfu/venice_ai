"""Skills system for Venice AI integration."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

SKILL_FILE_NAME = "SKILL.md"
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class Skill:
    """Represents a single loaded skill."""

    name: str
    description: str
    path: Path
    content: str = field(default="", repr=False)


def _parse_skill_md(text: str, path: Path, skills_dir: Path) -> Skill | None:
    """Parse a SKILL.md file into a Skill object."""
    try:
        import yaml as _yaml
    except ImportError:
        _LOGGER.warning("PyYAML not available; cannot parse skill at %s", path)
        return None

    match = _FRONTMATTER_RE.match(text)
    if not match:
        _LOGGER.warning("Skill at %s is missing YAML frontmatter", path)
        return None

    try:
        meta = _yaml.safe_load(match.group(1))
    except Exception as err:
        _LOGGER.warning("Failed to parse skill frontmatter at %s: %s", path, err)
        return None

    if not isinstance(meta, dict) or "description" not in meta:
        _LOGGER.warning("Skill at %s missing 'description' in frontmatter", path)
        return None

    description = str(meta["description"])[:1024]
    name = str(path.parent.relative_to(skills_dir))
    if len(name) > 64:
        _LOGGER.warning("Skill name too long at %s (max 64 chars)", path)
        return None

    # Body is everything after the closing ---
    body = text[match.end():]

    return Skill(name=name, description=description, path=path, content=body)


class SkillManager:
    """Manages discovery and loading of Venice AI skills."""

    _instance: SkillManager | None = None

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the manager."""
        self._hass = hass
        self._skills: dict[str, Skill] = {}

    @classmethod
    async def async_get_instance(cls, hass: HomeAssistant) -> SkillManager:
        """Return the singleton SkillManager, creating it if needed."""
        if cls._instance is None:
            cls._instance = cls(hass)
            await cls._instance.async_load_skills()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (used in tests or on unload)."""
        cls._instance = None

    @property
    def skills_dir(self) -> Path:
        """Return the path to the skills directory."""
        return (
            Path(self._hass.config.config_dir)
            / "custom_components"
            / "venice_ai"
            / "skills"
        )

    async def async_load_skills(self) -> int:
        """Scan skills_dir, parse all SKILL.md files, return count loaded."""
        skills_dir = self.skills_dir
        if not await self._hass.async_add_executor_job(skills_dir.is_dir):
            _LOGGER.debug("Skills directory does not exist: %s", skills_dir)
            self._skills = {}
            return 0

        pairs: list[tuple[Path, str]] = await self._hass.async_add_executor_job(
            self._scan_skills_dir, skills_dir
        )

        new_skills: dict[str, Skill] = {}
        for path, text in pairs:
            skill = _parse_skill_md(text, path, skills_dir)
            if skill is not None:
                new_skills[skill.name] = skill
                _LOGGER.debug("Loaded skill '%s' from %s", skill.name, path)

        self._skills = new_skills
        _LOGGER.info("Loaded %d skill(s) from %s", len(new_skills), skills_dir)
        return len(new_skills)

    def _scan_skills_dir(self, skills_dir: Path) -> list[tuple[Path, str]]:
        """Synchronous: walk skills_dir and read all SKILL.md files."""
        results = []
        for skill_path in skills_dir.rglob(SKILL_FILE_NAME):
            try:
                text = skill_path.read_text(encoding="utf-8")
                results.append((skill_path, text))
            except OSError as err:
                _LOGGER.warning("Could not read %s: %s", skill_path, err)
        return results

    def get_all_skills(self) -> list[Skill]:
        """Return all loaded skills."""
        return list(self._skills.values())

    def get_skill(self, name: str) -> Skill | None:
        """Return skill by name or None."""
        return self._skills.get(name)

    def get_enabled_skills(self, enabled_names: list[str]) -> list[Skill]:
        """Return loaded skills whose names are in enabled_names."""
        return [s for s in self._skills.values() if s.name in enabled_names]
