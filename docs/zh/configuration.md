---
layout: default
title: 配置
permalink: /zh/configuration/
parent: 中文
nav_order: 5
---

# 配置

配置文件：`~/.weavbot/config.json`。键均为 camelCase（如 `apiKey`、`allowFrom`）。环境变量以 `WB_` 前缀和 `__` 嵌套分隔符覆盖配置（如 `WB_AGENTS__DEFAULTS__MODEL`）。设置 `WB_LANG` 可通过 `weavbot.i18n` 覆盖 CLI 语言（`zh` 或 `en`）。

| 路径 | 说明 |
| --- | --- |
| 配置文件 | `~/.weavbot/config.json` |
| 工作区 | `~/.weavbot/workspace/` |
| 数据目录 | `~/.weavbot/` |
| 内置 bin | `~/.weavbot/bin/`（始终在代理工具 PATH 中） |
| 日志 | `~/.weavbot/logs/` |

## providers

对象。键为服务商名称（如 `anthropic`、`openrouter`）。每项：

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `mode` | `"openai"` \| `"anthropic"` | API 类型，默认 `"openai"` |
| `apiKey` | string | API 密钥 |
| `apiBase` | string（可选） | OpenAI 兼容 API 的 base URL |
| `extraHeaders` | object（可选） | 额外 HTTP 头 |

## agents.defaults

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `workspace` | string | `~/.weavbot/workspace` | 代理工作区路径 |
| `model` | string | — | 模型名（如 `claude-sonnet-4-20250514`） |
| `provider` | string | — | 需与 `providers` 中某键一致 |
| `maxTokens` | int | 8192 | 最大回复 token 数 |
| `temperature` | float | 0.1 | 采样温度 |
| `maxToolIterations` | int | 40 | 每轮最大工具调用次数 |
| `memoryWindow` | int | 100 | 对话窗口大小 |
| `reasoningEffort` | string \| null | null | 思考模式：`"low"` \| `"medium"` \| `"high"` |

## gateway

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `host` | string | `0.0.0.0` | 监听地址 |
| `port` | int | 18790 | 监听端口 |
| `heartbeat.enabled` | bool | true | 是否启用心跳服务 |
| `heartbeat.intervalS` | int | 1800 | 心跳间隔（秒） |

## tools

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `tools.web.proxy` | string \| null | null | 网页工具的 HTTP/SOCKS5 代理 |
| `tools.exec.timeout` | int | 60 | Shell 工具超时（秒） |
| `tools.exec.pathAppend` | string | `""` | Shell 的额外 PATH；`~/.weavbot/bin` 始终会 prepend |
| `tools.restrictToWorkspace` | bool | false | 将文件/Shell 工具限制在工作区内 |
| `tools.mcpServers` | object | {} | MCP 服务。键为名称。值：`command`、`args`、`env`（stdio）或 `url`、`headers`（HTTP）；`toolTimeout`、`disabledTools`、`enabledTools` |

## channels（全局）

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `channels.sendProgress` | bool | true | 向渠道流式输出代理文本进度 |
| `channels.sendToolHints` | bool | true | 向渠道流式输出工具调用提示 |

## channels.telegram

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否启用 |
| `token` | string | @BotFather 提供的 Bot Token |
| `allowFrom` | string[] | 允许的用户 ID 或用户名；空为全部允许 |
| `proxy` | string \| null | HTTP/SOCKS5 代理 URL |
| `replyToMessage` | bool | 回复时引用原消息 |

## channels.discord

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否启用 |
| `token` | string | Discord 开发者门户的 Bot Token |
| `allowFrom` | string[] | 允许的用户 ID；空为全部允许 |
| `gatewayUrl` | string | Discord 网关 URL |
| `intents` | int | 网关 intents 位掩码 |

## channels.feishu

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否启用 |
| `appId` | string | 飞书开放平台 App ID |
| `appSecret` | string | App Secret |
| `encryptKey` | string | 事件订阅加密密钥（可选） |
| `verificationToken` | string | 事件验证 Token（可选） |
| `allowFrom` | string[] | 允许的 open_id；空为全部允许 |
| `reactEmoji` | string | 表态表情类型（如 THUMBSUP、OK） |

## channels.dingtalk

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否启用 |
| `clientId` | string | AppKey |
| `clientSecret` | string | AppSecret |
| `allowFrom` | string[] | 允许的 staff_id；空为全部允许 |

## channels.slack

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否启用 |
| `mode` | string | 支持 `"socket"` |
| `webhookPath` | string | 事件 webhook 路径 |
| `botToken` | string | Bot Token（xoxb-...） |
| `appToken` | string | 应用级 Token（xapp-...） |
| `userTokenReadOnly` | bool | 使用只读用户 Token |
| `replyInThread` | bool | 在话题中回复 |
| `reactEmoji` | string | 表态表情（如 eyes） |
| `allowFrom` | string[] | 允许的发送者用户 ID；空为全部允许 |
| `groupPolicy` | string | `"mention"` \| `"open"` \| `"allowlist"` |
| `groupAllowFrom` | string[] | groupPolicy 为 allowlist 时允许的频道 ID；空为全部允许 |
| `dm.enabled` | bool | 是否启用私信 |
| `dm.policy` | string | `"open"` \| `"allowlist"` |
| `dm.allowFrom` | string[] | policy 为 allowlist 时允许的私信用户 ID；空为全部允许 |

## channels.qq

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否启用 |
| `appId` | string | q.qq.com 机器人 AppID |
| `secret` | string | 机器人密钥（AppSecret） |
| `allowFrom` | string[] | 允许的 openid；空为全部允许 |

## channels.email

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否启用 |
| `consentGranted` | bool | 用户同意访问邮箱 |
| `imapHost`、`imapPort`、`imapUsername`、`imapPassword` | string/int | IMAP（收信） |
| `imapMailbox` | string | 邮箱名（默认 INBOX） |
| `imapUseSsl` | bool | IMAP 使用 SSL |
| `smtpHost`、`smtpPort`、`smtpUsername`、`smtpPassword` | string/int | SMTP（发信） |
| `smtpUseTls`、`smtpUseSsl` | bool | SMTP TLS/SSL |
| `fromAddress` | string | 回复发件地址 |
| `autoReplyEnabled` | bool | 是否自动回复 |
| `pollIntervalSeconds` | int | 轮询间隔 |
| `markSeen` | bool | 是否标为已读 |
| `maxBodyChars` | int | 正文最大长度 |
| `subjectPrefix` | string | 回复主题前缀 |
| `allowFrom` | string[] | 允许的发件人；空为全部允许 |

## channels.mochat

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否启用 |
| `baseUrl` | string | Mochat API 基础 URL |
| `socketUrl`、`socketPath` | string | Socket.IO 端点 |
| `clawToken` | string | Claw Token |
| `agentUserId` | string | 代理用户 ID |
| `sessions`、`panels` | string[] | 会话/面板过滤 |
| `allowFrom` | string[] | 允许的用户；空为全部允许 |
| `mention.requireInGroups` | bool | 群聊是否要求 @ |
| `groups` | object | 按群规则（如 requireMention） |
| `replyDelayMode` | string | `"off"` \| `"non-mention"` |
| `replyDelayMs` | int | 非 @ 回复延迟（毫秒） |
| Socket/重试选项 | — | `socketReconnectDelayMs`、`socketMaxReconnectDelayMs`、`socketConnectTimeoutMs`、`refreshIntervalMs`、`watchTimeoutMs`、`watchLimit`、`retryDelayMs`、`maxRetryAttempts` |

[命令参考]({{ site.baseurl }}/zh/cli/) | [快速开始]({{ site.baseurl }}/zh/quick-start/)
