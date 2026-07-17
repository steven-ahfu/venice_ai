# AGENTS.md

This file provides guidance to coding agents when working with code in this repository.

## What This Is

A Home Assistant custom integration for the Venice AI API. Adds conversation (LLM), TTS, STT, AI tasks, and image generation as HA platforms.

## Installation & Testing

Unit tests live in `tests/` and run against a lightweight HA stub harness (`tests/conftest.py`). Run with:

```bash
pytest                       # full suite
pytest tests/test_client.py  # single file
```

To test on a live HA instance:

1. Copy `custom_components/venice_ai/` into your HA instance's `config/custom_components/`
2. Restart Home Assistant
3. Settings → Devices & Services → Add Integration → Venice AI

HACS compatibility is validated via GitHub Actions (`hacs/action@main`) on push/PR.

## Architecture

All source lives in `custom_components/venice_ai/`.

### Request Flow

```
HA Core → conversation.py / tts.py / stt.py / ai_task.py
               ↓
           client.py  (AsyncVeniceAIClient + sub-APIs)
               ↓
         Venice AI REST API (httpx, async)
```

### Key Files

| File | Role |
|------|------|
| `client.py` | `AsyncVeniceAIClient` — all HTTP to Venice API; sub-classes: `ChatCompletions`, `Models`, `Speech`, `Transcriptions`, `Images` |
| `conversation.py` | `VeniceAIConversationEntity` — tool-calling loop (user-configurable, default 5 iterations), HA ChatLog ↔ Venice message format conversion |
| `config_flow.py` | Config + options flow; dynamically fetches models from API and filters by capability |
| `tts.py` | `TextToSpeechEntity` — returns raw audio bytes |
| `stt.py` | `SpeechToTextEntity` — converts PCM→WAV before sending to API |
| `ai_task.py` | `VeniceAITaskEntity` — structured JSON output via AI |
| `__init__.py` | Entry point; sets up platforms and registers `generate_image` / `ai_task` services |
| `coordinator.py` | `DataUpdateCoordinator` — periodic model/capability refresh |
| `const.py` | All defaults and constants (models, voices, config keys) |
| `services.yaml` | Service schemas for `generate_image` and `ai_task` |
| `tools.py` | `ToolManager` — loads and merges `default_tools.yaml` + user `tools.yaml` |
| `default_tools.yaml` | Built-in tool definitions shipped with the integration |
| `functions/` | Tool executors per type: `native`, `template`, `rest`, `scrape`, `bash`, `read_file`, `write_file`, `edit_file`, `sqlite`, `composite` |
| `skills.py` | Skill loading from `skills/` (markdown-based prompt augmentation) |
| `diagnostics.py` | HA diagnostics dump (redacts API key) |
| `exceptions.py` | `VeniceAIError` hierarchy: `AuthenticationError`, `RateLimitError`, `ServiceUnavailableError`, `NetworkError` |

### Non-Obvious Details

- **Streaming**: `ChatCompletions.create()` uses SSE (`data: <json>` chunks); streaming is the default path for conversation.
- **Tool calling loop**: Conversation runs up to `CONF_MAX_TOOL_ITERATIONS` agentic iterations (default 5, user-configurable in options) — sends tool results back to the model until no more tool calls are requested.
- **Reasoning models**: Model ID can include query-string suffixes e.g. `model-name:disable_thinking=true&strip_thinking_response=true`; config_flow builds this string.
- **Model filtering**: Config flow fetches all Venice models and filters to only those with `function_calling` capability for chat, or the relevant capability for TTS/STT.
- **Options vs data**: HA config entry `data` is immutable (API key); `options` is mutable (model, prompt, temperature, etc.).
- **voluptuous_openapi**: Used to convert HA selector schemas into JSON Schema for Venice API tool definitions. Now a declared requirement in `manifest.json`.
- **Audio**: STT prepends a WAV header to raw PCM before posting to the transcription endpoint.
- **System prompt templating**: Supports `{{ha_name}}`, `{{user_name}}`, `{{llm_context}}` placeholders.
- **Custom tools**: `ToolManager` merges `default_tools.yaml` (shipped) with user-provided `/config/venice_ai/tools.yaml` at startup; user tools take precedence on name conflicts. Each tool's `type` dispatches to an executor in `functions/`.
- **`ai_task` is a soft dependency**: `manifest.json` puts it in `after_dependencies`, and `__init__.py` does a conditional import — the integration loads on HA versions without `ai_task`.

## Reading Live Home Assistant Data

### HA REST API

The HA REST API is available at `http://homeassistant.local:8123/api/` (or `http://supervisor/core/api/` from within HA OS add-ons). All endpoints require:

```
Authorization: Bearer <long_lived_access_token>
Content-Type: application/json
```

Useful endpoints for debugging and tooling:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/error_log` | GET | Full current log as plain text |
| `/api/states` | GET | All entity states |
| `/api/states/<entity_id>` | GET | Single entity state + attributes |
| `/api/services` | GET | All callable services |
| `/api/template` | POST | Evaluate a Jinja2 template (`{"template": "..."}`) |
| `/api/config` | GET | HA configuration info |
| `/api/logbook/<timestamp>` | GET | Logbook entries since timestamp |

### Reading Logs via tools.yaml

The simplest way to read live logs from a Venice AI tool is the `bash` type — no auth needed since it reads the file directly:

```yaml
- name: read_system_log
  type: bash
  description: Read recent Home Assistant log entries to diagnose errors or warnings.
  parameters:
    type: object
    properties:
      lines:
        type: integer
        description: Number of recent lines to return (default 100).
  command: "tail -n {{ lines | default(100) }} /config/home-assistant.log"
```

Alternatively use `rest` with a long-lived token stored as a template variable:

```yaml
- name: read_system_log
  type: rest
  resource: "http://supervisor/core/api/error_log"
  method: GET
  headers:
    Authorization: "Bearer YOUR_LONG_LIVED_TOKEN"
```

## Adding a New Platform

1. Create the entity file (e.g. `myplatform.py`) following the existing pattern.
2. Add the platform string to `PLATFORMS` in `__init__.py`.
3. Add any new constants to `const.py`.
4. Add config/options schema in `config_flow.py` if user-configurable.
5. Add UI strings to `strings.json`.
