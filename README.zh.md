# weavbot

轻量级个人 AI 助手框架。

[English](README.md)

## 安装

```bash
uv tool install git+https://github.com/yankeguo/weavbot.git
```

验证：

```bash
weavbot --version
```

## 快速开始

### 1. 初始化

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

### 2. 配置

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

所有渠道与工具配置见下方[配置说明](#配置)一节。

### 3. 运行

```bash
weavbot gateway
```

将启动常驻网关，管理代理、渠道、定时任务与心跳。

## 开机自启

交互式配置（`weavbot onboard`）可代为配置自启，也可手动配置：

### Linux（systemd）

向导会写入用户级服务到 `~/.config/systemd/user/weavbot.service`，并通过 `systemctl --user enable --now weavbot.service` 启用。

### macOS（launchd）

向导会写入 LaunchAgent 到 `~/Library/LaunchAgents/com.weavbot.gateway.plist` 并用 `launchctl load` 加载。

### Windows（traycli）

向导会下载 [traycli](https://github.com/yankeguo/traycli) 到 `~/.weavbot/bin/traycli.exe`，写入 `~/.traycli/config.json` 并创建启动快捷方式。traycli 以系统托盘应用形式运行 `weavbot gateway`，无控制台窗口。

## 命令参考

| 命令 | 说明 |
| --- | --- |
| `weavbot onboard [--set key=value]` | 初始化配置与工作区 |
| `weavbot gateway [-p/--port 18790]` | 启动网关 |
| `weavbot agent` | 交互式对话 |
| `weavbot agent -m "..."` | 发送单条消息 |
| `weavbot status` | 查看状态 |
| `weavbot channels status` | 查看渠道状态 |

## 配置

配置文件：`~/.weavbot/config.json`。键均为 camelCase（如 `apiKey`、`allowFrom`）。环境变量以 `WB_` 前缀和 `__` 嵌套分隔符覆盖配置（如 `WB_AGENTS__DEFAULTS__MODEL`）。设置 `WB_LANG` 可通过 `weavbot.i18n` 覆盖 CLI 语言（`zh` 或 `en`）。

| 路径 | 说明 |
| --- | --- |
| 配置文件 | `~/.weavbot/config.json` |
| 工作区 | `~/.weavbot/workspace/` |
| 数据目录 | `~/.weavbot/` |
| 内置 bin | `~/.weavbot/bin/`（始终在代理工具 PATH 中） |
| 日志 | `~/.weavbot/logs/` |

### providers

对象。键为服务商名称（如 `anthropic`、`openrouter`）。每项：

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `mode` | `"openai"` \| `"anthropic"` | API 类型，默认 `"openai"` |
| `apiKey` | string | API 密钥 |
| `apiBase` | string（可选） | OpenAI 兼容 API 的 base URL |
| `extraHeaders` | object（可选） | 额外 HTTP 头 |

### agents.defaults

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

### gateway

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `host` | string | `0.0.0.0` | 监听地址 |
| `port` | int | 18790 | 监听端口 |
| `heartbeat.enabled` | bool | true | 是否启用心跳服务 |
| `heartbeat.intervalS` | int | 1800 | 心跳间隔（秒） |

### tools

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `tools.web.proxy` | string \| null | null | 网页工具的 HTTP/SOCKS5 代理 |
| `tools.exec.timeout` | int | 60 | Shell 工具超时（秒） |
| `tools.exec.pathAppend` | string | `""` | Shell 的额外 PATH；`~/.weavbot/bin` 始终会 prepend |
| `tools.restrictToWorkspace` | bool | false | 将文件/Shell 工具限制在工作区内 |
| `tools.mcpServers` | object | {} | MCP 服务。键为名称。值：`command`、`args`、`env`（stdio）或 `url`、`headers`（HTTP）；`toolTimeout`、`disabledTools`、`enabledTools` |

### channels（全局）

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `channels.sendProgress` | bool | true | 向渠道流式输出代理文本进度 |
| `channels.sendToolHints` | bool | true | 向渠道流式输出工具调用提示 |

### channels.telegram

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否启用 |
| `token` | string | @BotFather 提供的 Bot Token |
| `allowFrom` | string[] | 允许的用户 ID 或用户名；空为全部允许 |
| `proxy` | string \| null | HTTP/SOCKS5 代理 URL |
| `replyToMessage` | bool | 回复时引用原消息 |

### channels.discord

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否启用 |
| `token` | string | Discord 开发者门户的 Bot Token |
| `allowFrom` | string[] | 允许的用户 ID；空为全部允许 |
| `gatewayUrl` | string | Discord 网关 URL |
| `intents` | int | 网关 intents 位掩码 |

### channels.feishu

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否启用 |
| `appId` | string | 飞书开放平台 App ID |
| `appSecret` | string | App Secret |
| `encryptKey` | string | 事件订阅加密密钥（可选） |
| `verificationToken` | string | 事件验证 Token（可选） |
| `allowFrom` | string[] | 允许的 open_id；空为全部允许 |
| `reactEmoji` | string | 表态表情类型（如 THUMBSUP、OK） |

### channels.dingtalk

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否启用 |
| `clientId` | string | AppKey |
| `clientSecret` | string | AppSecret |
| `allowFrom` | string[] | 允许的 staff_id；空为全部允许 |

### channels.slack

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

### channels.qq

| 键 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | bool | 是否启用 |
| `appId` | string | q.qq.com 机器人 AppID |
| `secret` | string | 机器人密钥（AppSecret） |
| `allowFrom` | string[] | 允许的 openid；空为全部允许 |

### channels.email

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

### channels.mochat

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

## 致谢

本项目为 [nanobot](https://github.com/HKUDS/nanobot)（[HKUDS](https://github.com/HKUDS)）的硬分叉。

## 许可证

MIT
