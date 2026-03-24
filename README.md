# weavbot

[![GitHub Actions](https://github.com/yankeguo/weavbot/actions/workflows/ci.yml/badge.svg)](https://github.com/yankeguo/weavbot/actions)
[![PyPI](https://img.shields.io/pypi/v/weavbot)](https://pypi.org/project/weavbot/)
[![Docs (English)](https://img.shields.io/badge/docs-English-blue)](https://yankeguo.github.io/weavbot/en/)
[![Docs (中文)](https://img.shields.io/badge/文档-中文-blue)](https://yankeguo.github.io/weavbot/zh/)

![Logo](https://imagedelivery.net/z27-nfL54f0eHFxCGFIatg/a4d02b7b-9a65-4e12-a600-997669806400/standard)

A lightweight personal AI assistant framework.

## Highlights

- Interactive onboarding: configure provider, model, and channel in one flow
- WeChat Clawbot support: [WeChat channel configuration](https://yankeguo.github.io/weavbot/en/configuration/#channelswechat)

## 亮点

- 交互式向导：一步完成 provider、model、channel 配置
- 微信 Clawbot 支持：[微信渠道配置](https://yankeguo.github.io/weavbot/zh/configuration/#channelswechat)

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

## Full documentation

- English: [https://yankeguo.github.io/weavbot/en/](https://yankeguo.github.io/weavbot/en/)

## 完整文档

- 中文: [https://yankeguo.github.io/weavbot/zh/](https://yankeguo.github.io/weavbot/zh/)

## Credits

This project is a hard fork of [nanobot](https://github.com/HKUDS/nanobot) by [HKUDS](https://github.com/HKUDS), with significant optimizations and improvements.

## License

MIT
