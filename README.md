# Venice AI
Home Assistant Venice AI Conversation Integration

## Overview
The Venice AI integration allows you to enhance your Home Assistant setup with advanced conversational capabilities powered by Venice AI. This integration enables seamless interaction with your smart home devices through natural language processing.

## Features
- Natural language understanding for smart home commands
- Customizable responses based on user preferences
- Integration with various Home Assistant components
- Dynamic model selection from available Venice AI models

## Installation

### Option 1: HACS (Recommended)
1. Make sure you have [HACS](https://hacs.xyz/) installed in your Home Assistant instance.
2. Click on HACS in the sidebar.
3. Go to "Integrations".
4. Click the three dots in the top right corner and select "Custom repositories".
5. Add `https://github.com/steven-ahfu/venice_ai` as a repository with category "Integration".
6. Click "Add".
7. Search for "Venice AI" in the integrations tab.
8. Click "Download" and follow the installation instructions.
9. Restart Home Assistant.

### Option 2: Manual Installation
1. **Clone the repository:**
   ```bash
   git clone https://github.com/steven-ahfu/venice_ai.git
   ```

2. **Copy the integration files:**
   Place the `venice_ai` folder in your Home Assistant `custom_components` directory.

3. **Restart Home Assistant:**
   After copying the files, restart your Home Assistant instance to load the new integration.

## Configuration
To configure the Venice AI integration:

1. Go to Settings → Devices & Services
2. Click "Add Integration" and search for "Venice AI"
3. Enter your Venice AI API key
4. Configure additional options as needed:
   - Select your preferred model
   - Adjust temperature, max tokens, and other parameters
   - Customize the system prompt if desired

## Models

The Venice AI integration automatically filters and displays only models that support function calling, which is required for Home Assistant device control.

The current default model is Llama 3.3 70B (llama-3.3-70b), which provides excellent function calling capabilities for smart home automation.

For reasoning models like Venice Reasoning (qwen-2.5-qwq-32b) or DeepSeek R1 671B, you can disable thinking for lower latency by enabling the "Disable thinking" option in the configuration.

## Custom Tools

You can extend Venice AI with your own tools by creating `/config/venice_ai/tools.yaml`. Tools are merged with the built-in defaults at startup — your tools take precedence on name conflicts.

Supported tool types: `native`, `template`, `rest`, `scrape`, `bash`, `read_file`, `write_file`, `edit_file`, `sqlite`, `composite`.

See [`docs/custom-tools-examples.md`](docs/custom-tools-examples.md) for working examples including:
- **Morning briefing** — weather + calendar + battery status in one call
- **Shopping list** — read and add items via conversation
- **Notes** — append and read freeform timestamped notes
- **Pyscript bridge** — call any `@service` pyscript function by name
- **SQLite analytics** — query the recorder DB for historical insights

## Skills

Skills inject extra context into the system prompt before each conversation,
teaching the assistant how to behave in your setup without hard-coding it into
every prompt. A skill is a `SKILL.md` file with YAML frontmatter:

```
custom_components/venice_ai/skills/<skill-name>/SKILL.md
```

```markdown
---
description: One sentence telling the assistant what this skill covers.
---

# Guidance

- Write the behavioral instructions as plain Markdown here.
- Everything below the frontmatter is appended to the system prompt when the
  skill is enabled.
```

Two skills ship with the integration — `home-assistant` (safe device control)
and `venice-assistant` (voice/chat behavior). Enable the skills you want on the
**Skills & Function Calling** step of the integration's options flow.

After adding or editing a skill, pick it up without restarting by calling the
**`venice_ai.reload_skills`** service (Developer Tools → Actions), or restart
Home Assistant.

## Support
If you encounter any issues or have feature requests, please open an issue on our [GitHub Issues page](https://github.com/steven-ahfu/venice_ai/issues).

## License
This project is licensed under the MIT License - see the LICENSE file for details.
