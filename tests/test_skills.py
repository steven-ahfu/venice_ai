"""Tests for skill discovery and parsing."""

import asyncio
import sys
from types import SimpleNamespace
from types import ModuleType

from custom_components.venice_ai.skills import SkillManager


class _FakeHass:
    def __init__(self, config_dir):
        self.config = SimpleNamespace(config_dir=str(config_dir))

    async def async_add_executor_job(self, func, *args):
        return func(*args)


def test_skills_dir_is_inside_installed_component(tmp_path):
    manager = SkillManager(_FakeHass(tmp_path))

    assert manager.skills_dir == (
        tmp_path / "custom_components" / "venice_ai" / "skills"
    )


def test_loads_skill_from_installed_component_directory(tmp_path, monkeypatch):
    yaml = ModuleType("yaml")
    yaml.safe_load = lambda text: {"description": text.split(":", 1)[1].strip()}
    monkeypatch.setitem(sys.modules, "yaml", yaml)
    skill_path = (
        tmp_path
        / "custom_components"
        / "venice_ai"
        / "skills"
        / "home-assistant"
        / "SKILL.md"
    )
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "---\ndescription: Home Assistant runtime controls.\n---\n\nUse entity services.\n",
        encoding="utf-8",
    )
    manager = SkillManager(_FakeHass(tmp_path))

    count = asyncio.run(manager.async_load_skills())

    assert count == 1
    skill = manager.get_skill("home-assistant")
    assert skill is not None
    assert skill.description == "Home Assistant runtime controls."
    assert skill.content.strip() == "Use entity services."
