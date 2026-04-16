---
layout: default
title: 配置
permalink: /zh/configuration/
parent: 中文
nav_order: 6
---

# 配置

数据根目录由 `WB_DATA_PATH` 控制（默认 `~/.weavbot`）。配置文件路径为 `WB_DATA_PATH/config.json`。键均为 camelCase（如 `apiKey`、`allowFrom`）。环境变量以 `WB_` 前缀和 `__` 嵌套分隔符覆盖配置（如 `WB_AGENTS__DEFAULTS__MODEL`）。设置 `WB_LANG` 可通过 `weavbot.i18n` 覆盖 CLI 语言（`zh` 或 `en`）。

| 路径 | 说明 |
| --- | --- |
| 配置文件 | `WB_DATA_PATH/config.json`（默认 `~/.weavbot/config.json`） |
| 工作区 | 默认 `WB_DATA_PATH/workspace/` |
| 数据目录 | `WB_DATA_PATH/`（默认 `~/.weavbot/`） |
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

Anthropic 说明：

- 如果服务端是 Anthropic 兼容网关（非原生 Anthropic），且支持 OpenAI 风格接口，优先使用 `mode: "openai"`。
- 若必须以 `mode: "anthropic"` 访问兼容网关（例如 Bailian Anthropic endpoint），请配置 `apiBase` 并开启调试日志检查请求体兼容性。
- Anthropic 模式调试环境变量：
  - `WB_DEBUG_ANTHROPIC=1`：输出脱敏后的请求摘要与详情。
  - `WB_ANTHROPIC_CACHE_CONTROL=0`：强制关闭 `cache_control` 字段，提升兼容网关通过率。

OpenAI 兼容模式说明：

- `mode: "openai"` 调试环境变量：
  - `WB_DEBUG_OPENAI=1`：输出脱敏后的请求摘要与详情，并在失败时输出失败请求参数详情。

## agents.defaults

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `workspace` | string | `workspace` | 代理工作区路径（相对路径会基于 `WB_DATA_PATH` 解析） |
| `model` | string | `anthropic/claude-opus-4-5` | 模型名（如 `claude-sonnet-4-20250514`） |
| `provider` | string | — | 需与 `providers` 中某键一致 |
| `maxTokens` | int | 8192 | 最大回复 token 数 |
| `maxContext` | int | 131072 | 上下文窗口大小 |
| `temperature` | float | 0.1 | 采样温度 |
| `maxToolIterations` | int | 40 | 每轮最大工具调用次数 |
| `reasoningEffort` | string \| null | null | 思考模式：`"low"` \| `"medium"` \| `"high"` |

## gateway

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
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

## channels.wecom

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否启用 |
| `botId` | string | 企业微信管理后台中的机器人 ID |
| `secret` | string | 长连接密钥 |
| `wsUrl` | string | WebSocket 地址（默认 `wss://openws.work.weixin.qq.com`） |
| `heartbeatIntervalSec` | int | 心跳间隔（秒） |
| `maxMissedPong` | int | 连续未收到 pong 的最大次数，超过后重连 |
| `reconnectBaseMs` | int | 断线重连基础退避时间（毫秒） |
| `reconnectMaxMs` | int | 断线重连最大退避时间（毫秒） |
| `maxReconnectAttempts` | int | 最大重连次数，`-1` 表示无限重试 |
| `requestTimeoutSec` | int | 请求超时（秒） |
| `singleInstanceGuard` | bool | 启用单实例守护，避免重复实例接入 |
| `allowFrom` | string[] | 允许的用户 ID；空为全部允许 |
| `perChatPerMinute` | int | 每个会话每分钟限流阈值 |
| `perChatPerHour` | int | 每个会话每小时限流阈值 |
| `uploadChunkSize` | int | 媒体上传分片大小（字节） |

## channels.wechat

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否启用 |
| `accountId` | string | 默认账号 ID（使用 `accounts` 时可不填） |
| `token` | string | 默认账号 token（使用 `accounts` 时可不填） |
| `routeTag` | string | 可选 `SKRouteTag` 请求头 |
| `allowFrom` | string[] | 允许的发送者 ID；空为全部允许 |
| `requestTimeoutSec` | int | HTTP 请求超时（秒） |
| `longPollTimeoutMs` | int | getUpdates 长轮询超时（毫秒） |
| `pollRetryDelayMs` | int | 轮询失败后的重试延迟（毫秒） |
| `maxConsecutiveFailures` | int | 连续失败退避阈值 |
| `sessionPauseMinutes` | int | 服务端返回会话过期（`-14`）后的暂停窗口（分钟） |
| `typingKeepaliveSec` | int | 输入状态保活间隔提示值 |
| `enabledAccounts` | string[] | 可选，限定启动的账号 key 列表 |
| `accounts` | object | 多账号映射。每个账号支持：`enabled`、`accountId`、`token`、`routeTag`、`allowFrom` |

说明：

- `weavbot onboard` 对 Wechat 仅做占位启用（`channels.wechat.enabled=true`），不执行二维码登录。
- 完成 onboarding 后，请执行 `weavbot wechat login` 扫码并保存账号凭据。
- 多账号共享同一 workspace，但会话键按账号 + 对端隔离。

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
| `socketDisableMsgpack` | bool | 禁用 Socket.IO 的 msgpack 序列化 |
| Socket/重试选项 | — | `socketReconnectDelayMs`、`socketMaxReconnectDelayMs`、`socketConnectTimeoutMs`、`refreshIntervalMs`、`watchTimeoutMs`、`watchLimit`、`retryDelayMs`、`maxRetryAttempts` |

[命令参考]({{ site.baseurl }}/zh/cli/) | [快速开始]({{ site.baseurl }}/zh/quick-start/)
