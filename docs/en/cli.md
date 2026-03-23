---
layout: default
title: CLI Reference
permalink: /en/cli/
parent: English
nav_order: 5
---

# CLI Reference

| Command | Description |
| --- | --- |
| `weavbot onboard [--set key=value]` | Initialize config and workspace |
| `weavbot gateway` | Start the gateway |
| `weavbot agent` | Interactive chat mode |
| `weavbot agent -m "..."` | Send a single message |

## `weavbot onboard`

`onboard` is the recommended first command after installation.

```bash
weavbot onboard
```

### What it initializes

- Creates `~/.weavbot/config.json`
- Creates `~/.weavbot/workspace/`
- Runs an interactive setup wizard for provider/model/channel
- Offers optional ripgrep install and auto-start setup

### Interactive picker behavior

- **Realtime filtering:** provider/model/channel pickers support arrow-key navigation and type-to-filter.
- **Single-select channel:** channel setup selects one channel per run, then prompts required fields.
- **Ctrl+C semantics:**
  - Provider picker: skip provider setup
  - Model picker: go back to provider picker
  - Channel picker and field input: skip channel setup
- **Compatibility fallback:** if realtime picker is unavailable (for example, non-TTY terminal), onboarding downgrades to numbered selection mode.

### Script-friendly mode with `--set`

Use repeatable `--set key=value` to configure without interactive input:

```bash
weavbot onboard \
  --set providers.openrouter.apiKey=sk-or-v1-xxx \
  --set providers.openrouter.apiBase=https://openrouter.ai/api/v1 \
  --set providers.openrouter.mode=openai \
  --set agents.defaults.provider=openrouter \
  --set agents.defaults.model=openai/gpt-4o-mini
```

Values are auto-coerced where possible (`true`, `false`, numbers, `null`), otherwise treated as strings.

## Chat Commands

In interactive mode or any chat channel (Telegram, Discord, etc.), you can use slash commands:

| Command | Description |
| --- | --- |
| `/new` | Start a new conversation (archive long-term memory first, then clear the session) |
| `/stop` | Stop the current running task (including subagents) |
| `/help` | Show available commands |

[Quick Start]({{ site.baseurl }}/en/quick-start/) | [Configuration]({{ site.baseurl }}/en/configuration/)
