"""AI Task integration for Venice AI."""

from __future__ import annotations

import asyncio
import json
import logging

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import AsyncVeniceAIClient, VeniceAIError
from .const import (
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_TEMPERATURE,
    DOMAIN,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_TEMPERATURE,
)

_LOGGER = logging.getLogger(__name__)

try:
    from homeassistant.components import ai_task
    _HAS_AI_TASK = True
except ImportError:
    ai_task = None  # type: ignore[assignment]
    _HAS_AI_TASK = False


def _structure_to_json_schema(structure) -> dict | None:
    """Best-effort conversion of a task ``structure`` to a JSON Schema dict.

    ``GenDataTask.structure`` is a voluptuous schema. We reuse
    ``voluptuous_openapi.convert`` (already a dependency path in this
    integration) when available; if the dep is missing or conversion fails,
    return ``None`` so the caller falls back to a plain JSON instruction.
    """
    if structure is None:
        return None
    try:
        from voluptuous_openapi import convert

        return convert(structure)
    except Exception as err:  # pragma: no cover - defensive
        _LOGGER.debug("Could not convert task structure to JSON schema: %s", err)
        return None


def _extract_json(text: str) -> str:
    """Strip common markdown code fences so json.loads succeeds on fenced JSON."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # Drop the opening fence line (``` or ```json) and the closing fence.
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AI Task entities."""
    if not _HAS_AI_TASK:
        _LOGGER.warning(
            "AI Task platform is not available in this Home Assistant version"
        )
        return
    _LOGGER.info("Setting up AI Task entities for entry %s", entry.entry_id)
    from . import VeniceAIRuntimeData

    runtime_data: VeniceAIRuntimeData = entry.runtime_data
    if not runtime_data or not runtime_data.client:
        _LOGGER.error(
            "Venice AI client not available in runtime_data for entry %s",
            entry.entry_id,
        )
        return
    entity = VeniceAITaskEntity(entry)
    _LOGGER.info("Created VeniceAITaskEntity: %s", entity.unique_id)
    # Store entity reference in runtime_data so the service handler can find it
    # without using hass.data (Architecture 7.1 fix)
    runtime_data.ai_task_entity = entity
    async_add_entities([entity])
    _LOGGER.info("Added VeniceAITaskEntity to Home Assistant")


if not _HAS_AI_TASK:
    # Define a dummy class so the module is import-safe when ai_task is unavailable
    class _DummyAITaskEntity:
        """Placeholder when ai_task is unavailable."""

    VeniceAITaskEntity = _DummyAITaskEntity  # type: ignore[misc,assignment]
else:

    class VeniceAITaskEntity(ai_task.AITaskEntity):
        """Venice AI AI Task entity."""

        _attr_has_entity_name = True
        _attr_name = "AI Task"

        def __init__(self, entry: ConfigEntry) -> None:
            """Initialize the entity."""
            super().__init__()
            self.entry = entry
            self._attr_unique_id = f"{entry.entry_id}_task"
            self._attr_device_info = dr.DeviceInfo(
                identifiers={(DOMAIN, entry.entry_id)},
                name=entry.title,
                manufacturer="Venice AI",
                model="AI Task",
                entry_type=dr.DeviceEntryType.SERVICE,
            )
            self._client: AsyncVeniceAIClient = entry.runtime_data.client
            self._attr_supported_features = ai_task.AITaskEntityFeature.GENERATE_DATA
            _LOGGER.info(
                "Initialized VeniceAITaskEntity for entry %s (runtime_data=%s, unique_id=%s)",
                entry.entry_id,
                bool(entry.runtime_data),
                self._attr_unique_id,
            )

        async def async_generate_data(
            self,
            task: ai_task.GenDataTask,
            chat_log: conversation.ChatLog,
        ) -> ai_task.GenDataTaskResult:
            """Handle a generate data task.

            Public entry-point that service handlers (and HA's ai_task platform)
            should call.  Internally delegates to _async_generate_data so the
            implementation stays testable and overridable.
            """
            return await self._async_generate_data(task, chat_log)

        async def _async_generate_data(
            self,
            task: ai_task.GenDataTask,
            chat_log: conversation.ChatLog,
        ) -> ai_task.GenDataTaskResult:
            """Internal implementation of generate data task."""
            # Build a local messages list without mutating chat_log.content.
            # HA core already appends the task instructions to chat_log.content
            # as a UserContent before calling us (and the custom service path
            # pre-seeds the ChatLog the same way), so we must NOT append them
            # again — doing so sent the instruction twice.
            messages = []
            for msg in chat_log.content:
                if isinstance(msg, conversation.SystemContent):
                    messages.append({"role": "system", "content": msg.content})
                elif isinstance(msg, conversation.UserContent):
                    messages.append({"role": "user", "content": msg.content})
                elif isinstance(msg, conversation.AssistantContent):
                    venice_msg = {
                        "role": "assistant",
                        "content": msg.content or "",
                    }
                    messages.append(venice_msg)

            if not messages or messages[-1].get("role") != "user":
                raise HomeAssistantError("No user message found in chat log")

            # When a structure is requested, actually ask the model for it:
            # build an OpenAI-style response_format json_schema (best effort)
            # and prepend a system instruction so models without native
            # structured output still emit parseable JSON. Without this the
            # model was never told to produce JSON, so json.loads() failed on
            # any prose reply.
            response_format = None
            if task.structure is not None:
                json_schema = _structure_to_json_schema(task.structure)
                if json_schema is not None:
                    response_format = {
                        "type": "json_schema",
                        "json_schema": {"name": "task_result", "schema": json_schema},
                    }
                schema_hint = (
                    json.dumps(json_schema) if json_schema is not None
                    else "the requested structure"
                )
                messages.insert(0, {
                    "role": "system",
                    "content": (
                        "Respond with ONLY a single valid JSON value matching this "
                        f"JSON schema, with no prose or markdown fences: {schema_hint}"
                    ),
                })

            # Use the configured chat model from options
            model: str = self.entry.options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL)

            # Use configured options from config entry instead of hardcoded values.
            # NumberSelector with step=1 returns float from the HA frontend; cast
            # to the types the Venice API expects.
            max_tokens: int = int(self.entry.options.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS))
            temperature: float = float(self.entry.options.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE))

            create_kwargs: dict = dict(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False,
            )
            if response_format is not None:
                create_kwargs["response_format"] = response_format

            try:
                response_data = await self._client.chat.completions.create_non_streaming(
                    **create_kwargs,
                )

                if not response_data or not response_data.get("choices"):
                    raise HomeAssistantError("Invalid Venice AI response")

                text = (
                    response_data["choices"][0]
                    .get("message", {})
                    .get("content", "")
                )

                if not task.structure:
                    return ai_task.GenDataTaskResult(
                        conversation_id=chat_log.conversation_id,
                        data=text,
                    )

                try:
                    data = json.loads(_extract_json(text))
                except json.JSONDecodeError as err:
                    _LOGGER.error(
                        "Failed to parse JSON response: %s. Response: %s",
                        err,
                        text,
                    )
                    raise HomeAssistantError(
                        "Error parsing structured response"
                    ) from err

                return ai_task.GenDataTaskResult(
                    conversation_id=chat_log.conversation_id,
                    data=data,
                )

            except VeniceAIError as err:
                _LOGGER.error("Venice AI error during task generation: %s", err)
                raise HomeAssistantError(f"Error generating data: {err}") from err
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.exception("Unexpected error during task generation")
                raise HomeAssistantError(f"Unexpected error: {err}") from err
