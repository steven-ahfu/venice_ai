"""SQLite function — queries the HA recorder database."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

from .base import Function

_LOGGER = logging.getLogger(__name__)


class SqliteFunction(Function):
    """Executes a SQLite query against the HA recorder database."""

    @property
    def function_type(self) -> str:
        return "sqlite"

    def validate_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        config = super().validate_schema(config)
        if "query" not in config:
            from ..exceptions import InvalidFunction
            raise InvalidFunction(config["name"], "missing 'query'")
        return config

    async def execute(
        self,
        hass: HomeAssistant,
        function_config: dict[str, Any],
        arguments: dict[str, Any],
        llm_context: Any,
        exposed_entities: list[dict[str, Any]],
    ) -> Any:
        query_tpl = function_config["query"]
        query = Template(query_tpl, hass).async_render(arguments, parse_result=False)
        single = function_config.get("single", False)

        db_url = function_config.get("db_url")
        if not db_url:
            try:
                from homeassistant.components.recorder import get_instance
                instance = get_instance(hass)
                db_url = instance.db_url
            except Exception:
                return {"error": "Could not determine recorder database URL"}

        try:
            import sqlite3
            def _run_query() -> list[dict[str, Any]]:
                conn = sqlite3.connect(f"file:{db_url.replace('sqlite:///', '')}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                try:
                    cursor = conn.execute(query)
                    rows = [dict(row) for row in cursor.fetchall()]
                    return rows
                finally:
                    conn.close()

            rows = await hass.async_add_executor_job(_run_query)
            if single:
                return rows[0] if rows else {}
            return rows
        except Exception as err:
            _LOGGER.warning("sqlite function failed: %s", err)
            return {"error": str(err)}
