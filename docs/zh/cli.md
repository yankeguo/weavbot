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
| `weavbot gateway [-p/--port 18790]` | 启动网关 |
| `weavbot agent` | 交互式对话 |
| `weavbot agent -m "..."` | 发送单条消息 |
| `weavbot status` | 查看状态 |
| `weavbot channels status` | 查看渠道状态 |

## 聊天命令

在交互式对话或任意聊天渠道（Telegram、Discord 等）中可使用斜杠命令：

| 命令 | 说明 |
| --- | --- |
| `/new` | 开始新对话（先归档长期记忆，再清空会话） |
| `/stop` | 停止当前正在执行的任务（含子代理） |
| `/help` | 显示可用命令 |

[快速开始]({{ site.baseurl }}/zh/quick-start/) | [配置]({{ site.baseurl }}/zh/configuration/)
