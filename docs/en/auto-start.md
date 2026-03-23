---
layout: default
title: Auto-Start
permalink: /en/auto-start/
parent: English
nav_order: 4
---

# Auto-Start

The interactive setup (`weavbot onboard`) can write auto-start configuration for you, but it does not start the gateway automatically. It prints the command(s) you can run manually.

## Linux (systemd)

The wizard writes a user-level service to `~/.config/systemd/user/weavbot.service` and enables it.

After onboarding, run:

```bash
systemctl --user daemon-reload
systemctl --user enable weavbot.service
systemctl --user start weavbot.service
```

## macOS (launchd)

The wizard writes a LaunchAgent to `~/Library/LaunchAgents/com.weavbot.gateway.plist`.

After onboarding, run:

```bash
launchctl load ~/Library/LaunchAgents/com.weavbot.gateway.plist
```

## Windows (traycli)

The wizard downloads [traycli](https://github.com/yankeguo/traycli) to `~/.weavbot/bin/traycli.exe`, writes `~/.traycli/config.json`, and creates a startup shortcut.

After onboarding, run:

```powershell
~/.weavbot/bin/traycli.exe
```

[Quick Start]({{ site.baseurl }}/en/quick-start/) | [CLI Reference]({{ site.baseurl }}/en/cli/)
