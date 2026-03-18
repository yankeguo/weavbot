---
layout: default
title: Quick Start
permalink: /en/quick-start/
parent: English
nav_order: 2
---

# Quick Start

## 1. Initialize

```bash
weavbot onboard
```

This creates `~/.weavbot/config.json` and `~/.weavbot/workspace/`, then launches an **interactive setup wizard** that walks you through:

1. **Provider selection** — fetches known providers and models from [models.dev](https://models.dev), lets you pick a provider, model, and enter your API key
2. **Channel configuration** — configure chat channels (Telegram, Discord, Feishu, DingTalk, Slack, QQ, WeCom, Email, Mochat) by entering credentials
3. **Dependency install** — detects and offers to install [ripgrep](https://github.com/BurntSushi/ripgrep) (required by the agent's file search tool) to `~/.weavbot/bin/`
4. **Auto-start setup** — configures the gateway to start automatically on login (systemd on Linux, launchd on macOS, [traycli](https://github.com/yankeguo/traycli) on Windows)

The wizard auto-detects your system language and displays prompts in Chinese when appropriate. Override with `WB_LANG=en` or `WB_LANG=zh`.
CLI translations are now provided by the standalone `weavbot.i18n` package, with key namespaces such as `cli.setup.*` and `cli.commands.*` for future extension.

Alternatively, use `--set` to configure values inline (repeatable, Helm-style):

```bash
weavbot onboard \
  --set providers.anthropic.apiKey=sk-ant-xxx \
  --set providers.anthropic.mode=anthropic \
  --set agents.defaults.model=claude-sonnet-4-20250514 \
  --set agents.defaults.provider=anthropic
```

Keys are dot-separated camelCase paths matching the JSON config structure. Values are auto-coerced (numbers, booleans, null) or treated as strings.

## 2. Configure

You can also edit `~/.weavbot/config.json` directly to set your API key and model.

Providers are a flat dictionary — the key is a free-form name you choose, and each entry specifies a `mode` (`"openai"` or `"anthropic"`) plus credentials:

```json
{
  "providers": {
    "anthropic": {
      "mode": "anthropic",
      "apiKey": "sk-ant-xxx"
    },
    "openrouter": {
      "apiKey": "sk-or-v1-xxx",
      "apiBase": "https://openrouter.ai/api/v1"
    },
    "deepseek": {
      "apiKey": "sk-xxx",
      "apiBase": "https://api.deepseek.com/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "claude-sonnet-4-20250514",
      "provider": "anthropic"
    }
  }
}
```

- `mode` defaults to `"openai"` (OpenAI-compatible API). Set `"anthropic"` for native Anthropic API.
- `agents.defaults.provider` must match a key in the `providers` dict.

All channel and tool options are documented in the [Configuration]({{ site.baseurl }}/en/configuration/) section.

## 3. Run

```bash
weavbot gateway
```

This starts the long-running gateway that manages the agent, channels, scheduled tasks, and heartbeat.

[Install]({{ site.baseurl }}/en/install/) | [Auto-Start]({{ site.baseurl }}/en/auto-start/) | [CLI Reference]({{ site.baseurl }}/en/cli/)
