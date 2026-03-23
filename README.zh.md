# weavbot

[![GitHub Actions](https://github.com/yankeguo/weavbot/actions/workflows/ci.yml/badge.svg)](https://github.com/yankeguo/weavbot/actions)
[![PyPI](https://img.shields.io/pypi/v/weavbot)](https://pypi.org/project/weavbot/)
[![Docs (English)](https://img.shields.io/badge/docs-English-blue)](https://yankeguo.github.io/weavbot/en/)
[![Docs (中文)](https://img.shields.io/badge/文档-中文-blue)](https://yankeguo.github.io/weavbot/zh/)

轻量级个人 AI 助手框架。

[English](./README.md)

## Highlights / 亮点

- Interactive onboarding for provider/model/channel setup / 交互式初始化（provider/model/channel 一步配置）
- Wechat Clawbot support / 支持微信 ClawBot（Wechat Clawbot）：[Wechat channel configuration](https://yankeguo.github.io/weavbot/en/configuration/#channelswechat) | [微信渠道配置](https://yankeguo.github.io/weavbot/zh/configuration/#channelswechat)

## 安装

```bash
uv tool install weavbot
```

验证：

```bash
weavbot --version
```

体验最新未发布功能：

```bash
uv tool install git+https://github.com/yankeguo/weavbot.git
```

安装后，建议按以下步骤开始：

执行 onboarding：

```bash
weavbot onboard
```

详细命令文档：

- English: [CLI Reference](https://yankeguo.github.io/weavbot/en/cli/)
- 中文: [命令参考](https://yankeguo.github.io/weavbot/zh/cli/)

**完整文档：** [https://yankeguo.github.io/weavbot/](https://yankeguo.github.io/weavbot/)

## 致谢

本项目为 [nanobot](https://github.com/HKUDS/nanobot)（[HKUDS](https://github.com/HKUDS)）的硬分叉，并做了大量优化与改进。

## 许可证

MIT
