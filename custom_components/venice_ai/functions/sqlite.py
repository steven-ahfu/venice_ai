"""SQLite executor — runs a read-only query against a SQLite database.

If `db_url` is not provided, defaults to the Home Assistant recorder DB. The
connection is opened with `?mode=ro` so the query cannot mutate state, but
queries are otherwise unrestricted — assume the model can read anything in
the DB it points at.

`query` is a Jinja2 template rendered with the LLM-supplied arguments.
**Build queries with parameter binding where possible**: blindly interpolating
LLM output into SQL is an injection vector even when the connection is
read-only (it can still exfiltrate data via crafted joins).

Set `single: true` to return only the first row as a dict instead of a list.

Returns a list of row-dicts, or `{error: ...}` on failure.

Example `tools.yaml` — daily summary of door-sensor events from the recorder:

    - name: door_events_today
      type: sqlite
      description: Count how many times each door sensor changed state today.
      parameters:
        type: object
        properties: {}
      query: >-
        SELECT meta.entity_id, COUNT(*) AS changes
        FROM states
        JOIN states_meta meta ON meta.metadata_id = states.metadata_id
        WHERE meta.entity_id LIKE 'binary_sensor.%door%'
          AND last_updated_ts >= strftime('%s', date('now'))
        GROUP BY meta.entity_id
        ORDER BY changes DESC;
"""
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
