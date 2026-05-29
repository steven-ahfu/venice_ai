# Custom Tools

Venice AI ships with a small set of built-in tools (see
[`custom_components/venice_ai/default_tools.yaml`](../custom_components/venice_ai/default_tools.yaml)).
You can add your own — or override the built-ins — by creating a YAML file at:

```
<config>/venice_ai/tools.yaml
```

(`<config>` is your Home Assistant configuration directory, the one that
contains `configuration.yaml`.)

Your tools are merged with the bundled defaults at startup. **On a name
conflict, your tool wins**, so you can redefine a built-in by reusing its
`name`.

After editing the file, reload the tools without restarting Home Assistant by
calling the **`venice_ai.reload_tools`** service (Developer Tools → Actions),
or restart Home Assistant. The currently active tool names are listed on the
**Skills & Function Calling** step of the integration's options flow.

## Tool schema

Every tool is a YAML mapping with at least these keys:

| Key | Required | Description |
| --- | --- | --- |
| `name` | yes | Unique function name the model calls. Use `snake_case`. |
| `type` | yes | One of the types below. |
| `description` | recommended | Tells the model *when* to use the tool. Be specific. |
| `parameters` | recommended | A JSON-Schema `object` describing the arguments the model must supply. |

`parameters` follows the OpenAI function-calling / JSON-Schema convention:

```yaml
parameters:
  type: object
  properties:
    location:
      type: string
      description: City name.
  required:
    - location
```

The values the model fills in are passed to the tool as `arguments` and are
available to every template field (`{{ location }}`, etc.) as Jinja2
variables.

### Available types

| Type | Purpose | Key fields |
| --- | --- | --- |
| `native` | Call Home Assistant directly | `operation`: `execute_service` or `get_history` |
| `template` | Render a Jinja2 template | `value_template`, optional `parse_result` |
| `script` | Run a HA script sequence | `sequence` (arguments become run variables) |
| `rest` | HTTP request | `resource` / `resource_template`, `method`, `headers`, `payload` / `payload_template`, `value_template` |
| `scrape` | Fetch a page and extract with a CSS selector | `resource` / `resource_template`, `select`, `attribute`, `index`, `value_template` |
| `bash` | Run a shell command (guarded) | `command`, `cwd`, `restrict_to_workspace` |
| `read_file` | Read a file from the workspace | `path`, optional `allow_dir` |
| `write_file` | Write a file to the workspace | `path`, `content`, optional `allow_dir` |
| `edit_file` | Find/replace text in a workspace file | `path`, `old_text`, `new_text`, optional `allow_dir` |
| `sqlite` | Query a SQLite database (recorder DB by default) | `query`, optional `single`, `db_url` |
| `composite` | Chain several tools in sequence | `sequence` (list of step configs) |

> **File and shell sandboxing.** `read_file` / `write_file` / `edit_file`
> resolve paths inside the `<config>/venice_ai/` workspace. Add extra allowed
> roots with `allow_dir`. The `bash` type blocks destructive commands (`rm -rf`,
> `mkfs`, `shutdown`, fork bombs, …), caps output at 10 000 characters, and
> times out after 5 minutes.

---

## Examples

### Morning briefing — weather + battery in one call

A `composite` tool runs each step in order. A step's result can be stored under
`response_variable` so later steps (and the final return value) can reference
it. The last step's output is what the model receives.

```yaml
- name: morning_briefing
  type: composite
  description: >-
    Build a single morning summary with the weather and the lowest phone
    battery. Use when the user asks for a morning briefing or "how's the day
    looking".
  parameters:
    type: object
    properties:
      location:
        type: string
        description: City to fetch weather for.
    required:
      - location
  sequence:
    - type: rest
      resource_template: "https://wttr.in/{{ location | urlencode }}?format=j1"
      method: GET
      response_variable: weather
    - type: template
      value_template: >-
        Weather: {{ (weather | from_json).current_condition[0].weatherDesc[0].value }},
        {{ (weather | from_json).current_condition[0].temp_C }}°C.
        Lowest battery: {{ states.sensor
          | selectattr('attributes.device_class', 'eq', 'battery')
          | map(attribute='state') | map('int', 0) | min }}%.
```

### Shopping list — read and add items via conversation

Two small `native` tools wrap the built-in `shopping_list` services. Adding an
item is a service call; reading the list is a `template`.

```yaml
- name: add_shopping_item
  type: native
  operation: execute_service
  description: Add an item to the Home Assistant shopping list.
  parameters:
    type: object
    properties:
      domain:
        type: string
        default: shopping_list
      service:
        type: string
        default: add_item
      service_data:
        type: object
        description: Must contain "name", e.g. {"name": "milk"}.
    required:
      - service_data

- name: read_shopping_list
  type: template
  description: Read the current shopping list back to the user.
  value_template: >-
    {% set items = state_attr('todo.shopping_list', 'all') or [] %}
    {% if items %}{{ items | map(attribute='summary') | join(', ') }}
    {% else %}The shopping list is empty.{% endif %}
```

### Notes — append and read timestamped notes

Uses the file tools. Files live under `<config>/venice_ai/`, so this writes to
`<config>/venice_ai/notes.txt`.

```yaml
- name: add_note
  type: write_file
  description: >-
    Append a freeform, timestamped note. Use when the user says "make a note"
    or "remember that…".
  parameters:
    type: object
    properties:
      text:
        type: string
        description: The note content.
    required:
      - text
  path: "notes.txt"
  content: "{{ now().isoformat() }} — {{ text }}\n"

- name: read_notes
  type: read_file
  description: Read back all saved notes.
  path: "notes.txt"
```

> `write_file` overwrites the target. For a true append-only log, point a
> `bash` tool at `echo "$(date) — {{ text }}" >> notes.txt` with
> `cwd: "{{ config_dir }}/venice_ai"` instead.

### Pyscript bridge — call any `@service` function by name

If you use [pyscript](https://github.com/custom-components/pyscript), every
`@service` function is exposed under the `pyscript` domain. A single `native`
tool lets the model call any of them.

```yaml
- name: call_pyscript
  type: native
  operation: execute_service
  description: >-
    Invoke a pyscript @service function by name. "service" is the function
    name; "service_data" carries its keyword arguments.
  parameters:
    type: object
    properties:
      domain:
        type: string
        default: pyscript
      service:
        type: string
        description: The pyscript function name to call.
      service_data:
        type: object
        description: Keyword arguments for the function.
    required:
      - service
```

### SQLite analytics — query the recorder DB

The `sqlite` type opens the recorder database **read-only** by default. Use it
for historical questions the live state can't answer.

```yaml
- name: top_power_consumers
  type: sqlite
  description: >-
    Return the entities with the most state changes in the last day — a rough
    proxy for the busiest devices. Use for "what's been most active lately".
  parameters:
    type: object
    properties:
      limit:
        type: integer
        description: How many rows to return.
        default: 5
  query: >-
    SELECT sm.entity_id, COUNT(*) AS changes
    FROM states s
    JOIN states_meta sm ON s.metadata_id = sm.metadata_id
    WHERE s.last_updated_ts > strftime('%s', 'now', '-1 day')
    GROUP BY sm.entity_id
    ORDER BY changes DESC
    LIMIT {{ limit | int(5) }};
```

> Pass `single: true` to return just the first row instead of a list, or set
> `db_url` to query a different SQLite file.

---

## Troubleshooting

- **Tool not showing up?** Check the Home Assistant log for
  `venice_ai` warnings — a malformed tool is skipped and logged with the
  reason (missing `name`, wrong `type`, missing required field, etc.).
- **Changes not taking effect?** Call `venice_ai.reload_tools` or restart HA.
- **Model not calling the tool?** Sharpen the `description` — it's the only
  signal the model has for *when* to use the tool.
