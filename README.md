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

This creates:

- `~/.weavbot/config.json` — configuration file
- `~/.weavbot/workspace/` — workspace directory with template files

Use `--set` to configure values inline during setup (repeatable, Helm-style):

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

## Windows: Tray Mode with traycli

On Windows, use [traycli](https://github.com/yankeguo/traycli) to keep `weavbot gateway` running as a system tray application.

Create `%USERPROFILE%\.traycli\config.json`:

```json
{
  "cmd": ["weavbot", "gateway"]
}
```

To start traycli automatically on login, place a shortcut to `traycli.exe` in the Start Menu Startup folder:

```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
```

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

Config keys use camelCase (e.g. `apiKey`, `allowFrom`, `mcpServers`).

Environment variables can override config values with the `WB_` prefix and `__` as the nesting delimiter, for example `WB_AGENTS__DEFAULTS__MODEL`.

## Credits

This project is a hard fork of [nanobot](https://github.com/HKUDS/nanobot) by [HKUDS](https://github.com/HKUDS).

## License

MIT
