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

### 2. Configure

Edit `~/.weavbot/config.json` to set your API key and model.

Set your API key (e.g. OpenRouter):

```json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-xxx"
    }
  }
}
```

Set your model:

```json
{
  "agents": {
    "defaults": {
      "model": "anthropic/claude-sonnet-4-6",
      "provider": "openrouter"
    }
  }
}
```

For the full list of supported providers, channel configurations (Telegram, Discord, Feishu, Slack, etc.), and MCP setup, refer to the [upstream nanobot documentation](https://github.com/HKUDS/nanobot).

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
| `weavbot onboard` | Initialize config and workspace |
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
