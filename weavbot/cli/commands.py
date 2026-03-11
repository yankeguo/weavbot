"""CLI commands for weavbot."""

import asyncio
import os
import select
import signal
import sys
from pathlib import Path

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from weavbot import __logo__, __version__
from weavbot.config.schema import Config
from weavbot.i18n import t
from weavbot.utils.helpers import sync_workspace_templates

app = typer.Typer(
    name="weavbot",
    help=f"{__logo__} weavbot - Personal AI Assistant",
    no_args_is_help=True,
)

console = Console()
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}

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
    from weavbot.utils.helpers import get_workspace_path

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
    workspace = get_workspace_path()

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
    else:
        console.print(f"  [cyan]{_t('chat_example_single')}[/cyan]")
    console.print(f"\n[dim]{_t('chat_apps_hint')}[/dim]")


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
    port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Start the weavbot gateway."""
    from weavbot.agent.loop import AgentLoop
    from weavbot.bus.queue import MessageBus
    from weavbot.channels.manager import ChannelManager
    from weavbot.config.loader import load_config
    from weavbot.cron.service import CronService
    from weavbot.cron.types import CronJob
    from weavbot.heartbeat.service import HeartbeatService
    from weavbot.session.manager import SessionManager

    if verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG)

    console.print(f"{__logo__} {_t('gateway_starting', port)}")

    config = load_config()
    sync_workspace_templates(config.workspace_path)
    bus = MessageBus()
    provider = _make_provider(config)
    session_manager = SessionManager(config.workspace_path)

    # Create cron service first (callback set after agent creation)
    cron_store_path = config.workspace_path / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    # Create agent with cron service
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        reasoning_effort=config.agents.defaults.reasoning_effort,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
    )

    # Set cron callback (needs agent)
    async def on_cron_job(job: CronJob) -> str | None:
        """Execute a cron job through the agent."""
        from weavbot.agent.tools.cron import CronTool
        from weavbot.agent.tools.message import MessageTool

        reminder_note = (
            "[Scheduled Task] Timer finished.\n\n"
            f"Task '{job.name}' has been triggered.\n"
            f"Scheduled instruction: {job.payload.message}"
        )

        # Prevent the agent from scheduling new cron jobs during execution
        cron_tool = agent.tools.get("cron")
        cron_token = None
        if isinstance(cron_tool, CronTool):
            cron_token = cron_tool.set_cron_context(True)
        try:
            response = await agent.process_direct(
                reminder_note,
                session_key=f"cron:{job.id}",
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to or "direct",
            )
        finally:
            if isinstance(cron_tool, CronTool) and cron_token is not None:
                cron_tool.reset_cron_context(cron_token)

        message_tool = agent.tools.get("message")
        if isinstance(message_tool, MessageTool) and message_tool._sent_in_turn:
            return response

        if job.payload.deliver and job.payload.to and response:
            from weavbot.bus.events import OutboundMessage

            await bus.publish_outbound(
                OutboundMessage(
                    channel=job.payload.channel or "cli", chat_id=job.payload.to, content=response
                )
            )
        return response

    cron.on_job = on_cron_job

    # Create channel manager
    channels = ChannelManager(config, bus)

    def _pick_heartbeat_target() -> tuple[str, str]:
        """Pick a routable channel/chat target for heartbeat-triggered messages."""
        enabled = set(channels.enabled_channels)
        # Prefer the most recently updated non-internal session on an enabled channel.
        for item in session_manager.list_sessions():
            key = item.get("key") or ""
            if ":" not in key:
                continue
            channel, chat_id = key.split(":", 1)
            if channel in {"cli", "system"}:
                continue
            if channel in enabled and chat_id:
                return channel, chat_id
        # Fallback keeps prior behavior but remains explicit.
        return "cli", "direct"

    # Create heartbeat service
    async def on_heartbeat_execute(tasks: str) -> str:
        """Phase 2: execute heartbeat tasks through the full agent loop."""
        channel, chat_id = _pick_heartbeat_target()

        async def _silent(*_args, **_kwargs):
            pass

        return await agent.process_direct(
            tasks,
            session_key="heartbeat",
            channel=channel,
            chat_id=chat_id,
            on_progress=_silent,
        )

    async def on_heartbeat_notify(response: str) -> None:
        """Deliver a heartbeat response to the user's channel."""
        from weavbot.bus.events import OutboundMessage

        channel, chat_id = _pick_heartbeat_target()
        if channel == "cli":
            return  # No external channel available to deliver to
        await bus.publish_outbound(
            OutboundMessage(channel=channel, chat_id=chat_id, content=response)
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
    session_id: str = typer.Option("cli:direct", "--session", "-s", help="Session ID"),
    markdown: bool = typer.Option(
        True, "--markdown/--no-markdown", help="Render assistant output as Markdown"
    ),
    logs: bool = typer.Option(
        False, "--logs/--no-logs", help="Show weavbot runtime logs during chat"
    ),
):
    """Interact with the agent directly."""
    from loguru import logger

    from weavbot.agent.loop import AgentLoop
    from weavbot.bus.queue import MessageBus
    from weavbot.config.loader import load_config
    from weavbot.cron.service import CronService

    config = load_config()
    sync_workspace_templates(config.workspace_path)

    bus = MessageBus()
    provider = _make_provider(config)

    # Create cron service for tool usage (no callback needed for CLI unless running)
    cron_store_path = config.workspace_path / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

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
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        reasoning_effort=config.agents.defaults.reasoning_effort,
        web_proxy=config.tools.web.proxy or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        mcp_servers=config.tools.mcp_servers,
        channels_config=config.channels,
    )

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
                    message, session_id, on_progress=_cli_progress
                )
            _print_agent_response(response, render_markdown=markdown)
            await agent_loop.close_mcp()

        asyncio.run(run_once())
    else:
        # Interactive mode — route through bus like other channels
        from weavbot.bus.events import InboundMessage

        _init_prompt_session()
        console.print(f"{__logo__} {_t('interactive_mode')}\n")

        if ":" in session_id:
            cli_channel, cli_chat_id = session_id.split(":", 1)
        else:
            cli_channel, cli_chat_id = "cli", session_id

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
# Channel Commands
# ============================================================================


channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status():
    """Show channel status."""
    from weavbot.config.loader import load_config

    config = load_config()

    table = Table(title=_t("channel_status"))
    table.add_column(_t("column_channel"), style="cyan")
    table.add_column(_t("column_enabled"), style="green")
    table.add_column(_t("column_configuration"), style="yellow")

    dc = config.channels.discord
    table.add_row("Discord", "✓" if dc.enabled else "✗", dc.gateway_url)

    # Feishu
    fs = config.channels.feishu
    fs_config = (
        f"app_id: {fs.app_id[:10]}..." if fs.app_id else f"[dim]{_t('not_configured')}[/dim]"
    )
    table.add_row("Feishu", "✓" if fs.enabled else "✗", fs_config)

    # Mochat
    mc = config.channels.mochat
    mc_base = mc.base_url or f"[dim]{_t('not_configured')}[/dim]"
    table.add_row("Mochat", "✓" if mc.enabled else "✗", mc_base)

    # Telegram
    tg = config.channels.telegram
    tg_config = f"token: {tg.token[:10]}..." if tg.token else f"[dim]{_t('not_configured')}[/dim]"
    table.add_row("Telegram", "✓" if tg.enabled else "✗", tg_config)

    # Slack
    slack = config.channels.slack
    slack_config = (
        _t("socket")
        if slack.app_token and slack.bot_token
        else f"[dim]{_t('not_configured')}[/dim]"
    )
    table.add_row("Slack", "✓" if slack.enabled else "✗", slack_config)

    # DingTalk
    dt = config.channels.dingtalk
    dt_config = (
        f"client_id: {dt.client_id[:10]}..."
        if dt.client_id
        else f"[dim]{_t('not_configured')}[/dim]"
    )
    table.add_row("DingTalk", "✓" if dt.enabled else "✗", dt_config)

    # QQ
    qq = config.channels.qq
    qq_config = (
        f"app_id: {qq.app_id[:10]}..." if qq.app_id else f"[dim]{_t('not_configured')}[/dim]"
    )
    table.add_row("QQ", "✓" if qq.enabled else "✗", qq_config)

    # Email
    em = config.channels.email
    em_config = em.imap_host if em.imap_host else f"[dim]{_t('not_configured')}[/dim]"
    table.add_row("Email", "✓" if em.enabled else "✗", em_config)

    console.print(table)


# ============================================================================
# Status Commands
# ============================================================================


@app.command()
def status():
    """Show weavbot status."""
    from weavbot.config.loader import get_config_path, load_config

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{__logo__} {_t('status_title')}\n")

    config_mark = "[green]✓[/green]" if config_path.exists() else "[red]✗[/red]"
    workspace_mark = "[green]✓[/green]" if workspace.exists() else "[red]✗[/red]"
    console.print(_t("status_config", config_path, config_mark))
    console.print(_t("status_workspace", workspace, workspace_mark))

    if config_path.exists():
        console.print(_t("status_model", config.agents.defaults.model))
        provider = config.agents.defaults.provider or f"[dim]{_t('not_set')}[/dim]"
        console.print(_t("status_provider", provider))

        for name, p in config.providers.items():
            has_key = bool(p.api_key)
            base_info = f" ({p.api_base})" if p.api_base else ""
            key_mark = "[green]✓[/green]" if has_key else f"[dim]{_t('not_set')}[/dim]"
            console.print(f"{name} [dim][{p.mode}][/dim]: {key_mark}{base_info}")


if __name__ == "__main__":
    app()
