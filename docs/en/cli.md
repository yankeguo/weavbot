---
layout: default
title: CLI Reference
permalink: /en/cli/
parent: English
nav_order: 5
---

# CLI Reference

| Command | Description |
| --- | --- |
| `weavbot onboard [--set key=value]` | Initialize config and workspace |
| `weavbot gateway` | Start the gateway |
| `weavbot agent` | Interactive chat mode |
| `weavbot agent -m "..."` | Send a single message |
| `weavbot status` | Show status |
| `weavbot channels status` | Show channel status |

## Chat Commands

In interactive mode or any chat channel (Telegram, Discord, etc.), you can use slash commands:

| Command | Description |
| --- | --- |
| `/new` | Start a new conversation (archive long-term memory first, then clear the session) |
| `/stop` | Stop the current running task (including subagents) |
| `/help` | Show available commands |

[Quick Start]({{ site.baseurl }}/en/quick-start/) | [Configuration]({{ site.baseurl }}/en/configuration/)
