---
layout: default
title: 开机自启
permalink: /zh/auto-start/
---

# 开机自启

交互式配置（`weavbot onboard`）可代为配置自启，也可手动配置：

## Linux（systemd）

向导会写入用户级服务到 `~/.config/systemd/user/weavbot.service`，并通过 `systemctl --user enable --now weavbot.service` 启用。

## macOS（launchd）

向导会写入 LaunchAgent 到 `~/Library/LaunchAgents/com.weavbot.gateway.plist` 并用 `launchctl load` 加载。

## Windows（traycli）

向导会下载 [traycli](https://github.com/yankeguo/traycli) 到 `~/.weavbot/bin/traycli.exe`，写入 `~/.traycli/config.json` 并创建启动快捷方式。traycli 以系统托盘应用形式运行 `weavbot gateway`，无控制台窗口。

[快速开始](quick-start) | [命令参考](cli)
