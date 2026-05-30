"""Bash function — runs a shell command on the HA host and returns its output.

The `command` is rendered as a Jinja2 template with the LLM-supplied
`arguments` as variables, then executed via `asyncio.create_subprocess_shell`.

Guards:
  * Denylist regex blocks `rm -rf`, `mkfs`, `dd`, `shutdown`, `reboot`,
    `format`, `chmod 777`, and shell fork bombs.
  * 5 minute timeout; stdout/stderr capped at 10 000 chars each.
  * If `restrict_to_workspace: true` (default) and `cwd` is set, `..` in the
    rendered command is rejected to discourage path traversal.

The denylist is intentionally narrow — this tool is still dangerous and
should only be exposed to trusted users.

Returns `{exit_code, stdout, stderr}` on success, `{error: ...}` on failure.

Example `tools.yaml` — append a timestamped note to a file:

    - name: append_note
      type: bash
      description: Append a freeform timestamped note to ~/notes.txt.
      parameters:
        type: object
        properties:
          text:
            type: string
            description: The note content.
        required: [text]
      command: 'echo "$(date -Iseconds) — {{ text }}" >> notes.txt'
      cwd: "{{ config_dir }}/venice_ai"
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

from .base import Function

_LOGGER = logging.getLogger(__name__)

SHELL_TIMEOUT = 300
SHELL_OUTPUT_LIMIT = 10000
SHELL_DENY_PATTERNS = [
    r"\brm\s+-[rRf]",
    r"\bformat\b",
    r"\bdd\s+if=",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bmkfs\b",
    r":\(\)\{.*\}",  # fork bomb
    r"\bchmod\s+777\b",
]


def _is_command_denied(command: str) -> bool:
    return any(re.search(p, command) for p in SHELL_DENY_PATTERNS)


class BashFunction(Function):
    """Executes shell commands with security restrictions."""

    @property
    def function_type(self) -> str:
        return "bash"

    def validate_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        config = super().validate_schema(config)
        if "command" not in config:
            from ..exceptions import InvalidFunction
            raise InvalidFunction(config["name"], "missing 'command'")
        return config

    async def execute(
        self,
        hass: HomeAssistant,
        function_config: dict[str, Any],
        arguments: dict[str, Any],
        llm_context: Any,
        exposed_entities: list[dict[str, Any]],
    ) -> Any:
        command_tpl = function_config["command"]
        command = Template(command_tpl, hass).async_render(arguments, parse_result=False)

        if _is_command_denied(command):
            return {"error": "Command blocked by security policy"}

        cwd_tpl = function_config.get("cwd")
        cwd = None
        if cwd_tpl:
            cwd = Template(cwd_tpl, hass).async_render(arguments, parse_result=False)

        restrict = function_config.get("restrict_to_workspace", True)
        if restrict and cwd and ".." in command:
            return {"error": "Path traversal detected in command"}

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=SHELL_TIMEOUT)
            except asyncio.TimeoutError:
                proc.kill()
                return {"error": f"Command timed out after {SHELL_TIMEOUT}s"}

            return {
                "exit_code": proc.returncode,
                "stdout": stdout.decode(errors="replace")[:SHELL_OUTPUT_LIMIT],
                "stderr": stderr.decode(errors="replace")[:SHELL_OUTPUT_LIMIT],
            }
        except Exception as err:
            _LOGGER.warning("Bash function failed: %s", err)
            return {"error": str(err)}
