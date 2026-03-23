# weavbot

[![GitHub Actions](https://github.com/yankeguo/weavbot/actions/workflows/ci.yml/badge.svg)](https://github.com/yankeguo/weavbot/actions)
[![PyPI](https://img.shields.io/pypi/v/weavbot)](https://pypi.org/project/weavbot/)
[![Docs (English)](https://img.shields.io/badge/docs-English-blue)](https://yankeguo.github.io/weavbot/en/)
[![Docs (中文)](https://img.shields.io/badge/文档-中文-blue)](https://yankeguo.github.io/weavbot/zh/)

轻量级个人 AI 助手框架。

[English](./README.md)

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

## 初始化（推荐首次运行）

初始化本地配置/工作区并启动交互式向导：

```bash
weavbot onboard
```

`onboard` 会执行：

- 创建 `~/.weavbot/config.json` 和 `~/.weavbot/workspace/`
- 引导选择 provider/model（支持实时过滤）
- 在向导中配置一个聊天渠道（Telegram/Discord/Feishu/DingTalk/Slack/QQ/Wecom/Email/Mochat/Wechat）
- 可选安装 `ripgrep` 与配置网关开机自启

脚本化场景可使用可重复的 `--set key=value`：

```bash
weavbot onboard \
  --set providers.openrouter.apiKey=sk-or-v1-xxx \
  --set providers.openrouter.apiBase=https://openrouter.ai/api/v1 \
  --set agents.defaults.provider=openrouter \
  --set agents.defaults.model=openai/gpt-4o-mini
```

详细命令文档：

- English: [CLI Reference](https://yankeguo.github.io/weavbot/en/cli/)
- 中文: [命令参考](https://yankeguo.github.io/weavbot/zh/cli/)

**完整文档：** [https://yankeguo.github.io/weavbot/](https://yankeguo.github.io/weavbot/)

## 微信渠道配置

微信渠道建议分两步：

1. 在配置中启用渠道（`onboard` 对微信只做占位启用）：
   - `channels.wechat.enabled=true`
2. 使用独立命令完成扫码登录与凭据绑定：

```bash
weavbot wechat login
```

多账号时，将账号配置写入 `channels.wechat.accounts`，并可用 `channels.wechat.enabledAccounts` 控制当前运行哪些账号。

配置参考：

- 中文: [微信配置](https://yankeguo.github.io/weavbot/zh/configuration/#channelswechat)
- English: [Wechat config](https://yankeguo.github.io/weavbot/en/configuration/#channelswechat)

## 致谢

本项目为 [nanobot](https://github.com/HKUDS/nanobot)（[HKUDS](https://github.com/HKUDS)）的硬分叉，并做了大量优化与改进。

## 许可证

MIT
