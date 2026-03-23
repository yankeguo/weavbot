---
layout: default
title: 开机自启
permalink: /zh/auto-start/
parent: 中文
nav_order: 4
---

# 开机自启

交互式配置（`weavbot onboard`）可以帮你写入自启配置，但不会自动启动网关；向导会输出可手动执行的命令。

## Linux（systemd）

向导会写入用户级服务到 `~/.config/systemd/user/weavbot.service` 并启用。

执行 `onboard` 后，可手动运行：

```bash
systemctl --user daemon-reload
systemctl --user enable weavbot.service
systemctl --user start weavbot.service
```

## macOS（launchd）

向导会写入 LaunchAgent 到 `~/Library/LaunchAgents/com.weavbot.gateway.plist`。

执行 `onboard` 后，可手动运行：

```bash
launchctl load ~/Library/LaunchAgents/com.weavbot.gateway.plist
```

## Windows（traycli）

向导会下载 [traycli](https://github.com/yankeguo/traycli) 到 `~/.weavbot/bin/traycli.exe`，写入 `~/.traycli/config.json` 并创建启动快捷方式。

执行 `onboard` 后，可手动运行：

```powershell
~/.weavbot/bin/traycli.exe
```

[快速开始]({{ site.baseurl }}/zh/quick-start/) | [命令参考]({{ site.baseurl }}/zh/cli/)
