---
description: Teaches the assistant how Venice chat, speech synthesis, and transcription behave in a Home Assistant voice pipeline.
---

# Voice Response Behavior

- Produce replies that sound natural when spoken aloud: concise sentences, direct answers, and no unnecessary formatting.
- When speech recognition leaves a device name, value, or security-sensitive command ambiguous, ask a short clarification question before acting.
- Do not expose hidden reasoning or `<think>...</think>` text in a spoken reply.

# Venice Chat Behavior

- Venice chat uses `POST /chat/completions` with OpenAI-compatible `messages`, `tools`, `tool_choice`, sampling controls, and streaming fields.
- Keep `n` at `1` for an interactive voice assistant.
- Function-call messages may be used for Home Assistant tools; wait for returned tool results before giving a final spoken outcome.
- `venice_parameters.include_venice_system_prompt` defaults to `true`; set it to `false` when the Home Assistant agent's own system instructions must have full control.
- Use `venice_parameters.strip_thinking_response: true` to remove reasoning tags from supported reasoning-model output, or `disable_thinking: true` when the selected model supports disabling reasoning.
- Server-side search is controlled through `venice_parameters.enable_web_search` with `off`, `auto`, or `on`; use it only for questions requiring current external information.
- If citations are needed, enable web citations and speak a short answer rather than reading citation markup aloud.
- Some Venice features can be encoded in the model identifier as suffixes, including `enable_web_search`, `include_venice_system_prompt`, `strip_thinking_response`, and `disable_thinking`. Unknown suffix keys are silently ignored.
- `enable_e2ee` and `enable_x_search` must be sent in `venice_parameters`, not model suffixes.
- `/responses` is stateless and supports fewer Venice parameters than `/chat/completions`; send full history with each request and prefer chat completions for this voice agent's tool-driven conversation.

# Speech Synthesis

- Venice TTS uses `POST /audio/speech`.
- Keep synthesized `input` at or below `4096` characters. Split long replies at sentence boundaries.
- Choose a voice that belongs to the selected TTS model; voice names are case-sensitive and a wrong model/voice pairing fails.
- Available output formats include `mp3`, `opus`, `aac`, `flac`, `wav`, and `pcm`; `pcm` is 24 kHz signed 16-bit little-endian audio suitable for low-latency pipelines.
- Set `streaming: true` for latency-sensitive spoken replies and consume audio chunks as they arrive.
- Keep `speed` near `0.8` to `1.3` for understandable narration unless the user requests otherwise.
- Use language or style controls only when the selected speech model supports them; unsupported values may be ignored.

# Speech Transcription

- Venice STT uses `POST /audio/transcriptions` with `multipart/form-data`.
- Upload actual audio in the `file` field; base64 embedded in JSON is not accepted.
- Supported inputs include `wav`, `wave`, `flac`, `m4a`, `aac`, `mp4`, `mp3`, `ogg`, and `webm`.
- Use `json` output for normal conversation processing. Use timestamp-capable JSON or subtitle output when timings matter; plain `text` loses timestamp data.
- A `language` hint is honored by Whisper-family models; other transcription models may auto-detect and ignore it.

# Failures

- On `401`, treat the Venice credential as invalid and do not retry the same request as if it were transient.
- On `429`, wait according to `Retry-After` when present, then retry conservatively.
- On a `5xx` or network failure, describe the voice service as temporarily unavailable and retry only when the conversation can tolerate delay.
- On `422`, state that the request could not be processed; do not improvise a tool result or device outcome.
