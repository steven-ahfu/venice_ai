"""File read/write/edit functions for Venice AI."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

from .base import Function

_LOGGER = logging.getLogger(__name__)

FILE_READ_SIZE_LIMIT = 1024 * 1024  # 1 MB


def _resolve_path(hass: HomeAssistant, raw_path: str, allow_dirs: list[str] | None = None) -> Path:
    """Resolve path relative to config dir workspace. Raises ValueError if outside allowed dirs."""
    workspace = Path(hass.config.config_dir) / "venice_ai"
    allowed = [workspace]
    if allow_dirs:
        for d in allow_dirs:
            allowed.append(Path(d).expanduser())

    resolved = (workspace / raw_path).resolve()
    if not any(str(resolved).startswith(str(a.resolve())) for a in allowed):
        raise ValueError(f"Path '{resolved}' is outside the allowed workspace")
    return resolved


class ReadFileFunction(Function):
    """Reads a file from the venice_ai workspace."""

    @property
    def function_type(self) -> str:
        return "read_file"

    def validate_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        config = super().validate_schema(config)
        if "path" not in config:
            from ..exceptions import InvalidFunction
            raise InvalidFunction(config["name"], "missing 'path'")
        return config

    async def execute(
        self,
        hass: HomeAssistant,
        function_config: dict[str, Any],
        arguments: dict[str, Any],
        llm_context: Any,
        exposed_entities: list[dict[str, Any]],
    ) -> Any:
        raw_path = Template(function_config["path"], hass).async_render(arguments, parse_result=False)
        allow_dirs = function_config.get("allow_dir")
        try:
            path = _resolve_path(hass, raw_path, allow_dirs)
            if not path.is_file():
                return {"error": f"File not found: {raw_path}"}
            size = path.stat().st_size
            if size > FILE_READ_SIZE_LIMIT:
                return {"error": f"File too large ({size} bytes, limit {FILE_READ_SIZE_LIMIT})"}
            content = await hass.async_add_executor_job(path.read_text, "utf-8")
            return {"content": content, "size": size}
        except ValueError as err:
            return {"error": str(err)}
        except Exception as err:
            _LOGGER.warning("read_file failed: %s", err)
            return {"error": str(err)}


class WriteFileFunction(Function):
    """Writes content to a file in the venice_ai workspace."""

    @property
    def function_type(self) -> str:
        return "write_file"

    def validate_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        config = super().validate_schema(config)
        for field in ("path", "content"):
            if field not in config:
                from ..exceptions import InvalidFunction
                raise InvalidFunction(config["name"], f"missing '{field}'")
        return config

    async def execute(
        self,
        hass: HomeAssistant,
        function_config: dict[str, Any],
        arguments: dict[str, Any],
        llm_context: Any,
        exposed_entities: list[dict[str, Any]],
    ) -> Any:
        raw_path = Template(function_config["path"], hass).async_render(arguments, parse_result=False)
        content = Template(function_config["content"], hass).async_render(arguments, parse_result=False)
        allow_dirs = function_config.get("allow_dir")
        try:
            path = _resolve_path(hass, raw_path, allow_dirs)
            path.parent.mkdir(parents=True, exist_ok=True)
            await hass.async_add_executor_job(path.write_text, content, "utf-8")
            return {"success": True, "path": str(path), "bytes_written": len(content.encode())}
        except ValueError as err:
            return {"error": str(err)}
        except Exception as err:
            _LOGGER.warning("write_file failed: %s", err)
            return {"error": str(err)}


class EditFileFunction(Function):
    """Replaces text in a file in the venice_ai workspace."""

    @property
    def function_type(self) -> str:
        return "edit_file"

    def validate_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        config = super().validate_schema(config)
        for field in ("path", "old_text", "new_text"):
            if field not in config:
                from ..exceptions import InvalidFunction
                raise InvalidFunction(config["name"], f"missing '{field}'")
        return config

    async def execute(
        self,
        hass: HomeAssistant,
        function_config: dict[str, Any],
        arguments: dict[str, Any],
        llm_context: Any,
        exposed_entities: list[dict[str, Any]],
    ) -> Any:
        raw_path = Template(function_config["path"], hass).async_render(arguments, parse_result=False)
        old_text = Template(function_config["old_text"], hass).async_render(arguments, parse_result=False)
        new_text = Template(function_config["new_text"], hass).async_render(arguments, parse_result=False)
        allow_dirs = function_config.get("allow_dir")
        try:
            path = _resolve_path(hass, raw_path, allow_dirs)
            if not path.is_file():
                return {"error": f"File not found: {raw_path}"}
            content = await hass.async_add_executor_job(path.read_text, "utf-8")
            count = content.count(old_text)
            if count == 0:
                return {"error": "old_text not found in file"}
            new_content = content.replace(old_text, new_text)
            await hass.async_add_executor_job(path.write_text, new_content, "utf-8")
            return {"success": True, "path": str(path), "replacements": count}
        except ValueError as err:
            return {"error": str(err)}
        except Exception as err:
            _LOGGER.warning("edit_file failed: %s", err)
            return {"error": str(err)}
