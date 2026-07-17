"""Native executor — talks to Home Assistant directly (services + recorder).

Dispatches on `operation`:
  * `execute_service`  — calls `hass.services.async_call(domain, service,
                         service_data, blocking=True)`. Enforces the exposed-
                         entity allowlist on every `entity_id` (flat or under
                         `target`, string or list): unknown entities raise
                         `EntityNotFound`, non-exposed ones raise
                         `EntityNotExposed`. Broad targeting by
                         `area_id`/`device_id`/`label_id` is rejected because
                         it cannot be checked against the allowlist.
  * `get_history`      — queries the recorder for state changes of
                         `entity_ids` between `start_time` and `end_time`
                         (ISO 8601). Defaults to the last 24h.
  * `get_statistics`   — not yet implemented.
  * `add_automation`   — not yet implemented.

`execute_service` is the workhorse — most "do X" tools should use it rather
than `script` or `bash`, because it routes through HA's normal service stack
and respects HA's exposure rules.

Example `tools.yaml` — let the LLM call any HA service safely:

    - name: execute_service
      type: native
      operation: execute_service
      description: Call a Home Assistant service on an exposed entity.
        Use this to turn things on/off, set brightness, play media, etc.
      parameters:
        type: object
        properties:
          domain:
            type: string
            description: The HA domain (light, switch, media_player, …).
          service:
            type: string
            description: The service name (turn_on, turn_off, …).
          service_data:
            type: object
            description: Service data, e.g. {"entity_id": "light.kitchen",
              "brightness_pct": 40}.
        required: [domain, service, service_data]

    - name: thermostat_history
      type: native
      operation: get_history
      description: Get recent thermostat readings.
      parameters:
        type: object
        properties:
          entity_ids:
            type: array
            items: {type: string}
          start_time:
            type: string
            description: ISO 8601 timestamp; defaults to 24h ago.
        required: [entity_ids]
"""
from __future__ import annotations

import datetime
import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .base import Function
from ..exceptions import CallServiceError, EntityNotFound, EntityNotExposed

_LOGGER = logging.getLogger(__name__)

_OPERATIONS = {
    "execute_service",
    "get_history",
    "get_statistics",
    "add_automation",
    "alarm_clock_set_timer",
    "alarm_clock_set_alarm",
    "alarm_clock_list",
    "alarm_clock_cancel",
    "alarm_clock_snooze",
    "alarm_clock_stop",
}

ALARM_CLOCK_DOMAIN = "ha_alarm_clock"

_DURATION_RE = re.compile(
    r"(\d+)\s*(h(?:our|ours|rs?)?|m(?:in|inute|inutes)?|s(?:ec|econd|econds)?)",
    re.IGNORECASE,
)


def _parse_duration_to_seconds(text: str) -> int:
    """Parse a human duration ("5 minutes", "1h30m", "00:05:00", "90s") to seconds.

    Returns 0 if nothing parseable is found; the caller surfaces that as an error.
    """
    if not text:
        return 0
    text = text.strip()
    if ":" in text and _DURATION_RE.search(text) is None:
        parts = text.split(":")
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            return 0
        if len(nums) == 3:
            return nums[0] * 3600 + nums[1] * 60 + nums[2]
        if len(nums) == 2:
            return nums[0] * 60 + nums[1]
        return 0
    total = 0
    for n, unit in _DURATION_RE.findall(text):
        n = int(n)
        u = unit.lower()[0]
        if u == "h":
            total += n * 3600
        elif u == "s":
            total += n
        else:
            total += n * 60
    return total


def _parse_clock_time(text: str, date_hint: str | None = None) -> tuple[str, str]:
    """Parse a clock-time string into (HH:MM, YYYY-MM-DD).

    Accepts "07:30", "7:30 AM", "7:30PM", "18:00", and ISO 8601 timestamps.
    If date_hint is provided it is used as-is; otherwise picks today if the
    time is still in the future, else tomorrow.
    """
    if not text:
        raise ValueError("time is required")
    s = text.strip()
    if "T" in s and len(s) >= 16:
        dt = datetime.datetime.fromisoformat(s)
        return dt.strftime("%H:%M"), dt.strftime("%Y-%m-%d")

    upper = s.upper()
    is_pm = "PM" in upper
    is_am = "AM" in upper
    clean = upper.replace("AM", "").replace("PM", "").strip()
    if ":" in clean:
        h_str, m_str = clean.split(":", 1)
        h = int(h_str)
        m = int(m_str)
    else:
        h = int(clean)
        m = 0
    if is_pm and h < 12:
        h += 12
    if is_am and h == 12:
        h = 0
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"invalid clock time: {text}")

    hhmm = f"{h:02d}:{m:02d}"
    if date_hint:
        return hhmm, date_hint
    now = datetime.datetime.now()
    candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if candidate <= now:
        candidate += datetime.timedelta(days=1)
    return hhmm, candidate.strftime("%Y-%m-%d")


class NativeFunction(Function):
    """Calls Home Assistant services or retrieves HA data."""

    @property
    def function_type(self) -> str:
        return "native"

    def validate_schema(self, config: dict[str, Any]) -> dict[str, Any]:
        config = super().validate_schema(config)
        op = config.get("operation")
        if op and op not in _OPERATIONS:
            from ..exceptions import InvalidFunction
            raise InvalidFunction(config["name"], f"unknown operation '{op}'")
        return config

    async def execute(
        self,
        hass: HomeAssistant,
        function_config: dict[str, Any],
        arguments: dict[str, Any],
        llm_context: Any,
        exposed_entities: list[dict[str, Any]],
    ) -> Any:
        operation = function_config.get("operation", "execute_service")

        if operation == "execute_service":
            return await self._execute_service(hass, arguments, exposed_entities)
        if operation == "get_history":
            return await self._get_history(hass, arguments)
        if operation == "get_statistics":
            return await self._get_statistics(hass, arguments)
        if operation == "add_automation":
            return await self._add_automation(hass, arguments)
        if operation == "alarm_clock_set_timer":
            return await self._alarm_clock_set_timer(hass, arguments)
        if operation == "alarm_clock_set_alarm":
            return await self._alarm_clock_set_alarm(hass, arguments)
        if operation == "alarm_clock_list":
            return self._alarm_clock_list(hass)
        if operation == "alarm_clock_cancel":
            return await self._alarm_clock_cancel(hass, arguments)
        if operation == "alarm_clock_snooze":
            return await self._alarm_clock_snooze(hass, arguments)
        if operation == "alarm_clock_stop":
            return await self._alarm_clock_stop(hass)
        return {"error": f"Unknown operation: {operation}"}

    async def _execute_service(
        self,
        hass: HomeAssistant,
        arguments: dict[str, Any],
        exposed_entities: list[dict[str, Any]],
    ) -> Any:
        domain = arguments.get("domain")
        service = arguments.get("service")
        service_data = arguments.get("service_data", {})

        if not domain or not service:
            return {"error": "domain and service are required"}
        if not isinstance(service_data, dict):
            return {"error": "service_data must be an object"}

        # The exposure allowlist is the only access-control boundary on this
        # tool. It can only be enforced against explicit entity_ids, so reject
        # area/device/label/target targeting outright — otherwise the model (or
        # a prompt-injection payload) could act on non-exposed entities by
        # naming an area or device instead of an entity. Collect entity_id
        # from both the flat and nested (`target`) forms and validate each one.
        target = service_data.get("target")
        broad_keys = {"area_id", "device_id", "label_id"}
        used_broad = broad_keys & set(service_data)
        if isinstance(target, dict):
            used_broad |= broad_keys & set(target)
        if used_broad:
            return {
                "error": (
                    "Targeting by "
                    + ", ".join(sorted(used_broad))
                    + " is not allowed; specify an explicit entity_id for an "
                    "exposed entity instead."
                )
            }

        raw_ids: list[str] = []
        for source in (service_data.get("entity_id"), (target or {}).get("entity_id")):
            if isinstance(source, str):
                raw_ids.append(source)
            elif isinstance(source, list):
                raw_ids.extend(str(i) for i in source)

        if raw_ids:
            exposed_ids = {e["entity_id"] for e in exposed_entities}
            known_ids = set(hass.states.async_entity_ids())
            for eid in raw_ids:
                if eid not in known_ids:
                    raise EntityNotFound(eid)
                if eid not in exposed_ids:
                    raise EntityNotExposed(eid)

        try:
            await hass.services.async_call(
                domain, service, service_data, blocking=True
            )
            return {"success": True}
        except Exception as err:
            raise CallServiceError(domain, service, str(err)) from err

    async def _get_history(self, hass: HomeAssistant, arguments: dict[str, Any]) -> Any:
        try:
            from homeassistant.components import recorder
            entity_ids = arguments.get("entity_ids", [])
            if isinstance(entity_ids, str):
                entity_ids = [entity_ids]
            start_time = arguments.get("start_time")
            end_time = arguments.get("end_time")
            import datetime
            start = datetime.datetime.fromisoformat(start_time) if start_time else (
                datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
            )
            end = datetime.datetime.fromisoformat(end_time) if end_time else None
            history = await recorder.get_instance(hass).async_add_executor_job(
                lambda: recorder.history.get_significant_states(hass, start, end, entity_ids)
            )
            result = {}
            for eid, states in history.items():
                result[eid] = [{"state": s.state, "last_changed": s.last_changed.isoformat()} for s in states]
            return result
        except Exception as err:
            _LOGGER.warning("get_history failed: %s", err)
            return {"error": str(err)}

    async def _get_statistics(self, hass: HomeAssistant, arguments: dict[str, Any]) -> Any:
        return {"error": "get_statistics not yet implemented"}

    async def _add_automation(self, hass: HomeAssistant, arguments: dict[str, Any]) -> Any:
        return {"error": "add_automation not yet implemented"}

    # ── ha_alarm_clock wrappers ────────────────────────────────────────────
    # The HACS integration `nirnachmani/HA-Alarm-Clock` accepts only absolute
    # HH:MM + YYYY-MM-DD, so we parse "in N minutes" / "at 7:30 AM" here and
    # forward to its services. Each helper returns a clear error if the
    # integration isn't installed instead of letting HA's "Service not found"
    # surface raw.

    def _has_alarm_clock(self, hass: HomeAssistant) -> bool:
        return hass.services.has_service(ALARM_CLOCK_DOMAIN, "set_alarm")

    def _missing_integration_error(self) -> dict[str, Any]:
        return {
            "error": (
                "Timers and alarms require the HACS integration "
                "'nirnachmani/HA-Alarm-Clock'. Tell the user to install it from "
                "HACS (Custom repositories → "
                "https://github.com/nirnachmani/HA-Alarm-Clock, category Integration)."
            )
        }

    async def _alarm_clock_set_timer(
        self, hass: HomeAssistant, arguments: dict[str, Any]
    ) -> Any:
        if not self._has_alarm_clock(hass):
            return self._missing_integration_error()
        duration = arguments.get("duration", "")
        name = arguments.get("name")
        if not name:
            return {"error": "name is required"}
        seconds = _parse_duration_to_seconds(duration)
        if seconds <= 0:
            return {"error": f"Could not parse duration: {duration!r}"}
        fires_at = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
        service_data: dict[str, Any] = {
            "time": fires_at.strftime("%H:%M"),
            "date": fires_at.strftime("%Y-%m-%d"),
            "name": name,
            "repeat": "once",
        }
        if arguments.get("media_player"):
            service_data["media_player"] = arguments["media_player"]
        try:
            await hass.services.async_call(
                ALARM_CLOCK_DOMAIN, "set_alarm", service_data, blocking=True
            )
        except Exception as err:
            raise CallServiceError(ALARM_CLOCK_DOMAIN, "set_alarm", str(err)) from err
        return {
            "success": True,
            "name": name,
            "fires_at": fires_at.isoformat(timespec="seconds"),
            "duration_seconds": seconds,
        }

    async def _alarm_clock_set_alarm(
        self, hass: HomeAssistant, arguments: dict[str, Any]
    ) -> Any:
        if not self._has_alarm_clock(hass):
            return self._missing_integration_error()
        time_str = arguments.get("time", "")
        name = arguments.get("name")
        if not name:
            return {"error": "name is required"}
        try:
            hhmm, ymd = _parse_clock_time(time_str, arguments.get("date"))
        except ValueError as err:
            return {"error": str(err)}
        service_data: dict[str, Any] = {
            "time": hhmm,
            "date": ymd,
            "name": name,
            "repeat": arguments.get("repeat", "once"),
        }
        if arguments.get("media_player"):
            service_data["media_player"] = arguments["media_player"]
        try:
            await hass.services.async_call(
                ALARM_CLOCK_DOMAIN, "set_alarm", service_data, blocking=True
            )
        except Exception as err:
            raise CallServiceError(ALARM_CLOCK_DOMAIN, "set_alarm", str(err)) from err
        return {"success": True, "name": name, "fires_at": f"{ymd}T{hhmm}"}

    def _alarm_clock_list(self, hass: HomeAssistant) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for state in hass.states.async_all():
            eid = state.entity_id
            if not (eid.startswith("switch.ha_alarm_clock_alarm_") or
                    eid.startswith("switch.ha_alarm_clock_reminder_")):
                continue
            attrs = state.attributes or {}
            items.append({
                "name": attrs.get("friendly_name") or eid,
                "entity_id": eid,
                "fires_at": attrs.get("next_fire_time") or attrs.get("time"),
                "enabled": state.state == "on",
                "kind": "alarm" if "alarm" in eid else "reminder",
            })
        if not items:
            return {"items": [], "note": "No active timers or alarms."}
        return {"items": items}

    async def _alarm_clock_cancel(
        self, hass: HomeAssistant, arguments: dict[str, Any]
    ) -> Any:
        if not self._has_alarm_clock(hass):
            return self._missing_integration_error()
        if arguments.get("all"):
            try:
                await hass.services.async_call(
                    ALARM_CLOCK_DOMAIN, "delete_all", {}, blocking=True
                )
            except Exception as err:
                raise CallServiceError(ALARM_CLOCK_DOMAIN, "delete_all", str(err)) from err
            return {"success": True, "deleted_all": True}
        name = arguments.get("name")
        if not name:
            return {"error": "Pass name (partial match) or all=true"}
        try:
            await hass.services.async_call(
                ALARM_CLOCK_DOMAIN, "delete_alarm", {"name": name}, blocking=True
            )
        except Exception as err:
            raise CallServiceError(ALARM_CLOCK_DOMAIN, "delete_alarm", str(err)) from err
        return {"success": True, "cancelled": name}

    async def _alarm_clock_snooze(
        self, hass: HomeAssistant, arguments: dict[str, Any]
    ) -> Any:
        if not self._has_alarm_clock(hass):
            return self._missing_integration_error()
        minutes = int(arguments.get("minutes", 5))
        try:
            await hass.services.async_call(
                ALARM_CLOCK_DOMAIN, "snooze", {"minutes": minutes}, blocking=True
            )
        except Exception as err:
            raise CallServiceError(ALARM_CLOCK_DOMAIN, "snooze", str(err)) from err
        return {"success": True, "snoozed_minutes": minutes}

    async def _alarm_clock_stop(self, hass: HomeAssistant) -> Any:
        if not self._has_alarm_clock(hass):
            return self._missing_integration_error()
        try:
            await hass.services.async_call(
                ALARM_CLOCK_DOMAIN, "stop_all", {}, blocking=True
            )
        except Exception as err:
            raise CallServiceError(ALARM_CLOCK_DOMAIN, "stop_all", str(err)) from err
        return {"success": True, "stopped": True}
