# weavbot

A lightweight personal AI assistant framework.

Hard fork of [nanobot](https://github.com/HKUDS/nanobot), for detailed documentation on models, providers, channels, MCP, and more, refer to the upstream project.

## Installation

```bash
uv tool install git+https://github.com/yankeguo/weavbot.git
```

Verify:

```bash
weavbot --version
```

## Quick Start

### 1. Initialize

```bash
weavbot onboard
```

This creates `~/.weavbot/config.json` and `~/.weavbot/workspace/`, then launches an **interactive setup wizard** that walks you through:

1. **Provider selection** — fetches known providers and models from [models.dev](https://models.dev), lets you pick a provider, model, and enter your API key
2. **Channel configuration** — configure chat channels (Telegram, Discord, Feishu, DingTalk, Slack, QQ, Email, Mochat) by entering credentials
3. **Dependency install** — detects and offers to install [ripgrep](https://github.com/BurntSushi/ripgrep) (required by the agent's file search tool) to `~/.weavbot/bin/`
4. **Auto-start setup** — configures the gateway to start automatically on login (systemd on Linux, launchd on macOS, [traycli](https://github.com/yankeguo/traycli) on Windows)

The wizard auto-detects your system language and displays prompts in Chinese when appropriate. Override with `WB_LANG=en` or `WB_LANG=zh`.

Alternatively, use `--set` to configure values inline (repeatable, Helm-style):

```bash
weavbot onboard \
  --set providers.anthropic.apiKey=sk-ant-xxx \
  --set providers.anthropic.mode=anthropic \
  --set agents.defaults.model=claude-sonnet-4-20250514 \
  --set agents.defaults.provider=anthropic
```

Keys are dot-separated camelCase paths matching the JSON config structure. Values are auto-coerced (numbers, booleans, null) or treated as strings.

### 2. Configure

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

For channel configurations (Telegram, Discord, Feishu, Slack, etc.) and MCP setup, refer to the [upstream nanobot documentation](https://github.com/HKUDS/nanobot).

### 3. Run

```bash
weavbot gateway
```

This starts the long-running gateway that manages the agent, channels, scheduled tasks, and heartbeat.

## Auto-Start

The interactive setup (`weavbot onboard`) can configure auto-start for you. You can also set it up manually:

### Linux (systemd)

The wizard writes a user-level service to `~/.config/systemd/user/weavbot.service` and enables it with `systemctl --user enable --now weavbot.service`.

### macOS (launchd)

The wizard writes a LaunchAgent to `~/Library/LaunchAgents/com.weavbot.gateway.plist` and loads it with `launchctl load`.

### Windows (traycli)

The wizard downloads [traycli](https://github.com/yankeguo/traycli) to `~/.weavbot/bin/traycli.exe`, writes `~/.traycli/config.json`, and creates a startup shortcut. traycli keeps `weavbot gateway` running as a system tray application with no console window.

## CLI Reference

| Command | Description |
| --- | --- |
| `weavbot onboard [--set key=value]` | Initialize config and workspace |
| `weavbot gateway` | Start the gateway |
| `weavbot agent` | Interactive chat mode |
| `weavbot agent -m "..."` | Send a single message |
| `weavbot status` | Show status |
| `weavbot channels status` | Show channel status |

## Configuration Reference

| Item | Value |
| --- | --- |
| Config file | `~/.weavbot/config.json` |
| Workspace | `~/.weavbot/workspace/` |
| Data directory | `~/.weavbot/` |
| Built-in bin | `~/.weavbot/bin/` (always in agent tool PATH) |
| Logs | `~/.weavbot/logs/` |

Config keys use camelCase (e.g. `apiKey`, `allowFrom`, `mcpServers`).

Environment variables can override config values with the `WB_` prefix and `__` as the nesting delimiter, for example `WB_AGENTS__DEFAULTS__MODEL`.

Set `WB_LANG` to override the interactive setup language (e.g. `WB_LANG=zh` or `WB_LANG=en`).

## Credits

This project is a hard fork of [nanobot](https://github.com/HKUDS/nanobot) by [HKUDS](https://github.com/HKUDS).

## License

MIT
