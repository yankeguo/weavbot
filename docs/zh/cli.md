---
layout: default
title: 命令参考
permalink: /zh/cli/
parent: 中文
nav_order: 5
---

# 命令参考

| 命令 | 说明 |
| --- | --- |
| `weavbot onboard [--set key=value]` | 初始化配置与工作区 |
| `weavbot gateway` | 启动网关 |
| `weavbot agent` | 交互式对话 |
| `weavbot agent -m "..."` | 发送单条消息 |

## `weavbot onboard`

安装后建议第一条执行命令就是 `onboard`。

```bash
weavbot onboard
```

### 初始化内容

- 创建 `WB_HOME/config.json`（默认 `~/.weavbot/config.json`）
- 创建 `WB_HOME/workspace/`（默认 `~/.weavbot/workspace/`）
- 启动服务商/模型/渠道的交互式配置向导
- 可选安装 ripgrep 与配置开机自启

### 交互选择行为

- **实时过滤：** 服务商、模型、渠道选择都支持方向键移动与输入过滤。
- **渠道单选：** 每次向导只选择一个渠道，随后填写该渠道字段。
- **Ctrl+C 语义：**
  - 服务商选择：跳过服务商配置
  - 模型选择：回到服务商选择
  - 渠道选择与字段输入：跳过渠道配置
- **兼容模式回退：** 若实时选择器不可用（例如非 TTY 终端），自动回退到数字编号选择模式。

### `--set` 脚本化配置

可重复传入 `--set key=value`，用于非交互或自动化场景：

```bash
weavbot onboard \
  --set providers.openrouter.apiKey=sk-or-v1-xxx \
  --set providers.openrouter.apiBase=https://openrouter.ai/api/v1 \
  --set providers.openrouter.mode=openai \
  --set agents.defaults.provider=openrouter \
  --set agents.defaults.model=openai/gpt-4o-mini
```

值会尽量自动推断类型（`true`、`false`、数字、`null`），其余按字符串处理。

## 聊天命令

在交互式对话或任意聊天渠道（Telegram、Discord 等）中可使用斜杠命令：

| 命令 | 说明 |
| --- | --- |
| `/new` | 开始新对话（先归档长期记忆，再清空会话） |
| `/stop` | 停止当前正在执行的任务（含子代理） |
| `/help` | 显示可用命令 |

[快速开始]({{ site.baseurl }}/zh/quick-start/) | [配置]({{ site.baseurl }}/zh/configuration/)
