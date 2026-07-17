"""File read / write / edit executors for Venice AI tools.

All three executors resolve paths inside the `<config>/venice_ai/` workspace
by default. A tool config can opt in to additional directories with
`allow_dir: ["/full/path"]`; any path that resolves outside the allowlist is
rejected with a `ValueError`. Read size is capped at 1 MB.

These are scoped, non-shell alternatives to the `bash` tool — they're safer
than letting the model run shell commands, but they still grant filesystem
access to the LLM, so only expose them when the workspace contents are
appropriate.

Returns `{success, path, ...}` on success or `{error: ...}` on failure.

Example `tools.yaml` — notes that the model can read and append to:

    - name: add_note
      type: write_file
      description: Append a freeform, timestamped note. Use when the user
        says "make a note" or "remember that…".
      parameters:
        type: object
        properties:
          text:
            type: string
            description: The note content.
        required: [text]
      path: "notes.txt"
      content: "{{ now().isoformat() }} — {{ text }}\\n"

    - name: read_notes
      type: read_file
      description: Read back all saved notes.
      path: "notes.txt"

    - name: fix_note_typo
      type: edit_file
      description: Replace a misspelled word inside notes.txt.
      parameters:
        type: object
        properties:
          wrong: {type: string}
          right: {type: string}
        required: [wrong, right]
      path: "notes.txt"
      old_text: "{{ wrong }}"
      new_text: "{{ right }}"
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

from .base import Function

_LOGGER = logging.getLogger(__name__)

FILE_READ_SIZE_LIMIT = 1024 * 1024  # 1 MB
FILE_WRITE_SIZE_LIMIT = 1024 * 1024  # 1 MB


def _resolve_path(hass: HomeAssistant, raw_path: str, allow_dirs: list[str] | None = None) -> Path:
    """Resolve raw_path against the venice_ai workspace (or one of allow_dirs) and verify
    the result is contained inside one of those roots.

    Resolution rules:
      * If raw_path is absolute, it is resolved as-is and must land inside an allowed root.
      * If raw_path is relative, it is joined against each allowed root in order; the first
        join whose resolution stays inside that root wins.
      * Containment is checked with Path.is_relative_to so siblings like
        '/config/venice_ai_attack' are rejected (string-prefix would accept them).
    """
    allowed_roots = [(Path(hass.config.config_dir) / "venice_ai").resolve()]
    if allow_dirs:
        allowed_roots.extend(Path(d).expanduser().resolve() for d in allow_dirs)

    raw = Path(raw_path)
    candidates = [raw.resolve()] if raw.is_absolute() else [(root / raw).resolve() for root in allowed_roots]

    for candidate in candidates:
        if any(candidate == root or candidate.is_relative_to(root) for root in allowed_roots):
            return candidate
    raise ValueError(f"Path '{raw_path}' is outside the allowed workspace")


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
        content_bytes = len(content.encode())
        if content_bytes > FILE_WRITE_SIZE_LIMIT:
            return {"error": f"Content too large ({content_bytes} bytes, limit {FILE_WRITE_SIZE_LIMIT})"}
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
