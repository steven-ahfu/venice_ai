"""Tools system for Venice AI integration.

Loads tool definitions from two sources:

  1. A YAML file bundled inside the integration (``default_tools.yaml``)
     so the integration ships with a usable set out of the box.
  2. An optional user file at ``<config>/venice_ai/tools.yaml`` which can
     add new tools or override bundled ones (same `name` wins).

The result is exposed via a singleton ToolManager that mirrors the
SkillManager pattern: ``await ToolManager.async_get_instance(hass)``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .functions import get_function
from .exceptions import FunctionNotFound, InvalidFunction

_LOGGER = logging.getLogger(__name__)

USER_TOOLS_FILENAME = "tools.yaml"
DEFAULT_TOOLS_FILENAME = "default_tools.yaml"


@dataclass
class Tool:
    """A single loaded tool definition (validated)."""

    name: str
    type: str
    description: str
    source: str
    config: dict[str, Any] = field(repr=False, default_factory=dict)


class ToolManager:
    """Discovers and loads Venice AI tool definitions."""

    _instance: ToolManager | None = None

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._tools: dict[str, Tool] = {}

    @classmethod
    async def async_get_instance(cls, hass: HomeAssistant) -> ToolManager:
        if cls._instance is None:
            cls._instance = cls(hass)
            await cls._instance.async_load_tools()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    @property
    def user_tools_path(self) -> Path:
        return Path(self._hass.config.config_dir) / "venice_ai" / USER_TOOLS_FILENAME

    @property
    def bundled_tools_path(self) -> Path:
        return Path(__file__).parent / DEFAULT_TOOLS_FILENAME

    async def async_load_tools(self) -> int:
        """Reload tools from bundled defaults + user file. Returns total loaded."""
        bundled_raw = await self._hass.async_add_executor_job(
            self._read_yaml_file, self.bundled_tools_path
        )
        user_raw = await self._hass.async_add_executor_job(
            self._read_yaml_file, self.user_tools_path
        )

        tools: dict[str, Tool] = {}
        for entry in bundled_raw:
            tool = self._validate(entry, source="bundled")
            if tool is not None:
                tools[tool.name] = tool
        for entry in user_raw:
            tool = self._validate(entry, source=str(self.user_tools_path))
            if tool is not None:
                tools[tool.name] = tool

        self._tools = tools
        _LOGGER.info(
            "Loaded %d Venice AI tool(s) (bundled=%d, user=%d at %s)",
            len(tools),
            len(bundled_raw),
            len(user_raw),
            self.user_tools_path,
        )
        return len(tools)

    def _read_yaml_file(self, path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        try:
            import yaml as _yaml
        except ImportError:
            _LOGGER.warning("PyYAML not available; cannot read %s", path)
            return []
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as err:
            _LOGGER.warning("Could not read %s: %s", path, err)
            return []
        try:
            parsed = _yaml.safe_load(text)
        except Exception as err:
            _LOGGER.error("Failed to parse tools YAML at %s: %s", path, err)
            return []
        if parsed is None:
            return []
        if isinstance(parsed, dict):
            return [parsed]
        if isinstance(parsed, list):
            return [e for e in parsed if isinstance(e, dict)]
        _LOGGER.warning("Tools YAML at %s has unexpected top-level type %s", path, type(parsed).__name__)
        return []

    def _validate(self, entry: dict[str, Any], source: str) -> Tool | None:
        name = entry.get("name")
        ftype = entry.get("type")
        if not name or not ftype:
            _LOGGER.warning("Skipping tool with missing name/type in %s: %r", source, entry)
            return None
        try:
            fn = get_function(ftype)
            fn.validate_schema(entry)
        except FunctionNotFound:
            _LOGGER.warning("Skipping tool '%s' in %s: unknown type '%s'", name, source, ftype)
            return None
        except InvalidFunction as err:
            _LOGGER.warning("Skipping invalid tool '%s' in %s: %s", name, source, err)
            return None
        except Exception as err:
            _LOGGER.warning("Skipping tool '%s' in %s: %s", name, source, err)
            return None
        return Tool(
            name=str(name),
            type=str(ftype),
            description=str(entry.get("description", "")),
            source=source,
            config=entry,
        )

    def get_all_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)
