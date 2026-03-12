---
layout: default
title: 快速开始
permalink: /zh/quick-start/
---

# 快速开始

## 1. 初始化

```bash
weavbot onboard
```

会创建 `~/.weavbot/config.json` 和 `~/.weavbot/workspace/`，并启动**交互式配置向导**，依次完成：

1. **服务商选择** — 从 [models.dev](https://models.dev) 拉取已知服务商与模型，选择服务商、模型并填写 API 密钥
2. **渠道配置** — 配置聊天渠道（Telegram、Discord、飞书、钉钉、Slack、QQ、Email、Mochat）的凭证
3. **依赖安装** — 检测并在缺失时安装 [ripgrep](https://github.com/BurntSushi/ripgrep)（代理文件搜索工具所需）到 `~/.weavbot/bin/`
4. **开机自启** — 配置网关在登录后自动启动（Linux 用 systemd，macOS 用 launchd，Windows 用 [traycli](https://github.com/yankeguo/traycli)）

向导会根据系统语言自动选择提示语言，必要时显示中文。可通过 `WB_LANG=en` 或 `WB_LANG=zh` 覆盖。
CLI 翻译已拆分到独立的 `weavbot.i18n` 包，当前采用 `cli.setup.*` 与 `cli.commands.*` 这类 key 命名空间，便于后续扩展。

也可使用 `--set` 在命令行内联配置（可重复，类似 Helm）：

```bash
weavbot onboard \
  --set providers.anthropic.apiKey=sk-ant-xxx \
  --set providers.anthropic.mode=anthropic \
  --set agents.defaults.model=claude-sonnet-4-20250514 \
  --set agents.defaults.provider=anthropic
```

键为与 JSON 配置结构对应的点分 camelCase 路径，值会自动推断类型（数字、布尔、null）或按字符串处理。

## 2. 配置

也可直接编辑 `~/.weavbot/config.json` 设置 API 密钥和模型。

服务商为扁平对象，键为自定名称，每项包含 `mode`（`"openai"` 或 `"anthropic"`）及凭证：

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

- `mode` 默认为 `"openai"`（OpenAI 兼容 API），设为 `"anthropic"` 使用原生 Anthropic API
- `agents.defaults.provider` 必须与 `providers` 中的某个键一致

所有渠道与工具配置见[配置说明](configuration)一节。

## 3. 运行

```bash
weavbot gateway
```

将启动常驻网关，管理代理、渠道、定时任务与心跳。

[安装](install) | [开机自启](auto-start) | [命令参考](cli)
