# weavbot

[![GitHub Actions](https://github.com/yankeguo/weavbot/actions/workflows/ci.yml/badge.svg)](https://github.com/yankeguo/weavbot/actions)
[![PyPI](https://img.shields.io/pypi/v/weavbot)](https://pypi.org/project/weavbot/)
[![Docs (English)](https://img.shields.io/badge/docs-English-blue)](https://yankeguo.github.io/weavbot/en/)
[![Docs (中文)](https://img.shields.io/badge/文档-中文-blue)](https://yankeguo.github.io/weavbot/zh/)

A lightweight personal AI assistant framework.

[中文说明](./README.zh.md)

## Highlights / 亮点

- Interactive onboarding for provider/model/channel setup / 交互式初始化（provider/model/channel 一步配置）
- Wechat Clawbot support / 支持微信 ClawBot（Wechat Clawbot）：[Wechat channel configuration](https://yankeguo.github.io/weavbot/en/configuration/#channelswechat) | [微信渠道配置](https://yankeguo.github.io/weavbot/zh/configuration/#channelswechat)

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

After installation, run the recommended first steps:

Run onboarding:

```bash
weavbot onboard
```

Detailed CLI docs:
- English: [CLI Reference](https://yankeguo.github.io/weavbot/en/cli/)
- 中文: [命令参考](https://yankeguo.github.io/weavbot/zh/cli/)

**Full documentation:** [https://yankeguo.github.io/weavbot/](https://yankeguo.github.io/weavbot/)

## Credits

This project is a hard fork of [nanobot](https://github.com/HKUDS/nanobot) by [HKUDS](https://github.com/HKUDS), with significant optimizations and improvements.

## License

MIT
