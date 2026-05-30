"""Abstract base class for Venice AI custom function executors.

A `Function` is the Python implementation behind a `type:` value in
`default_tools.yaml` or a user's `<config>/venice_ai/tools.yaml`. Subclasses
register themselves in `functions/__init__.py:FUNCTIONS` keyed by
`function_type`, and `ToolManager` calls `validate_schema()` at load time
and `execute()` per tool call.

Lifecycle for one tool call:

    1. The model picks a tool by name; ToolManager looks up the Tool's
       `type` and resolves it to a Function instance via `get_function()`.
    2. `Function.execute()` runs with the LLM-supplied `arguments` and a
       snapshot of `exposed_entities` (HA's allowlist of entities the user
       has exposed to LLMs).
    3. The return value (anything JSON-serialisable) is fed back to the
       model as the tool result.

Subclasses MUST:
  * Set `function_type` to the YAML `type:` string (e.g. "rest", "bash").
  * Implement `async execute(...)`.

Subclasses SHOULD:
  * Extend `validate_schema()` to assert required fields and reject bad
    configs early — raising `InvalidFunction` causes the tool to be
    skipped at load time instead of failing per call.
  * Return `{"error": "..."}` for recoverable failures so the model can
    react, and raise for programmer errors.

See `bash.py`, `web.py`, `template.py`, etc. for concrete examples.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from homeassistant.core import HomeAssistant

from ..exceptions import InvalidFunction


class Function(ABC):
    """Abstract base for all custom function types."""

    @property
    @abstractmethod
    def function_type(self) -> str:
        """Return the type string used in YAML config."""

    def validate_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        """Validate a function config dict. Override to add schema validation.

        Raises InvalidFunction on failure.
        """
        if "name" not in config:
            raise InvalidFunction(str(config.get("name", "unknown")), "missing 'name' field")
        if config.get("type") != self.function_type:
            raise InvalidFunction(
                str(config.get("name", "unknown")),
                f"type mismatch: expected '{self.function_type}', got '{config.get('type')}'",
            )
        return config

    @abstractmethod
    async def execute(
        self,
        hass: HomeAssistant,
        function_config: dict[str, Any],
        arguments: dict[str, Any],
        llm_context: Any,
        exposed_entities: list[dict[str, Any]],
    ) -> Any:
        """Execute the function and return a result."""
