"""Interactive provider configuration wizard for the onboard command."""

from __future__ import annotations

import copy
import io
import json as _json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from weavbot.config.schema import Config
from weavbot.i18n import t

MODELS_DEV_URL = "https://models.dev/api.json"


def _t(key: str, *args: Any) -> str:
    return t(f"cli.setup.{key}", *args)


_NPM_TO_MODE: dict[str, str] = {
    "@ai-sdk/anthropic": "anthropic",
    "@ai-sdk/openai": "openai",
    "@ai-sdk/openai-compatible": "openai",
}


def _fetch_providers(console: Console) -> dict[str, Any] | None:
    """Fetch the models.dev provider catalogue. Returns None on failure."""
    with console.status(f"[dim]{_t('fetching')}[/dim]", spinner="dots"):
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(MODELS_DEV_URL)
                resp.raise_for_status()
                return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            console.print(f"[red]{_t('fetch_failed')}:[/red] {exc}")
            console.print(f"[dim]{_t('fetch_fallback')}[/dim]")
            return None


def _compatible_providers(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Filter and sort providers compatible with weavbot's openai/anthropic modes."""
    results: list[dict[str, Any]] = []
    for key, data in raw.items():
        npm = data.get("npm", "")
        if npm not in _NPM_TO_MODE:
            continue
        models = data.get("models") or {}
        tool_models = {mid: m for mid, m in models.items() if m.get("tool_call")}
        if not tool_models:
            continue
        results.append(
            {
                "key": key,
                "id": data.get("id", key),
                "name": data.get("name", key),
                "npm": npm,
                "api": data.get("api"),
                "doc": data.get("doc"),
                "models": tool_models,
            }
        )
    results.sort(key=lambda p: p["name"].lower())
    return results


def _format_limit(value: int | None) -> str:
    if value is None:
        return "-"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}K"
    return str(value)


def _prompt_number(prompt_text: str, max_val: int) -> int | None:
    """Prompt for a 1-based number. Returns None if user wants to cancel."""
    while True:
        raw = typer.prompt(prompt_text, default="")
        if not raw:
            return None
        try:
            n = int(raw)
        except ValueError:
            typer.echo(_t("enter_number", max_val))
            continue
        if 1 <= n <= max_val:
            return n
        typer.echo(_t("enter_number", max_val))


def _select_provider(providers: list[dict[str, Any]], console: Console) -> dict[str, Any] | None:
    """Display provider list, support search and selection. Returns chosen provider or None."""
    filtered = providers

    while True:
        table = Table(title=_t("available_providers"), show_lines=False)
        table.add_column("#", style="dim", width=4, justify="right")
        table.add_column(_t("table_id"), style="cyan")
        table.add_column(_t("table_name"))
        table.add_column(_t("table_mode"), style="green")
        table.add_column(_t("table_models"), justify="right")

        for idx, p in enumerate(filtered, 1):
            mode = _NPM_TO_MODE.get(p["npm"], "?")
            table.add_row(
                str(idx),
                p["id"],
                p["name"],
                mode,
                str(len(p["models"])),
            )

        console.print()
        console.print(table)
        console.print(f"[dim]{_t('provider_hint')}[/dim]")

        raw = typer.prompt(_t("provider"), default="")
        if not raw:
            return None

        # Try number selection
        try:
            n = int(raw)
            if 1 <= n <= len(filtered):
                return filtered[n - 1]
        except ValueError:
            pass

        # Text search — filter and loop
        query = raw.lower()
        filtered = [p for p in providers if query in p["name"].lower() or query in p["id"].lower()]
        if not filtered:
            console.print(f"[yellow]{_t('no_match', raw)}[/yellow]")
            filtered = providers
        elif len(filtered) == 1:
            return filtered[0]


def _select_model(provider: dict[str, Any], console: Console) -> tuple[str, dict[str, Any]] | None:
    """Display model list for a provider. Returns (model_id, model_data) or None."""
    models = provider["models"]
    entries = list(models.items())
    entries.sort(key=lambda e: e[1].get("name", e[0]).lower())

    table = Table(title=_t("models_title", provider["name"]), show_lines=False)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column(_t("table_id"), style="cyan")
    table.add_column(_t("table_name"))
    table.add_column(_t("context"), justify="right")
    table.add_column(_t("max_output"), justify="right")
    table.add_column(_t("reasoning"), justify="center")

    for idx, (mid, mdata) in enumerate(entries, 1):
        limit = mdata.get("limit") or {}
        table.add_row(
            str(idx),
            mdata.get("id", mid),
            mdata.get("name", mid),
            _format_limit(limit.get("context")),
            _format_limit(limit.get("output")),
            "✓" if mdata.get("reasoning") else "",
        )

    console.print()
    console.print(table)

    choice = _prompt_number(_t("model_range", len(entries)), len(entries))
    if choice is None:
        return None

    mid, mdata = entries[choice - 1]
    model_id = mdata.get("id", mid)
    return model_id, mdata


_CHANNEL_DEFS: list[dict[str, Any]] = [
    {
        "key": "telegram",
        "name": "Telegram",
        "fields": [
            {"key": "token", "label_key": "field_bot_token", "secret": True},
        ],
    },
    {
        "key": "discord",
        "name": "Discord",
        "fields": [
            {"key": "token", "label_key": "field_bot_token", "secret": True},
        ],
    },
    {
        "key": "feishu",
        "name": "Feishu",
        "fields": [
            {"key": "appId", "label_key": "field_app_id", "secret": False},
            {"key": "appSecret", "label_key": "field_app_secret", "secret": True},
        ],
    },
    {
        "key": "dingtalk",
        "name": "DingTalk",
        "fields": [
            {"key": "clientId", "label_key": "field_client_id", "secret": False},
            {"key": "clientSecret", "label_key": "field_client_secret", "secret": True},
        ],
    },
    {
        "key": "slack",
        "name": "Slack",
        "fields": [
            {"key": "botToken", "label_key": "field_bot_token_xoxb", "secret": True},
            {"key": "appToken", "label_key": "field_app_token", "secret": True},
        ],
    },
    {
        "key": "qq",
        "name": "QQ",
        "fields": [
            {"key": "appId", "label_key": "field_app_id", "secret": False},
            {"key": "secret", "label_key": "field_app_secret", "secret": True},
        ],
    },
    {
        "key": "email",
        "name": "Email",
        "fields": [
            {"key": "imapHost", "label_key": "field_imap_host", "secret": False},
            {"key": "imapUsername", "label_key": "field_imap_username", "secret": False},
            {"key": "imapPassword", "label_key": "field_imap_password", "secret": True},
            {"key": "smtpHost", "label_key": "field_smtp_host", "secret": False},
            {"key": "smtpUsername", "label_key": "field_smtp_username", "secret": False},
            {"key": "smtpPassword", "label_key": "field_smtp_password", "secret": True},
            {"key": "fromAddress", "label_key": "field_from_address", "secret": False},
        ],
        "extra": {"consentGranted": True},
    },
    {
        "key": "mochat",
        "name": "Mochat",
        "fields": [
            {"key": "clawToken", "label_key": "field_claw_token", "secret": True},
            {"key": "agentUserId", "label_key": "field_agent_user_id", "secret": False},
        ],
    },
]


def _configure_channels(data: dict, console: Console) -> dict:
    """Run the interactive channel configuration wizard.

    Mutates and returns the config *data* dict. If the user declines or
    cancels, the dict is returned unchanged.
    """
    console.print()
    if not typer.confirm(_t("configure_channels"), default=False):
        return data

    table = Table(title=_t("available_channels"), show_lines=False)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column(_t("channel"), style="cyan")
    table.add_column(_t("fields"))

    for idx, ch in enumerate(_CHANNEL_DEFS, 1):
        field_names = ", ".join(_t(f["label_key"]) for f in ch["fields"])
        table.add_row(str(idx), ch["name"], field_names)

    console.print()
    console.print(table)

    raw = typer.prompt(_t("select_channels"), default="")
    if not raw.strip():
        return data

    selected_indices: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            n = int(part)
        except ValueError:
            console.print(f"[yellow]{_t('skip_invalid', part)}[/yellow]")
            continue
        if 1 <= n <= len(_CHANNEL_DEFS):
            selected_indices.append(n - 1)
        else:
            console.print(f"[yellow]{_t('skip_out_of_range', part)}[/yellow]")

    if not selected_indices:
        return data

    channels_data = data.setdefault("channels", {})
    configured: list[str] = []

    for idx in selected_indices:
        ch_def = _CHANNEL_DEFS[idx]
        console.print(f"\n[bold]--- {ch_def['name']} ---[/bold]")

        values: dict[str, Any] = {}
        cancelled = False
        for field in ch_def["fields"]:
            label = _t(field["label_key"])
            value: str = typer.prompt(f"  {label}", hide_input=field["secret"], default="")
            if not value.strip():
                console.print(f"[dim]{_t('skipping_channel', ch_def['name'], label)}[/dim]")
                cancelled = True
                break
            values[field["key"]] = value.strip()

        if cancelled:
            continue

        ch_data = channels_data.setdefault(ch_def["key"], {})
        ch_data["enabled"] = True
        ch_data.update(values)
        if "extra" in ch_def:
            ch_data.update(ch_def["extra"])

        configured.append(ch_def["name"])
        console.print(f"[green]✓[/green] {ch_def['name']} {_t('configured')}")

    if configured:
        console.print(f"\n[green]✓[/green] {_t('channels_configured', ', '.join(configured))}")

    return data


_TRAYCLI_REPO = "yankeguo/traycli"
_TRAYCLI_FALLBACK_TAG = "v0.1.2"


def _setup_systemd(exe_path: str, console: Console) -> None:
    """Write a systemd user service and enable it."""
    console.print(f"[dim]{_t('autostart_linux')}[/dim]")

    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_file = unit_dir / "weavbot.service"

    unit_file.write_text(
        f"""\
[Unit]
Description=weavbot gateway
After=network-online.target

[Service]
ExecStart={exe_path} gateway
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
""",
        encoding="utf-8",
    )

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "weavbot.service"], check=True)
    subprocess.run(["systemctl", "--user", "start", "weavbot.service"], check=True)

    console.print(f"[green]✓[/green] {_t('autostart_configured')}")
    console.print(f"[green]✓[/green] {_t('service_started')}")


def _setup_launchd(exe_path: str, console: Console) -> None:
    """Write a launchd LaunchAgent plist and load it."""
    console.print(f"[dim]{_t('autostart_macos')}[/dim]")

    log_dir = Path.home() / ".weavbot" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    agents_dir = Path.home() / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    plist_path = agents_dir / "com.weavbot.gateway.plist"

    stdout_log = str(log_dir / "stdout.log")
    stderr_log = str(log_dir / "stderr.log")

    plist_content = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.weavbot.gateway</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exe_path}</string>
        <string>gateway</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{stdout_log}</string>
    <key>StandardErrorPath</key>
    <string>{stderr_log}</string>
</dict>
</plist>
"""
    plist_path.write_text(plist_content, encoding="utf-8")

    subprocess.run(["launchctl", "load", str(plist_path)], check=True)

    console.print(f"[green]✓[/green] {_t('autostart_configured')}")
    console.print(f"[green]✓[/green] {_t('service_started')}")


def _setup_traycli(exe_path: str, console: Console) -> None:
    """Download traycli, write config, and create a Startup shortcut on Windows."""
    console.print(f"[dim]{_t('autostart_windows')}[/dim]")

    bin_dir = Path.home() / ".weavbot" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    traycli_path = bin_dir / "traycli.exe"

    # --- Download traycli.exe ---
    tag = _TRAYCLI_FALLBACK_TAG
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(f"https://api.github.com/repos/{_TRAYCLI_REPO}/releases/latest")
            if resp.status_code == 200:
                tag = resp.json().get("tag_name", tag)
    except Exception:
        pass

    download_url = (
        f"https://github.com/{_TRAYCLI_REPO}/releases/download/{tag}/traycli-windows-amd64.exe"
    )

    console.print(f"[dim]{_t('downloading_traycli')} ({tag})[/dim]")
    try:
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            resp = client.get(download_url)
            resp.raise_for_status()
            traycli_path.write_bytes(resp.content)
    except (httpx.HTTPError, OSError) as exc:
        console.print(f"[red]{_t('download_failed', exc)}[/red]")
        return

    # --- Write traycli config ---
    traycli_config_dir = Path.home() / ".traycli"
    traycli_config_dir.mkdir(parents=True, exist_ok=True)
    config_file = traycli_config_dir / "config.json"
    config_data = {
        "cmd": [exe_path, "gateway"],
        "env": {"PYTHONUTF8": "1"},
    }
    config_file.write_text(_json.dumps(config_data, indent=2), encoding="utf-8")

    # --- Create .lnk shortcut in Startup folder ---
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        appdata = str(Path.home() / "AppData" / "Roaming")
    startup_dir = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    startup_dir.mkdir(parents=True, exist_ok=True)
    lnk_path = startup_dir / "weavbot.lnk"

    try:
        traycli_str = str(traycli_path).replace("'", "''")
        lnk_str = str(lnk_path).replace("'", "''")
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"$s=(New-Object -COM WScript.Shell).CreateShortcut('{lnk_str}');"
                f"$s.TargetPath='{traycli_str}';$s.Save()",
            ],
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        console.print(f"[yellow]{_t('shortcut_create_failed', exc)}[/yellow]")
        console.print(f"[dim]{_t('shortcut_manual_hint', traycli_path, startup_dir)}[/dim]")
        return

    console.print(f"[green]✓[/green] {_t('autostart_configured')}")


_WEAVBOT_BIN = Path.home() / ".weavbot" / "bin"

_RG_FALLBACK_VERSION = "15.1.0"

_RG_TARGETS: dict[tuple[str, str], str] = {
    ("linux", "x86_64"): "x86_64-unknown-linux-musl",
    ("linux", "aarch64"): "aarch64-unknown-linux-gnu",
    ("darwin", "x86_64"): "x86_64-apple-darwin",
    ("darwin", "arm64"): "aarch64-apple-darwin",
    ("win32", "amd64"): "x86_64-pc-windows-msvc",
    ("win32", "x86_64"): "x86_64-pc-windows-msvc",
    ("win32", "arm64"): "aarch64-pc-windows-msvc",
}


def _install_ripgrep(console: Console) -> None:
    """Detect ripgrep and offer to install it to ~/.weavbot/bin/ if missing."""
    rg_name = "rg.exe" if sys.platform == "win32" else "rg"

    existing = shutil.which("rg") or shutil.which("rg.exe")
    if existing:
        console.print(f"[green]✓[/green] {_t('rg_found', existing)}")
        return

    local_rg = _WEAVBOT_BIN / rg_name
    if local_rg.is_file():
        console.print(f"[green]✓[/green] {_t('rg_found', local_rg)}")
        return

    console.print()
    if not typer.confirm(_t("install_ripgrep"), default=True):
        return

    plat = "linux" if sys.platform.startswith("linux") else sys.platform
    machine = platform.machine().lower()
    target = _RG_TARGETS.get((plat, machine))
    if not target:
        console.print(f"[yellow]{_t('rg_download_failed_platform', plat, machine)}[/yellow]")
        return

    version = _RG_FALLBACK_VERSION
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get("https://api.github.com/repos/BurntSushi/ripgrep/releases/latest")
            if resp.status_code == 200:
                version = resp.json().get("tag_name", version)
    except Exception:
        pass

    is_windows = sys.platform == "win32"
    ext = "zip" if is_windows else "tar.gz"
    archive_name = f"ripgrep-{version}-{target}.{ext}"
    download_url = (
        f"https://github.com/BurntSushi/ripgrep/releases/download/{version}/{archive_name}"
    )

    console.print(f"[dim]{_t('downloading_rg')} ({version})[/dim]")
    try:
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            resp = client.get(download_url)
            resp.raise_for_status()
            archive_bytes = resp.content
    except (httpx.HTTPError, OSError) as exc:
        console.print(f"[red]{_t('rg_download_failed', exc)}[/red]")
        return

    _WEAVBOT_BIN.mkdir(parents=True, exist_ok=True)

    try:
        if is_windows:
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
                for name in zf.namelist():
                    if name.endswith("/rg.exe"):
                        local_rg.write_bytes(zf.read(name))
                        break
                else:
                    console.print(
                        f"[red]{_t('rg_download_failed', _t('rg_download_missing_exe'))}[/red]"
                    )
                    return
        else:
            with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tf:
                for member in tf.getmembers():
                    if member.name.endswith("/rg") and member.isfile():
                        data = tf.extractfile(member)
                        if data:
                            local_rg.write_bytes(data.read())
                            break
                else:
                    console.print(
                        f"[red]{_t('rg_download_failed', _t('rg_download_missing_bin'))}[/red]"
                    )
                    return
            local_rg.chmod(local_rg.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except (tarfile.TarError, zipfile.BadZipFile, OSError) as exc:
        console.print(f"[red]{_t('rg_download_failed', exc)}[/red]")
        return

    console.print(f"[green]✓[/green] {_t('rg_installed', local_rg)}")


def _configure_autostart(console: Console) -> None:
    """Offer to configure platform-specific auto-start for weavbot gateway."""
    console.print()
    if not typer.confirm(_t("configure_autostart"), default=False):
        return

    exe = shutil.which("weavbot") or shutil.which("weavbot.exe")
    if not exe:
        console.print(f"[yellow]{_t('exe_not_found')}[/yellow]")
        return

    console.print(f"[green]✓[/green] {_t('exe_found', exe)}")

    try:
        if sys.platform.startswith("linux"):
            _setup_systemd(exe, console)
        elif sys.platform == "darwin":
            _setup_launchd(exe, console)
        elif sys.platform == "win32":
            _setup_traycli(exe, console)
        else:
            console.print(f"[yellow]{_t('autostart_unsupported')}[/yellow]")
    except (subprocess.CalledProcessError, OSError) as exc:
        console.print(f"[red]{_t('autostart_setup_failed', exc)}[/red]")


def interactive_provider_setup(config: Config, console: Console) -> Config:
    """Run the interactive setup wizard (provider + channels).

    Returns the (possibly modified) config. If the user cancels at any step
    the original config is returned unchanged.
    """
    console.print(f"\n[bold]{_t('interactive_setup')}[/bold]")

    data = config.model_dump(by_alias=True)
    changed = False

    # --- Provider setup ---
    raw = _fetch_providers(console)
    if raw is not None:
        providers = _compatible_providers(raw)
        if not providers:
            console.print(f"[red]{_t('no_compatible')}[/red]")
        else:
            provider = _select_provider(providers, console)
            if provider is not None:
                result = _select_model(provider, console)
                if result is not None:
                    model_id, model_data = result

                    console.print()
                    if provider.get("doc"):
                        console.print(f"[dim]{_t('docs')}: {provider['doc']}[/dim]")
                    api_key: str = typer.prompt(_t("api_key"), hide_input=True)

                    if api_key.strip():
                        api_key = api_key.strip()
                        provider_id: str = provider["id"]
                        mode = _NPM_TO_MODE[provider["npm"]]
                        api_base: str | None = provider.get("api") or None
                        if mode == "anthropic" and api_base:
                            api_base = api_base.rstrip("/")
                            if api_base.endswith("/v1"):
                                api_base = api_base[:-3] or None
                        limit = model_data.get("limit") or {}
                        max_tokens: int = limit.get("output", 8192)
                        max_context: int = limit.get("context", 131072)

                        console.print()
                        console.print(f"[bold]{_t('provider_summary')}:[/bold]")
                        console.print(
                            f"  {_t('provider_label')}:   [cyan]{provider_id}[/cyan] ({provider['name']})"
                        )
                        console.print(f"  {_t('mode')}:       [green]{mode}[/green]")
                        if api_base:
                            console.print(f"  {_t('api_base')}:   {api_base}")
                        console.print(f"  {_t('model')}:      [cyan]{model_id}[/cyan]")
                        console.print(f"  {_t('max_tokens')}: {max_tokens}")
                        console.print(f"  {_t('max_context')}: {_format_limit(max_context)}")
                        console.print(
                            f"  {_t('api_key')}:    {api_key[:8]}{'*' * max(0, len(api_key) - 8)}"
                        )

                        if typer.confirm(f"\n{_t('apply_provider')}", default=True):
                            data.setdefault("providers", {})[provider_id] = {
                                "mode": mode,
                                "apiKey": api_key,
                                **({"apiBase": api_base} if api_base else {}),
                            }
                            defaults = data.setdefault("agents", {}).setdefault("defaults", {})
                            defaults["provider"] = provider_id
                            defaults["model"] = model_id
                            defaults["maxTokens"] = max_tokens
                            defaults["maxContext"] = max_context
                            changed = True
                            console.print(
                                f"[green]✓[/green] {_t('provider_configured', provider_id)}"
                            )

    # --- Channel setup ---
    prev_channels = copy.deepcopy(data.get("channels", {}))
    _configure_channels(data, console)
    if data.get("channels", {}) != prev_channels:
        changed = True

    if changed:
        config = Config.model_validate(data)

    # --- Ripgrep install (needed by grep_file agent tool) ---
    _install_ripgrep(console)

    # --- Auto-start setup (independent of config changes) ---
    _configure_autostart(console)

    return config
