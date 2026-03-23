# weavbot

[![GitHub Actions](https://github.com/yankeguo/weavbot/actions/workflows/ci.yml/badge.svg)](https://github.com/yankeguo/weavbot/actions)
[![PyPI](https://img.shields.io/pypi/v/weavbot)](https://pypi.org/project/weavbot/)
[![Docs (English)](https://img.shields.io/badge/docs-English-blue)](https://yankeguo.github.io/weavbot/en/)
[![Docs (中文)](https://img.shields.io/badge/文档-中文-blue)](https://yankeguo.github.io/weavbot/zh/)

A lightweight personal AI assistant framework.

## Installation

```bash
uv tool install weavbot
```

Verify:

```bash
weavbot --version
```

To try the latest unreleased features:

```bash
uv tool install git+https://github.com/yankeguo/weavbot.git
```

## Onboard (Recommended First Run)

Initialize local config/workspace and run the interactive setup wizard:

```bash
weavbot onboard
```

What `onboard` does:

- Creates `~/.weavbot/config.json` and `~/.weavbot/workspace/`
- Guides provider/model selection with realtime filtering
- Configures one chat channel in the wizard (Telegram/Discord/Feishu/DingTalk/Slack/QQ/Wecom/Email/Mochat)
- Offers optional `ripgrep` install and gateway auto-start setup

For non-interactive or scripted setup, use repeatable `--set key=value`:

```bash
weavbot onboard \
  --set providers.openrouter.apiKey=sk-or-v1-xxx \
  --set providers.openrouter.apiBase=https://openrouter.ai/api/v1 \
  --set agents.defaults.provider=openrouter \
  --set agents.defaults.model=openai/gpt-4o-mini
```

Detailed CLI docs:
- English: [CLI Reference](https://yankeguo.github.io/weavbot/en/cli/)
- 中文: [命令参考](https://yankeguo.github.io/weavbot/zh/cli/)

**Full documentation:** [https://yankeguo.github.io/weavbot/](https://yankeguo.github.io/weavbot/)

## Credits

This project is a hard fork of [nanobot](https://github.com/HKUDS/nanobot) by [HKUDS](https://github.com/HKUDS), with significant optimizations and improvements.

## License

MIT
