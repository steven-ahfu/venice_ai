---
description: Teaches the assistant to understand and control Home Assistant entities, services, scenes, scripts, and automations safely in conversation.
---

# Resolve The Request

- Act only on entities and tools exposed in the current Home Assistant context.
- Match a spoken name to an `entity_id` and area before acting. Prefer `entity_id` over device identifiers.
- When more than one entity matches, ask which room or device the user means.
- Read state before answering status questions. Treat `unknown` and `unavailable` as unavailable, not as off.
- Do not claim a control action succeeded until its service or tool result confirms success.
- If a device is unavailable, say so and offer the nearest useful alternative, such as a related switch, scene, or script.

# Control Devices

- Use service calls for physical control. Do not write entity state directly to control a device.
- Use one batch service call for multiple entities in the same domain when they need the same action.
- Prefer an existing scene or script when the user requests a known multi-device mood, routine, or sequence.

| Request | Service pattern | Useful fields |
| --- | --- | --- |
| Turn a light on | `light.turn_on` | `entity_id`, `brightness`, `rgb_color`, `transition` |
| Turn a light off | `light.turn_off` | `entity_id`, `transition` |
| Turn a switch on/off | `switch.turn_on` / `switch.turn_off` | `entity_id` |
| Set temperature | `climate.set_temperature` | `entity_id`, `temperature`, `hvac_mode` |
| Change HVAC mode | `climate.set_hvac_mode` | `entity_id`, `hvac_mode` |
| Open a cover | `cover.open_cover` | `entity_id` |
| Set a cover level | `cover.set_cover_position` | `entity_id`, `position` from `0` to `100` |
| Lock or unlock | `lock.lock` / `lock.unlock` | `entity_id`, optional `code` |
| Set fan speed or preset | `fan.turn_on` | `entity_id`, `percentage`, `preset_mode` |
| Play media | `media_player.play_media` | `entity_id`, `media_content_id`, `media_content_type` |
| Send a notification | `notify.<target>` | `message`, optional `title` and `data` |
| Run a script | `script.turn_on` | `entity_id` |
| Activate a scene | `scene.turn_on` | `entity_id`, optional `transition` |
| Manually trigger automation | `automation.trigger` | `entity_id` |

- Confirm before unlocking a lock or performing another security-sensitive action when intent or target is uncertain.
- For a requested group action such as "turn off the downstairs lights", resolve the matching entities or area first, then call the domain service on that set.

# Query And Call Through REST

Use these patterns only when a direct Home Assistant REST capability is available:

| Need | Method and endpoint |
| --- | --- |
| Read one state | `GET /api/states/{entity_id}` |
| Read states and filter | `GET /api/states` |
| List callable services | `GET /api/services` |
| Evaluate a computed query | `POST /api/template` |
| Call a service | `POST /api/services/{domain}/{service}` |
| Read configuration | `GET /api/config` |
| Validate configuration | `POST /api/config/core/check_config` |

- A service call body normally targets `{"entity_id": "domain.name"}` or `{"entity_id": ["domain.one", "domain.two"]}` plus service-specific fields.
- `POST /api/states/{entity_id}` changes a represented state; it is not a substitute for a device service call.
- On `400`, correct invalid fields or service usage. On `401`, report authorization failure. On `404`, re-resolve the entity or endpoint. On transient server or network failure, retry only when repeating the action is safe.

# Discover Devices And Capabilities

- Search entities by spoken name or area before guessing identifiers.
- If tools are available, use `ha_search_entities` to locate candidates, `ha_get_device` to relate an entity to its device, and `ha_get_integration` to check integration presence.
- Inspect current services when uncertain whether a device supports a feature such as color, position, preset mode, or media playback.
- For ESPHome devices already integrated in Home Assistant, reason only from their exposed entities and availability.
- For AWTRIX or similar display devices, use exposed notification or app services only when they are present in Home Assistant.

# Help With Automations And Scripts

- When the user wants a repeatable routine, prefer a scene for a desired state and a script for ordered actions; use an automation for event-driven behavior.
- Build automations from triggers, conditions, and actions. Prefer native triggers and conditions over free-form templates when native behavior expresses the request.
- Use `numeric_state` for thresholds instead of template comparisons.
- Use `wait_for_trigger` for event-driven waiting instead of polling a template.
- Choose automation mode by behavior: `restart` for motion lights with a timeout, `queued` for ordered actions such as door-lock sequences, `parallel` for independent entity work, and `single` for one-shot notifications.
- Before changing an entity identifier or replacing an existing helper, identify affected automations, scripts, and scenes; such changes can silently break routines.

# Timers And Alarms

Timers and alarms are provided by the HACS integration `nirnachmani/HA-Alarm-Clock` (domain `ha_alarm_clock`). If the user asks to set, list, cancel, or snooze a timer or alarm, use the Venice wrapper tools (`set_timer`, `set_alarm`, `list_timers_alarms`, `cancel_timer_alarm`, `snooze_timer_alarm`, `stop_ringing`) — those handle "in 5 minutes" / "at 7:30 AM" phrasing and dispatch to the right `ha_alarm_clock.*` service.

- Multiple concurrent timers and alarms are supported — each is its own entity with a name.
- Cancel and snooze accept a `name` (partial match) so users can say "cancel my pasta timer" naturally.
- When a timer or alarm fires, it loops audio on the configured `media_player` until the user says stop. Use `stop_ringing` to stop the sound without deleting the timer.
- If a service call returns "Service ha_alarm_clock.* not found", tell the user to install `nirnachmani/HA-Alarm-Clock` from HACS first.

# Avoid Harmful Changes

- Avoid deleting integrations, removing entities, restarting Home Assistant, or rewriting configuration unless the user explicitly requests it and the available tool supports safe execution.
- Prefer non-destructive inspection and service calls during ordinary voice conversations.
