"""CLI commands for weavbot."""

import asyncio
import json
import os
import select
import signal
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import typer
from loguru import logger
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

from weavbot import __logo__, __version__
from weavbot.bus.events import InboundMessage
from weavbot.config.schema import Config
from weavbot.i18n import t
from weavbot.utils.helpers import build_session_key, sync_workspace_templates, validate_session_key

app = typer.Typer(
    name="weavbot",
    help=f"{__logo__} weavbot - Personal AI Assistant",
    no_args_is_help=True,
)
wechat_app = typer.Typer(name="wechat", help="Wechat channel helper commands")
app.add_typer(wechat_app, name="wechat")

console = Console()
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}


@dataclass
class RouteTarget:
    """Minimal routable target selected from session metadata."""

    channel: str
    chat_id: str
    session_key: str
    metadata: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# CLI input: prompt_toolkit for editing, paste, history, and display
# ---------------------------------------------------------------------------

_PROMPT_SESSION: PromptSession | None = None
_SAVED_TERM_ATTRS = None  # original termios settings, restored on exit


def _t(key: str, *args: object) -> str:
    return t(f"cli.commands.{key}", *args)


def _flush_pending_tty_input() -> None:
    """Drop unread keypresses typed while the model was generating output."""
    if sys.platform == "win32":
        try:
            import msvcrt

            while msvcrt.kbhit():
                msvcrt.getch()
        except Exception:
            pass
        return

    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    try:
        import termios

        termios.tcflush(fd, termios.TCIFLUSH)
        return
    except Exception:
        pass

    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break
    except Exception:
        return


def _restore_terminal() -> None:
    """Restore terminal to its original state (echo, line buffering, etc.)."""
    if _SAVED_TERM_ATTRS is None:
        return
    try:
        import termios

        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
    except Exception:
        pass


def _init_prompt_session() -> None:
    """Create the prompt_toolkit session with persistent file history."""
    global _PROMPT_SESSION, _SAVED_TERM_ATTRS

    # Save terminal state so we can restore it on exit
    try:
        import termios

        _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    history_file = Path.home() / ".weavbot" / "history" / "cli_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    _PROMPT_SESSION = PromptSession(
        history=FileHistory(str(history_file)),
        enable_open_in_editor=False,
        multiline=False,  # Enter submits (single line mode)
    )


def _print_agent_response(response: str, render_markdown: bool) -> None:
    """Render assistant response with consistent terminal styling."""
    content = response or ""
    body = Markdown(content) if render_markdown else Text(content)
    console.print()
    console.print(f"[cyan]{__logo__} weavbot[/cyan]")
    console.print(body)
    console.print()


def _is_exit_command(command: str) -> bool:
    """Return True when input should end interactive chat."""
    return command.lower() in EXIT_COMMANDS


def _collect_heartbeat_progress(
    progress_items: list[str], content: str, *, tool_hint: bool = False
) -> None:
    """Collect user-facing heartbeat progress text; always ignore tool hints."""
    if tool_hint:
        return
    text = (content or "").strip()
    if not text:
        return
    if progress_items and progress_items[-1] == text:
        return
    progress_items.append(text)


def _assemble_heartbeat_response(progress_items: list[str], final_content: str) -> str:
    """Assemble heartbeat message as progress blocks followed by final content."""
    merged: list[str] = []
    for item in progress_items:
        text = item.strip()
        if not text:
            continue
        if merged and merged[-1] == text:
            continue
        merged.append(text)

    final_text = (final_content or "").strip()
    if final_text and (not merged or merged[-1] != final_text):
        merged.append(final_text)

    if not merged:
        return ""
    return "\n\n".join(merged)


def _build_background_notify_contract(
    *,
    source: str,
    channel: str,
    chat_id: str,
    target_metadata: dict[str, object] | None = None,
) -> str:
    """Build explicit notification contract for background-triggered turns."""
    metadata_text = "{}"
    if target_metadata:
        try:
            metadata_text = json.dumps(target_metadata, ensure_ascii=False, sort_keys=True)
        except TypeError:
            metadata_text = "{}"
    return (
        f"[{source} Notification Contract]\n"
        "- This is a background task run.\n"
        "- Do NOT send user-facing plain text unless you intentionally notify the user.\n"
        "- Only notify when necessary by calling the `message` tool.\n"
        "- For routine/no-op outcomes, finish silently without calling `message`.\n"
        "- If an important result requires user action, call `message` once with concise content.\n"
        "- For `message` target routing, prefer current context defaults; if needed, use:\n"
        f"  - session_key: {InboundMessage.default_session_key(channel, chat_id)}\n"
        f"  - target metadata hint: {metadata_text}\n"
    )


def _build_heartbeat_execute_input(
    tasks: str, *, channel: str, chat_id: str, target_metadata: dict[str, object]
) -> str:
    """Compose heartbeat execution input with explicit notify contract."""
    task_text = (tasks or "").strip() or "(empty heartbeat tasks)"
    return (
        "[Heartbeat Task]\n"
        f"{task_text}\n\n"
        f"{_build_background_notify_contract(source='Heartbeat', channel=channel, chat_id=chat_id, target_metadata=target_metadata)}"
    )


def _build_cron_execute_input(
    *,
    job_name: str,
    instruction: str,
    channel: str,
    chat_id: str,
) -> str:
    """Compose cron execution input with explicit notify contract."""
    return (
        "[Scheduled Task] Timer finished.\n\n"
        f"Task '{job_name}' has been triggered.\n"
        f"Scheduled instruction: {instruction}\n\n"
        f"{_build_background_notify_contract(source='Cron', channel=channel, chat_id=chat_id)}"
    )


def _looks_like_agent_error(text: str) -> bool:
    """Best-effort classifier for user-visible execution failure texts."""
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    error_markers = (
        "sorry, i encountered an error",
        "error calling the ai model",
        "maximum number of tool call iterations",
        "context is too large to process safely",
    )
    return any(marker in normalized for marker in error_markers)


async def _suppress_background_progress(_content: str, *, tool_hint: bool = False) -> None:
    """Drop background progress/tool-hint updates to avoid user-facing noise."""
    _ = tool_hint
    return None


def _parse_heartbeat_target(key: str) -> RouteTarget | None:
    """Parse a session key into heartbeat delivery target fields.

    Returns routable target or None for invalid keys.
    """
    text = (key or "").strip()
    if not text:
        return None

    # Wechat uses scoped session key: wechat_{account_key}_{peer_id}
    if text.startswith("wechat_"):
        parts = text.split("_", 2)
        if len(parts) == 3 and parts[1] and parts[2]:
            return RouteTarget(
                channel="wechat",
                chat_id=parts[2],
                session_key=text,
                metadata={"wechat": {"account_key": parts[1]}},
            )
        return None

    # Legacy compatibility: wechat:{account_key}:{peer_id}
    if text.startswith("wechat:"):
        legacy_parts = text.split(":", 2)
        if len(legacy_parts) == 3 and legacy_parts[1] and legacy_parts[2]:
            return RouteTarget(
                channel="wechat",
                chat_id=legacy_parts[2],
                session_key=build_session_key(*legacy_parts),
                metadata={"wechat": {"account_key": legacy_parts[1]}},
            )
        return None

    if "_" not in text:
        return None
    channel, chat_id = text.split("_", 1)
    if not channel or not chat_id:
        return None
    return RouteTarget(channel=channel, chat_id=chat_id, session_key=text, metadata={})


def _parse_cli_session_route(session_key: str) -> tuple[str, str]:
    """Parse normalized session key to (channel, chat_id) for CLI ingress."""
    normalized = validate_session_key(session_key)
    if "_" not in normalized:
        raise ValueError("session_key must include channel and chat_id, e.g. cli_direct")
    channel, chat_id = normalized.split("_", 1)
    if not channel or not chat_id:
        raise ValueError("session_key must include channel and chat_id, e.g. cli_direct")
    return channel, chat_id


def _extract_interactive_target(
    item: dict[str, object], enabled_channels: set[str]
) -> RouteTarget | None:
    """Extract interactive delivery target from session item metadata or key fallback."""
    key = str(item.get("key") or "")
    if key.startswith(("heartbeat:", "heartbeat_", "cron:", "cron_", "system:", "system_")):
        return None

    meta = item.get("metadata")
    session_meta = meta if isinstance(meta, dict) else {}
    if bool(session_meta.get("_cron_in_job")) or bool(session_meta.get("_heartbeat_in_job")):
        return None
    raw_target = (
        session_meta.get("interactive_target")
        if isinstance(session_meta.get("interactive_target"), dict)
        else None
    )
    payload = raw_target if isinstance(raw_target, dict) else {}
    channel = str(payload.get("channel") or "").strip()
    chat_id = str(payload.get("chat_id") or "").strip()
    session_key = str(payload.get("session_key") or "").strip()
    target = (
        RouteTarget(
            channel=channel,
            chat_id=chat_id,
            session_key=session_key,
            metadata=dict(payload.get("metadata") or {})
            if isinstance(payload.get("metadata"), dict)
            else {},
        )
        if channel and chat_id and session_key
        else None
    )
    if target and target.channel not in {"cli", "system"} and target.channel in enabled_channels:
        return target
    return None


def _pick_heartbeat_target_from_sessions(
    sessions: list[dict[str, object]], enabled_channels: set[str]
) -> RouteTarget:
    """Pick routable heartbeat target from recent user-facing sessions."""
    for item in sessions:
        target = _extract_interactive_target(item, enabled_channels)
        if target:
            return target
    return RouteTarget(
        channel="cli",
        chat_id="direct",
        session_key=InboundMessage.default_session_key("cli", "direct"),
        metadata={},
    )


async def _read_interactive_input_async() -> str:
    """Read user input using prompt_toolkit (handles paste, history, display).

    prompt_toolkit natively handles:
    - Multiline paste (bracketed paste mode)
    - History navigation (up/down arrows)
    - Clean display (no ghost characters or artifacts)
    """
    if _PROMPT_SESSION is None:
        raise RuntimeError("Call _init_prompt_session() first")
    try:
        with patch_stdout():
            return await _PROMPT_SESSION.prompt_async(
                HTML("<b fg='ansiblue'>You:</b> "),
            )
    except EOFError as exc:
        raise KeyboardInterrupt from exc


def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} weavbot v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(None, "--version", "-v", callback=version_callback, is_eager=True),
):
    """weavbot - Personal AI Assistant."""
    pass


# ============================================================================
# Onboard / Setup
# ============================================================================


def _apply_config_overrides(data: dict, overrides: list[str]) -> dict:
    """Apply ``--set key=value`` overrides to a config dict.

    Keys are dot-separated camelCase paths (e.g. ``providers.custom.apiBase``).
    Values are coerced via ``json.loads`` first (int, bool, float, null, list);
    if that fails the raw string is used as-is.
    """
    import json as _json

    for item in overrides:
        if "=" not in item:
            raise typer.BadParameter(_t("invalid_set_format", item))
        key, raw_value = item.split("=", 1)
        if not key:
            raise typer.BadParameter(_t("empty_set_key", item))

        try:
            value = _json.loads(raw_value)
        except (ValueError, _json.JSONDecodeError):
            value = raw_value

        parts = key.split(".")
        target = data
        for part in parts[:-1]:
            if part not in target or not isinstance(target[part], dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value

    return data


@app.command()
def onboard(
    set_values: list[str] = typer.Option(
        [], "--set", help="Set config value (dot path), e.g. --set providers.custom.apiKey=sk-xxx"
    ),
):
    """Initialize weavbot configuration and workspace."""
    from weavbot.config.loader import get_config_path, load_config, save_config
    from weavbot.config.schema import Config
    from weavbot.utils.helpers import ensure_workspace_path

    config_path = get_config_path()

    if config_path.exists():
        console.print(f"[yellow]{_t('config_exists', config_path)}[/yellow]")
        console.print(f"  [bold]y[/bold] = {_t('overwrite_yes')}")
        console.print(f"  [bold]N[/bold] = {_t('overwrite_no')}")
        if typer.confirm(_t("overwrite_confirm")):
            config = Config()
            console.print(f"[green]✓[/green] {_t('config_reset', config_path)}")
        else:
            config = load_config()
            console.print(f"[green]✓[/green] {_t('config_refreshed', config_path)}")
    else:
        config = Config()
        console.print(f"[green]✓[/green] {_t('config_created', config_path)}")

    if set_values:
        data = config.model_dump(by_alias=True)
        _apply_config_overrides(data, set_values)
        config = Config.model_validate(data)
        for item in set_values:
            console.print(f"[green]✓[/green] {_t('config_set', item)}")
    else:
        from weavbot.cli.interactive_setup import interactive_provider_setup

        config = interactive_provider_setup(config, console)

    save_config(config)

    # Create workspace
    workspace = ensure_workspace_path()

    if not workspace.exists():
        workspace.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✓[/green] {_t('workspace_created', workspace)}")

    sync_workspace_templates(workspace)

    console.print(f"\n{__logo__} {_t('ready')}")

    has_any_key = any(p.api_key for p in config.providers.values())

    console.print(f"\n{_t('next_steps')}")
    if not has_any_key:
        console.print(f"  [cyan]{_t('add_api_key')}[/cyan]")
        console.print(f"     {_t('get_api_key')}")
        console.print(f"  [cyan]{_t('chat_example')}[/cyan]")
        console.print(f"  [cyan]{_t('gateway_example')}[/cyan]")
    else:
        console.print(f"  [cyan]{_t('chat_example_single')}[/cyan]")
        console.print(f"  [cyan]{_t('gateway_example_single')}[/cyan]")


def _make_provider(config: Config):
    """Create the appropriate LLM provider from config."""
    from weavbot.providers.anthropic_provider import AnthropicProvider
    from weavbot.providers.openai_provider import OpenAIProvider

    model = config.agents.defaults.model
    p = config.get_provider()

    if not p:
        console.print(f"[red]{_t('error_no_provider')}[/red]")
        console.print(_t("error_set_provider_hint"))
        raise typer.Exit(1)

    if not p.api_key:
        console.print(f"[red]{_t('error_no_api_key')}[/red]")
        raise typer.Exit(1)

    if p.mode == "anthropic":
        return AnthropicProvider(
            api_key=p.api_key,
            api_base=p.api_base,
            default_model=model,
            extra_headers=p.extra_headers,
        )

    return OpenAIProvider(
        api_key=p.api_key,
        api_base=p.api_base or "https://api.openai.com/v1",
        default_model=model,
        extra_headers=p.extra_headers,
    )


# ============================================================================
# Gateway / Server
# ============================================================================


@app.command()
def gateway(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Start the weavbot gateway."""
    from weavbot.agent.loop import AgentLoop
    from weavbot.bus.queue import MessageBus
    from weavbot.channels.manager import ChannelManager
    from weavbot.channels.store import ChannelStore
    from weavbot.config.loader import load_config
    from weavbot.cron.service import CronService
    from weavbot.cron.types import CronJob
    from weavbot.heartbeat.service import HeartbeatService
    from weavbot.session.manager import SessionManager
    from weavbot.utils.helpers import ensure_data_path
    from weavbot.utils.path_migration import prepare_runtime_paths

    if verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG)

    console.print(f"{__logo__} {_t('gateway_starting')}")

    config = load_config()
    runtime_paths = prepare_runtime_paths(config.workspace_path)
    channel_store = ChannelStore(ensure_data_path() / "channels")
    bus = MessageBus()
    provider = _make_provider(config)
    session_manager = SessionManager(config.workspace_path)

    # Create cron service first (callback set after agent creation)
    cron = CronService(runtime_paths.cron_store_path)

    # Create agent with cron service
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
        max_context=config.agents.defaults.max_context,
        max_iterations=config.agents.defaults.max_tool_iterations,
        reasoning_effort=config.agents.defaults.reasoning_effort,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
        channel_store=channel_store,
    )

    # Set cron callback (needs agent)
    async def on_cron_job(job: CronJob) -> str | None:
        """Execute a cron job through the agent."""
        from weavbot.bus.events import OutboundMessage

        primary = (
            channel_store.resolve(job.payload.original_session_key)
            if job.payload.original_session_key
            else None
        )
        channel = primary.channel if primary else "cli"
        chat_id = primary.chat_id if primary else "direct"

        ikey = job.payload.interactive_session_key
        interactive_resolved = channel_store.resolve(ikey) if ikey else None
        interactive_target = (
            RouteTarget(
                channel=interactive_resolved.channel,
                chat_id=interactive_resolved.chat_id,
                session_key=ikey,
                metadata=interactive_resolved.metadata,
            )
            if interactive_resolved
            else None
        )
        if interactive_target is None:
            fallback_target = _pick_heartbeat_target_from_sessions(
                session_manager.list_sessions(),
                set(channels.enabled_channels),
            )
            if fallback_target.channel != "cli":
                interactive_target = fallback_target
        reminder_note = _build_cron_execute_input(
            job_name=job.name,
            instruction=job.payload.message,
            channel=channel,
            chat_id=chat_id,
        )

        try:
            response = await agent.process_direct(
                reminder_note,
                session_key=build_session_key("cron", job.id),
                channel=channel,
                chat_id=chat_id,
                metadata={"_cron_in_job": True},
                on_progress=_suppress_background_progress,
                interactive_session_key=(
                    interactive_target.session_key if interactive_target else None
                ),
            )
        except Exception as e:
            logger.exception("Cron job execution failed: id={}, name={}", job.id, job.name)
            err_content = f"[Cron Error] Task '{job.name}' failed: {e}"
            if job.payload.original_session_key and channel != "cli":
                await bus.publish_outbound(
                    OutboundMessage(
                        session_key=job.payload.original_session_key, content=err_content
                    )
                )
            return err_content

        if response and _looks_like_agent_error(response):
            err_content = f"[Cron Error] Task '{job.name}' failed: {response}"
            if job.payload.original_session_key and channel != "cli":
                await bus.publish_outbound(
                    OutboundMessage(
                        session_key=job.payload.original_session_key, content=err_content
                    )
                )
            return err_content

        logger.info(
            "Cron job completed without outbound notify: id={}, name={}, channel={}, chat_id={}",
            job.id,
            job.name,
            channel,
            chat_id,
        )
        return ""

    cron.on_job = on_cron_job

    # Create channel manager
    channels = ChannelManager(config, bus, channel_store=channel_store)
    last_heartbeat_target: RouteTarget | None = None

    def _pick_heartbeat_target() -> RouteTarget:
        """Pick a routable channel/chat target for heartbeat-triggered messages."""
        return _pick_heartbeat_target_from_sessions(
            session_manager.list_sessions(),
            set(channels.enabled_channels),
        )

    def _heartbeat_session_key(channel: str, chat_id: str) -> str:
        """Rotate heartbeat context daily to avoid unbounded background-session growth."""
        return build_session_key("heartbeat", channel, chat_id, date.today().isoformat())

    # Create heartbeat service
    async def on_heartbeat_execute(tasks: str) -> str:
        """Phase 2: execute heartbeat tasks through the full agent loop."""
        nonlocal last_heartbeat_target
        target = _pick_heartbeat_target()
        last_heartbeat_target = target
        session_key = _heartbeat_session_key(target.channel, target.chat_id)
        execute_input = _build_heartbeat_execute_input(
            tasks,
            channel=target.channel,
            chat_id=target.chat_id,
            target_metadata=target.metadata,
        )
        try:
            final_content = await agent.process_direct(
                execute_input,
                session_key=session_key,
                channel=target.channel,
                chat_id=target.chat_id,
                metadata=target.metadata,
                on_progress=_suppress_background_progress,
                interactive_session_key=target.session_key,
            )
        except Exception as e:
            logger.exception(
                "Heartbeat execute failed: channel={}, chat_id={}", target.channel, target.chat_id
            )
            return f"[Heartbeat Error] Task execution failed: {e}"

        if final_content and _looks_like_agent_error(final_content):
            return f"[Heartbeat Error] {final_content}"
        logger.info(
            "Heartbeat execute completed without outbound notify: channel={}, chat_id={}, final_len={}",
            target.channel,
            target.chat_id,
            len(final_content or ""),
        )
        return ""

    async def on_heartbeat_notify(response: str) -> None:
        """Deliver a heartbeat response to the user's channel."""
        nonlocal last_heartbeat_target
        from weavbot.bus.events import OutboundMessage

        target = last_heartbeat_target or _pick_heartbeat_target()
        if target.channel == "cli":
            logger.warning("Heartbeat notify skipped because no recent routable user target found")
            return  # No external channel available to deliver to
        logger.info(
            "Heartbeat notify deliver: channel={}, chat_id={}, content_len={}, meta_keys={}",
            target.channel,
            target.chat_id,
            len(response or ""),
            sorted(target.metadata.keys()),
        )
        await bus.publish_outbound(
            OutboundMessage(
                session_key=target.session_key,
                content=response,
            )
        )

    hb_cfg = config.gateway.heartbeat
    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        provider=provider,
        model=agent.model,
        on_execute=on_heartbeat_execute,
        on_notify=on_heartbeat_notify,
        interval_s=hb_cfg.interval_s,
        enabled=hb_cfg.enabled,
    )

    if channels.enabled_channels:
        console.print(
            f"[green]✓[/green] {_t('channels_enabled', ', '.join(channels.enabled_channels))}"
        )
    else:
        console.print(f"[yellow]{_t('channels_warning_none')}[/yellow]")

    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]✓[/green] {_t('cron_jobs', cron_status['jobs'])}")

    console.print(f"[green]✓[/green] {_t('heartbeat_every', hb_cfg.interval_s)}")

    def _forward_sigterm_to_sigint(signum, frame):
        os.kill(os.getpid(), signal.SIGINT)

    signal.signal(signal.SIGTERM, _forward_sigterm_to_sigint)

    async def run():
        try:
            await cron.start()
            await heartbeat.start()
            await asyncio.gather(
                agent.run(),
                channels.start_all(),
            )
        except KeyboardInterrupt:
            console.print(f"\n{_t('shutting_down')}")
        finally:
            await agent.close_mcp()
            heartbeat.stop()
            cron.stop()
            agent.stop()
            await channels.stop_all()

    asyncio.run(run())


# ============================================================================
# Agent Commands
# ============================================================================


@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli_direct", "--session", "-s", help="Session ID"),
    markdown: bool = typer.Option(
        True, "--markdown/--no-markdown", help="Render assistant output as Markdown"
    ),
    logs: bool = typer.Option(
        False, "--logs/--no-logs", help="Show weavbot runtime logs during chat"
    ),
):
    """Interact with the agent directly."""
    from weavbot.agent.loop import AgentLoop
    from weavbot.bus.queue import MessageBus
    from weavbot.channels.store import ChannelStore
    from weavbot.config.loader import load_config
    from weavbot.cron.service import CronService
    from weavbot.utils.helpers import ensure_data_path
    from weavbot.utils.path_migration import prepare_runtime_paths

    config = load_config()
    runtime_paths = prepare_runtime_paths(config.workspace_path)

    bus = MessageBus()
    provider = _make_provider(config)
    channel_store = ChannelStore(ensure_data_path() / "channels")

    # Create cron service for tool usage (no callback needed for CLI unless running)
    cron = CronService(runtime_paths.cron_store_path)

    if logs:
        logger.enable("weavbot")
    else:
        logger.disable("weavbot")

    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
        max_context=config.agents.defaults.max_context,
        max_iterations=config.agents.defaults.max_tool_iterations,
        reasoning_effort=config.agents.defaults.reasoning_effort,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
        channel_store=channel_store,
    )

    try:
        normalized_session_id = validate_session_key(session_id)
        cli_channel, cli_chat_id = _parse_cli_session_route(normalized_session_id)
    except ValueError as e:
        console.print(f"[red]Invalid --session: {e}[/red]")
        raise typer.Exit(1)

    # Show spinner when logs are off (no output to miss); skip when logs are on
    def _thinking_ctx():
        if logs:
            from contextlib import nullcontext

            return nullcontext()
        # Animated spinner is safe to use with prompt_toolkit input handling
        return console.status(f"[dim]{_t('thinking')}[/dim]", spinner="dots")

    async def _cli_progress(content: str, *, tool_hint: bool = False) -> None:
        ch = agent_loop.channels_config
        if ch and tool_hint and not ch.send_tool_hints:
            return
        if ch and not tool_hint and not ch.send_progress:
            return
        console.print(f"  [dim]↳ {content}[/dim]")

    if message:
        # Single message mode — direct call, no bus needed
        async def run_once():
            with _thinking_ctx():
                response = await agent_loop.process_direct(
                    message,
                    normalized_session_id,
                    channel=cli_channel,
                    chat_id=cli_chat_id,
                    on_progress=_cli_progress,
                )
            _print_agent_response(response, render_markdown=markdown)
            await agent_loop.close_mcp()

        asyncio.run(run_once())
    else:
        # Interactive mode — route through bus like other channels
        from weavbot.bus.events import InboundMessage

        _init_prompt_session()
        console.print(f"{__logo__} {_t('interactive_mode')}\n")

        def _exit_on_sigint(signum, frame):
            _restore_terminal()
            console.print(f"\n{_t('goodbye')}")
            os._exit(0)

        signal.signal(signal.SIGINT, _exit_on_sigint)
        signal.signal(signal.SIGTERM, _exit_on_sigint)

        async def run_interactive():
            bus_task = asyncio.create_task(agent_loop.run())
            turn_done = asyncio.Event()
            turn_done.set()
            turn_response: list[str] = []

            async def _consume_outbound():
                while True:
                    try:
                        msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
                        if msg.metadata.get("_progress"):
                            is_tool_hint = msg.metadata.get("_tool_hint", False)
                            ch = agent_loop.channels_config
                            if ch and is_tool_hint and not ch.send_tool_hints:
                                pass
                            elif ch and not is_tool_hint and not ch.send_progress:
                                pass
                            else:
                                console.print(f"  [dim]↳ {msg.content}[/dim]")
                        elif not turn_done.is_set():
                            if msg.content:
                                turn_response.append(msg.content)
                            turn_done.set()
                        elif msg.content:
                            console.print()
                            _print_agent_response(msg.content, render_markdown=markdown)
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break

            outbound_task = asyncio.create_task(_consume_outbound())

            try:
                while True:
                    try:
                        _flush_pending_tty_input()
                        user_input = await _read_interactive_input_async()
                        command = user_input.strip()
                        if not command:
                            continue

                        if _is_exit_command(command):
                            _restore_terminal()
                            console.print(f"\n{_t('goodbye')}")
                            break

                        turn_done.clear()
                        turn_response.clear()

                        await bus.publish_inbound(
                            InboundMessage(
                                channel=cli_channel,
                                sender_id="user",
                                chat_id=cli_chat_id,
                                session_key=InboundMessage.default_session_key(
                                    cli_channel, cli_chat_id
                                ),
                                content=user_input,
                            )
                        )

                        with _thinking_ctx():
                            await turn_done.wait()

                        if turn_response:
                            _print_agent_response(turn_response[0], render_markdown=markdown)
                    except KeyboardInterrupt:
                        _restore_terminal()
                        console.print(f"\n{_t('goodbye')}")
                        break
                    except EOFError:
                        _restore_terminal()
                        console.print(f"\n{_t('goodbye')}")
                        break
            finally:
                agent_loop.stop()
                outbound_task.cancel()
                await asyncio.gather(bus_task, outbound_task, return_exceptions=True)
                await agent_loop.close_mcp()

        asyncio.run(run_interactive())


# ============================================================================
# Wechat Commands
# ============================================================================


@wechat_app.command("login")
def wechat_login(
    account_key: str = typer.Option(
        "", "--account", "-a", help="Account key name to save in channels.wechat.accounts"
    ),
    base_url: str = typer.Option(
        "", "--base-url", help="Wechat API base URL, default from config.channels.wechat.baseUrl"
    ),
    route_tag: str = typer.Option("", "--route-tag", help="Optional SKRouteTag header value"),
    timeout_ms: int = typer.Option(480000, "--timeout-ms", help="QR login timeout in milliseconds"),
):
    """Scan QR code and save Wechat account credentials."""
    from weavbot.channels.wechat.accounts import (
        resolve_state_dir,
        save_account_credentials,
        upsert_account_config,
    )
    from weavbot.channels.wechat.api import WechatApiClient
    from weavbot.channels.wechat.auth import account_key_from_account_id, wechat_qr_login
    from weavbot.config.loader import load_config, save_config
    from weavbot.config.schema import WechatAccountConfig

    config = load_config()
    wc = config.channels.wechat
    api_base = (base_url or wc.base_url).strip()
    if not api_base:
        raise typer.BadParameter("wechat baseUrl is empty")

    api = WechatApiClient(
        base_url=api_base,
        token="",
        request_timeout_sec=wc.request_timeout_sec,
        long_poll_timeout_ms=wc.long_poll_timeout_ms,
        route_tag=route_tag or wc.route_tag or None,
    )

    async def run_login():
        return await wechat_qr_login(api=api, console=console, timeout_ms=timeout_ms)

    result = asyncio.run(run_login())
    key = (account_key or account_key_from_account_id(result.account_id)).strip()
    state_dir = resolve_state_dir(config.workspace_path, wc.state_dir)
    save_account_credentials(
        state_dir,
        key,
        account_id=result.account_id,
        token=result.token,
        base_url=result.base_url,
        user_id=result.user_id,
    )

    upsert_account_config(
        wc,
        key,
        WechatAccountConfig(
            enabled=True,
            account_id=result.account_id,
            token=result.token,
            base_url=result.base_url,
            cdn_base_url=wc.cdn_base_url,
            route_tag=route_tag or wc.route_tag or "",
            allow_from=list(wc.allow_from or []),
        ),
    )
    wc.enabled = True
    if key not in wc.enabled_accounts:
        wc.enabled_accounts.append(key)
    save_config(config)

    console.print("\n[green]✓[/green] Wechat login success")
    console.print(f"  account key: [cyan]{key}[/cyan]")
    console.print(f"  account id: [cyan]{result.account_id}[/cyan]")
    console.print("  restart gateway: [cyan]weavbot gateway[/cyan]")


@wechat_app.command("list-accounts")
def wechat_list_accounts():
    """List saved Wechat account records."""
    from weavbot.channels.wechat.accounts import list_account_credentials, resolve_state_dir
    from weavbot.config.loader import load_config

    config = load_config()
    wc = config.channels.wechat
    state_dir = resolve_state_dir(config.workspace_path, wc.state_dir)
    rows = list_account_credentials(state_dir)
    if not rows:
        console.print("[yellow]No wechat accounts found.[/yellow]")
        return
    console.print("[bold]Wechat Accounts[/bold]")
    for row in rows:
        console.print(
            f"- key=[cyan]{row['key']}[/cyan] id={row['account_id']} "
            f"user={row['user_id'] or '-'} base={row['base_url'] or '-'}"
        )


if __name__ == "__main__":
    app()
