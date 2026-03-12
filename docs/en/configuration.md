---
layout: default
title: Configuration
permalink: /en/configuration/
parent: English
nav_order: 5
---

# Configuration

Config file: `~/.weavbot/config.json`. All keys use camelCase (e.g. `apiKey`, `allowFrom`). Environment variables override config with the `WB_` prefix and `__` as the nesting delimiter (e.g. `WB_AGENTS__DEFAULTS__MODEL`). Set `WB_LANG` to override CLI language (`zh` or `en`) via `weavbot.i18n`.

| Path | Description |
| --- | --- |
| Config file | `~/.weavbot/config.json` |
| Workspace | `~/.weavbot/workspace/` |
| Data directory | `~/.weavbot/` |
| Built-in bin | `~/.weavbot/bin/` (always in agent tool PATH) |
| Logs | `~/.weavbot/logs/` |

## providers

Object. Key = provider name (e.g. `anthropic`, `openrouter`). Each entry:

| Key | Type | Description |
| --- | --- | --- |
| `mode` | `"openai"` \| `"anthropic"` | API style; default `"openai"` |
| `apiKey` | string | API key |
| `apiBase` | string (optional) | Base URL for OpenAI-compatible APIs |
| `extraHeaders` | object (optional) | Extra HTTP headers |

## agents.defaults

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `workspace` | string | `~/.weavbot/workspace` | Agent workspace path |
| `model` | string | — | Model name (e.g. `claude-sonnet-4-20250514`) |
| `provider` | string | — | Must match a key in `providers` |
| `maxTokens` | int | 8192 | Max response tokens |
| `temperature` | float | 0.1 | Sampling temperature |
| `maxToolIterations` | int | 40 | Max tool-call rounds per turn |
| `memoryWindow` | int | 100 | Conversation window size |
| `reasoningEffort` | string \| null | null | `"low"` \| `"medium"` \| `"high"` for thinking mode |

## gateway

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `host` | string | `0.0.0.0` | Bind address |
| `port` | int | 18790 | Bind port |
| `heartbeat.enabled` | bool | true | Enable heartbeat service |
| `heartbeat.intervalS` | int | 1800 | Heartbeat interval (seconds) |

## tools

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `tools.web.proxy` | string \| null | null | HTTP/SOCKS5 proxy for web tools |
| `tools.exec.timeout` | int | 60 | Shell tool timeout (seconds) |
| `tools.exec.pathAppend` | string | `""` | Extra PATH for shell; `~/.weavbot/bin` is always prepended |
| `tools.restrictToWorkspace` | bool | false | Restrict file/shell tools to workspace |
| `tools.mcpServers` | object | {} | MCP servers. Key = name. Value: `command`, `args`, `env` (stdio) or `url`, `headers` (HTTP); `toolTimeout`, `disabledTools`, `enabledTools` |

## channels (global)

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `channels.sendProgress` | bool | true | Stream agent text progress to channel |
| `channels.sendToolHints` | bool | true | Stream tool-call hints to channel |

## channels.telegram

| Key | Type | Description |
| --- | --- | --- |
| `enabled` | bool | Enable channel |
| `token` | string | Bot token from @BotFather |
| `allowFrom` | string[] | Allowed user IDs or usernames; empty = allow all |
| `proxy` | string \| null | HTTP/SOCKS5 proxy URL |
| `replyToMessage` | bool | Quote original message in replies |

## channels.discord

| Key | Type | Description |
| --- | --- | --- |
| `enabled` | bool | Enable channel |
| `token` | string | Bot token from Discord Developer Portal |
| `allowFrom` | string[] | Allowed user IDs; empty = allow all |
| `gatewayUrl` | string | Discord gateway URL |
| `intents` | int | Gateway intents bitmask |

## channels.feishu

| Key | Type | Description |
| --- | --- | --- |
| `enabled` | bool | Enable channel |
| `appId` | string | Feishu Open Platform App ID |
| `appSecret` | string | App Secret |
| `encryptKey` | string | Event subscription encrypt key (optional) |
| `verificationToken` | string | Event verification token (optional) |
| `allowFrom` | string[] | Allowed open_ids; empty = allow all |
| `reactEmoji` | string | Reaction emoji type (e.g. THUMBSUP, OK) |

## channels.dingtalk

| Key | Type | Description |
| --- | --- | --- |
| `enabled` | bool | Enable channel |
| `clientId` | string | AppKey |
| `clientSecret` | string | AppSecret |
| `allowFrom` | string[] | Allowed staff_ids; empty = allow all |

## channels.slack

| Key | Type | Description |
| --- | --- | --- |
| `enabled` | bool | Enable channel |
| `mode` | string | `"socket"` supported |
| `webhookPath` | string | Events webhook path |
| `botToken` | string | Bot token (xoxb-...) |
| `appToken` | string | App-level token (xapp-...) |
| `userTokenReadOnly` | bool | Use read-only user token |
| `replyInThread` | bool | Reply in thread |
| `reactEmoji` | string | Reaction emoji (e.g. eyes) |
| `allowFrom` | string[] | Allowed sender user IDs; empty = allow all |
| `groupPolicy` | string | `"mention"` \| `"open"` \| `"allowlist"` |
| `groupAllowFrom` | string[] | Allowed channel IDs when groupPolicy is allowlist; empty = allow all |
| `dm.enabled` | bool | Enable DMs |
| `dm.policy` | string | `"open"` \| `"allowlist"` |
| `dm.allowFrom` | string[] | Allowed DM user IDs when policy is allowlist; empty = allow all |

## channels.qq

| Key | Type | Description |
| --- | --- | --- |
| `enabled` | bool | Enable channel |
| `appId` | string | Robot AppID from q.qq.com |
| `secret` | string | Robot secret (AppSecret) |
| `allowFrom` | string[] | Allowed openids; empty = allow all |

## channels.email

| Key | Type | Description |
| --- | --- | --- |
| `enabled` | bool | Enable channel |
| `consentGranted` | bool | Owner consent to access mailbox |
| `imapHost`, `imapPort`, `imapUsername`, `imapPassword` | string/int | IMAP (receive) |
| `imapMailbox` | string | Mailbox name (default INBOX) |
| `imapUseSsl` | bool | Use SSL for IMAP |
| `smtpHost`, `smtpPort`, `smtpUsername`, `smtpPassword` | string/int | SMTP (send) |
| `smtpUseTls`, `smtpUseSsl` | bool | SMTP TLS/SSL |
| `fromAddress` | string | From address for replies |
| `autoReplyEnabled` | bool | Send automatic replies |
| `pollIntervalSeconds` | int | Poll interval |
| `markSeen` | bool | Mark messages read |
| `maxBodyChars` | int | Max body length |
| `subjectPrefix` | string | Reply subject prefix |
| `allowFrom` | string[] | Allowed sender addresses; empty = allow all |

## channels.mochat

| Key | Type | Description |
| --- | --- | --- |
| `enabled` | bool | Enable channel |
| `baseUrl` | string | Mochat API base URL |
| `socketUrl`, `socketPath` | string | Socket.IO endpoint |
| `clawToken` | string | Claw token |
| `agentUserId` | string | Agent user ID |
| `sessions`, `panels` | string[] | Session/panel filters |
| `allowFrom` | string[] | Allowed users; empty = allow all |
| `mention.requireInGroups` | bool | Require @ in groups |
| `groups` | object | Per-group rules (e.g. requireMention) |
| `replyDelayMode` | string | `"off"` \| `"non-mention"` |
| `replyDelayMs` | int | Delay for non-mention replies |
| Socket/retry options | — | `socketReconnectDelayMs`, `socketMaxReconnectDelayMs`, `socketConnectTimeoutMs`, `refreshIntervalMs`, `watchTimeoutMs`, `watchLimit`, `retryDelayMs`, `maxRetryAttempts` |

[CLI Reference]({{ site.baseurl }}/en/cli/) | [Quick Start]({{ site.baseurl }}/en/quick-start/)
