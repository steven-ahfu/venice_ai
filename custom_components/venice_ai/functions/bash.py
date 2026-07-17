"""Bash function — runs a shell command on the HA host and returns its output.

The `command` is rendered as a Jinja2 template with the LLM-supplied
`arguments` as variables, then executed via `asyncio.create_subprocess_shell`.

Guards (best-effort, NOT a sandbox):
  * Denylist regex blocks obvious self-destructive commands (rm -r/-f
    combinations, mkfs, dd if=, shutdown, reboot, format, world-writable
    chmod, fork bombs).
  * 5 minute timeout; stdout/stderr capped at 10 000 chars each.

The denylist is a tripwire against a hallucinating LLM, not a security
boundary. Pipes, env wrappers, command substitution, or rephrasing will
bypass it — anyone with bash-tool access can do anything the HA process
user can do. Only expose this tool to a trusted setup.

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
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

from .base import Function

_LOGGER = logging.getLogger(__name__)

SHELL_TIMEOUT = 300
SHELL_OUTPUT_LIMIT = 10000
# Denylist is a best-effort tripwire for obvious self-foot-shooting (LLM
# hallucinating `rm -rf /`). It is NOT a sandbox — pipes, env wrappers,
# command substitution, or simply rephrasing trivially defeat it. Treat any
# bash tool as full shell access to the HA host.
SHELL_DENY_PATTERNS = [
    r"\brm\s+(?:-[a-zA-Z]*[rRf][a-zA-Z]*\s+)+",  # rm -rf / -fr / -r -f / --recursive --force
    r"\brm\s+--recursive\b",
    r"\brm\s+--force\b.*\b--recursive\b",
    r"\bformat\b",
    r"\bdd\s+if=",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bmkfs\b",
    r":\(\)\s*\{.*\|.*:",  # fork bomb (more accurate)
    r"\bchmod\s+(?:-R\s+)?0?[67]?7[67]7\b",  # 777, 0777, world-writable
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

        # NOTE: `restrict_to_workspace` is intentionally NOT enforced via a
        # ".." substring check — that gave a false sense of safety without
        # actually preventing escape (e.g. absolute paths, command
        # substitution, env-var expansion, encoded paths all bypass it).
        # The bash tool is full shell access; if you need a sandbox use the
        # file_* tools instead.

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
