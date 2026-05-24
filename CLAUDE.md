# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Home Assistant custom integration for the Venice AI API. Adds conversation (LLM), TTS, STT, AI tasks, and image generation as HA platforms.

## Installation & Testing

There are no automated tests or lint commands configured. To test changes:

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
| `client.py` | `AsyncVeniceAIClient` — all HTTP to Venice API; sub-classes: `ChatCompletions`, `Models`, `Voices`, `Speech`, `Transcriptions` |
| `conversation.py` | `VeniceAIConversationEntity` — tool-calling loop (max 10 iterations), HA ChatLog ↔ Venice message format conversion |
| `config_flow.py` | Config + options flow; dynamically fetches models from API and filters by capability |
| `tts.py` | `TextToSpeechEntity` — returns raw audio bytes |
| `stt.py` | `SpeechToTextEntity` — converts PCM→WAV before sending to API |
| `ai_task.py` | `VeniceAITaskEntity` — structured JSON output via AI |
| `__init__.py` | Entry point; sets up platforms and registers `generate_image` / `ai_task` services |
| `const.py` | All defaults and constants (models, voices, config keys) |
| `services.yaml` | Service schemas for `generate_image` and `ai_task` |

### Non-Obvious Details

- **Streaming**: `ChatCompletions.create()` uses SSE (`data: <json>` chunks); streaming is the default path for conversation.
- **Tool calling loop**: Conversation runs up to 10 agentic iterations — sends tool results back to the model until no more tool calls are requested.
- **Reasoning models**: Model ID can include query-string suffixes e.g. `model-name:disable_thinking=true&strip_thinking_response=true`; config_flow builds this string.
- **Model filtering**: Config flow fetches all Venice models and filters to only those with `function_calling` capability for chat, or the relevant capability for TTS/STT.
- **Options vs data**: HA config entry `data` is immutable (API key); `options` is mutable (model, prompt, temperature, etc.).
- **voluptuous_openapi**: Used to convert HA selector schemas into JSON Schema for Venice API tool definitions.
- **Audio**: STT prepends a WAV header to raw PCM before posting to the transcription endpoint.
- **System prompt templating**: Supports `{{ha_name}}`, `{{user_name}}`, `{{llm_context}}` placeholders.

## Adding a New Platform

1. Create the entity file (e.g. `myplatform.py`) following the existing pattern.
2. Add the platform string to `PLATFORMS` in `__init__.py`.
3. Add any new constants to `const.py`.
4. Add config/options schema in `config_flow.py` if user-configurable.
5. Add UI strings to `strings.json`.
