---
layout: default
title: Auto-Start
permalink: /en/auto-start/
parent: English
nav_order: 4
---

# Auto-Start

The interactive setup (`weavbot onboard`) can configure auto-start for you. You can also set it up manually:

## Linux (systemd)

The wizard writes a user-level service to `~/.config/systemd/user/weavbot.service` and enables it with `systemctl --user enable --now weavbot.service`.

## macOS (launchd)

The wizard writes a LaunchAgent to `~/Library/LaunchAgents/com.weavbot.gateway.plist` and loads it with `launchctl load`.

## Windows (traycli)

The wizard downloads [traycli](https://github.com/yankeguo/traycli) to `~/.weavbot/bin/traycli.exe`, writes `~/.traycli/config.json`, and creates a startup shortcut. traycli keeps `weavbot gateway` running as a system tray application with no console window.

[Quick Start]({{ site.baseurl }}/en/quick-start/) | [CLI Reference]({{ site.baseurl }}/en/cli/)
