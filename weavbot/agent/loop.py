"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from loguru import logger

from weavbot.agent.compact import ContextCompactor
from weavbot.agent.context import ContextBuilder
from weavbot.agent.memory import MemoryStore
from weavbot.agent.messages import ChatMessage
from weavbot.agent.subagent import SubagentManager
from weavbot.agent.tools.cron import CronTool
from weavbot.agent.tools.edit_file import EditFileTool
from weavbot.agent.tools.glob_file import GlobFileTool
from weavbot.agent.tools.grep_file import GrepFileTool
from weavbot.agent.tools.list_dir import ListDirTool
from weavbot.agent.tools.load_media import LoadMediaTool
from weavbot.agent.tools.message import MessageTool
from weavbot.agent.tools.read_file import ReadFileTool
from weavbot.agent.tools.registry import ToolRegistry
from weavbot.agent.tools.shell import ShellTool
from weavbot.agent.tools.spawn import SpawnTool
from weavbot.agent.tools.web_fetch import WebFetchTool
from weavbot.agent.tools.write_file import WriteFileTool
from weavbot.bus.events import InboundMessage, OutboundMessage
from weavbot.bus.queue import MessageBus
from weavbot.providers.base import LLMProvider
from weavbot.session.manager import Session, SessionManager

if TYPE_CHECKING:
    from weavbot.config.schema import ChannelsConfig, ExecToolConfig
    from weavbot.cron.service import CronService


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    _PARAM_MAX_CHARS = 80  # Max chars per param for channel display; longer values are truncated
    _DEFAULT_ESTIMATE_MULTIPLIER = 1.18
    _DEFAULT_SAFETY_TOKENS = 1536
    _DEFAULT_SAFETY_RATIO = 0.02
    _CALIBRATION_ALPHA = 0.2

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        max_context: int = 131072,
        reasoning_effort: str | None = None,
        web_proxy: str | None = None,
        exec_config: ExecToolConfig | None = None,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        channels_config: ChannelsConfig | None = None,
    ):
        from weavbot.config.schema import ExecToolConfig

        self.bus = bus
        self.channels_config = channels_config
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_context = max_context
        self.reasoning_effort = reasoning_effort
        self.web_proxy = web_proxy
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace

        self.context = ContextBuilder(workspace)
        self.compactor = ContextCompactor()
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort=reasoning_effort,
            web_proxy=web_proxy,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )

        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connecting = False
        self._active_tasks: dict[str, list[asyncio.Task]] = {}  # session_key -> tasks
        self._processing_lock = asyncio.Lock()
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        for cls in (
            ReadFileTool,
            WriteFileTool,
            EditFileTool,
            ListDirTool,
            GlobFileTool,
            GrepFileTool,
        ):
            self.tools.register(cls(workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(
            ShellTool(
                workspace=self.workspace,
                timeout=self.exec_config.timeout,
                restrict_to_workspace=self.restrict_to_workspace,
                path_append=self.exec_config.path_append,
            )
        )
        self.tools.register(LoadMediaTool(workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(WebFetchTool(proxy=self.web_proxy))
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.tools.register(SpawnTool(manager=self.subagents))
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers (one-time, lazy)."""
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from weavbot.agent.tools.mcp import connect_mcp_servers

        try:
            self._mcp_stack = AsyncExitStack()
            await self._mcp_stack.__aenter__()
            await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
            self._mcp_connected = True
        except Exception as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except Exception:
                    pass
                self._mcp_stack = None
        finally:
            self._mcp_connecting = False

    def _set_tool_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Update context for all tools that need routing info."""
        for name in ("message", "spawn", "cron"):
            if tool := self.tools.get(name):
                if hasattr(tool, "set_context"):
                    tool.set_context(channel, chat_id, *([message_id] if name == "message" else []))

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove <think>…</think> blocks that some models embed in content."""
        if not text:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """Format tool calls with name and all params, truncating long values for channel display."""

        def _fmt(tc) -> str:
            args = tc.arguments if isinstance(tc.arguments, dict) else {}
            parts = []
            for k, v in sorted(args.items()):
                v_str = str(v)
                if len(v_str) > AgentLoop._PARAM_MAX_CHARS:
                    v_str = v_str[: AgentLoop._PARAM_MAX_CHARS] + "…"
                if isinstance(v, str):
                    parts.append(f'{k}="{v_str}"')
                else:
                    parts.append(f"{k}={v_str}")
            args_str = ", ".join(parts)
            return f"{tc.name}({args_str})" if args_str else tc.name

        return ", ".join(_fmt(tc) for tc in tool_calls)

    @staticmethod
    def _normalize_usage(usage: dict[str, Any] | None) -> dict[str, int]:
        """Normalize provider usage payload to int counters with safe defaults."""

        def _as_int(key: str) -> int:
            raw = (usage or {}).get(key, 0)
            if isinstance(raw, bool):
                return 0
            if isinstance(raw, int):
                return max(0, raw)
            if isinstance(raw, float):
                return max(0, int(raw))
            return 0

        prompt = _as_int("prompt_tokens")
        completion = _as_int("completion_tokens")
        total = _as_int("total_tokens")
        if total <= 0:
            total = prompt + completion
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }

    def _record_session_token_usage(self, session: Session, turn_usage: dict[str, int]) -> None:
        """Persist token usage stats to session metadata for compact decisions."""
        usage = self._normalize_usage(turn_usage)
        token_usage = session.metadata.get("token_usage")
        token_usage = token_usage if isinstance(token_usage, dict) else {}

        accumulated_prev = token_usage.get("accumulated")
        accumulated_prev = accumulated_prev if isinstance(accumulated_prev, dict) else {}
        accumulated_prev = self._normalize_usage(accumulated_prev)

        accumulated = {
            "prompt_tokens": accumulated_prev["prompt_tokens"] + usage["prompt_tokens"],
            "completion_tokens": accumulated_prev["completion_tokens"] + usage["completion_tokens"],
            "total_tokens": accumulated_prev["total_tokens"] + usage["total_tokens"],
        }

        token_usage.update(
            {
                "last_turn": usage,
                "accumulated": accumulated,
                "context_prompt_tokens": usage["prompt_tokens"],
                "last_updated_at": datetime.now().isoformat(),
                "last_model": self.model,
            }
        )
        session.metadata["token_usage"] = token_usage

    def _get_context_fit_params(self, session: Session) -> dict[str, float | int]:
        """Get conservative context-fit params, with per-session calibration when available."""
        base_multiplier = self._DEFAULT_ESTIMATE_MULTIPLIER
        base_safety = self._DEFAULT_SAFETY_TOKENS
        estimator_meta = session.metadata.get("token_estimator")
        estimator_meta = estimator_meta if isinstance(estimator_meta, dict) else {}
        model_meta = estimator_meta.get(self.model)
        model_meta = model_meta if isinstance(model_meta, dict) else {}
        multiplier_raw = model_meta.get("estimate_multiplier", base_multiplier)
        safety_raw = model_meta.get("safety_tokens", base_safety)
        try:
            multiplier = float(multiplier_raw)
        except (TypeError, ValueError):
            multiplier = base_multiplier
        try:
            safety_tokens = int(safety_raw)
        except (TypeError, ValueError):
            safety_tokens = base_safety
        return {
            "estimate_multiplier": min(3.0, max(1.0, multiplier)),
            "safety_tokens": min(32768, max(256, safety_tokens)),
            "safety_ratio": self._DEFAULT_SAFETY_RATIO,
        }

    def _record_estimation_error(
        self,
        session: Session,
        *,
        estimated_prompt_tokens: int,
        actual_prompt_tokens: int,
    ) -> None:
        """Persist estimate-vs-actual telemetry and update estimator calibration."""
        if estimated_prompt_tokens <= 0 or actual_prompt_tokens <= 0:
            return
        token_usage = session.metadata.get("token_usage")
        token_usage = token_usage if isinstance(token_usage, dict) else {}
        estimation = token_usage.get("estimation")
        estimation = estimation if isinstance(estimation, dict) else {}
        estimation.update(
            {
                "last_estimated_prompt_tokens": int(estimated_prompt_tokens),
                "last_actual_prompt_tokens": int(actual_prompt_tokens),
                "last_ratio": round(actual_prompt_tokens / max(1, estimated_prompt_tokens), 4),
                "last_updated_at": datetime.now().isoformat(),
                "model": self.model,
            }
        )
        token_usage["estimation"] = estimation
        session.metadata["token_usage"] = token_usage

        estimator_meta = session.metadata.get("token_estimator")
        estimator_meta = estimator_meta if isinstance(estimator_meta, dict) else {}
        model_meta = estimator_meta.get(self.model)
        model_meta = model_meta if isinstance(model_meta, dict) else {}
        current_multiplier = model_meta.get(
            "estimate_multiplier", self._DEFAULT_ESTIMATE_MULTIPLIER
        )
        current_safety = model_meta.get("safety_tokens", self._DEFAULT_SAFETY_TOKENS)
        samples = int(model_meta.get("samples", 0) or 0)

        try:
            current_multiplier_f = float(current_multiplier)
        except (TypeError, ValueError):
            current_multiplier_f = self._DEFAULT_ESTIMATE_MULTIPLIER
        try:
            current_safety_i = int(current_safety)
        except (TypeError, ValueError):
            current_safety_i = self._DEFAULT_SAFETY_TOKENS

        observed_ratio = actual_prompt_tokens / max(1, estimated_prompt_tokens)
        alpha = self._CALIBRATION_ALPHA
        calibrated_multiplier = (1.0 - alpha) * current_multiplier_f + alpha * max(
            1.0, observed_ratio
        )
        underestimation = max(0, actual_prompt_tokens - estimated_prompt_tokens)
        calibrated_safety = int((1.0 - alpha) * current_safety_i + alpha * (underestimation + 512))
        model_meta.update(
            {
                "estimate_multiplier": min(3.0, max(1.0, round(calibrated_multiplier, 4))),
                "safety_tokens": min(32768, max(256, calibrated_safety)),
                "samples": samples + 1,
                "last_estimated_prompt_tokens": int(estimated_prompt_tokens),
                "last_actual_prompt_tokens": int(actual_prompt_tokens),
                "last_updated_at": datetime.now().isoformat(),
            }
        )
        estimator_meta[self.model] = model_meta
        session.metadata["token_estimator"] = estimator_meta

    async def _build_initial_messages_with_compaction(
        self,
        session: Session,
        current_message: str,
        *,
        channel: str,
        chat_id: str,
        media: list[str] | None = None,
    ) -> tuple[list[ChatMessage], list[ChatMessage]]:
        """Build initial messages and compact context when output budget cannot fit."""
        history = session.get_history()
        fit_params = self._get_context_fit_params(session)
        initial_messages = self.context.build_messages(
            history=history,
            current_message=current_message,
            media=media,
            channel=channel,
            chat_id=chat_id,
        )

        if self.compactor.can_fit(
            initial_messages, self.max_context, self.max_tokens, **fit_params
        ):
            return history, initial_messages

        estimated_before = self.compactor.estimate_tokens(
            initial_messages, estimate_multiplier=fit_params["estimate_multiplier"]
        )
        logger.info(
            "Context budget exceeded before run (est_prompt={}, max_context={}, max_tokens={}), trying compaction",
            estimated_before,
            self.max_context,
            self.max_tokens,
        )

        if not await self._consolidate_memory(session, up_to_index=len(session.messages)):
            logger.warning("Memory consolidation failed before context compaction; continuing")

        compact = await self.compactor.compact_session_to_new_start(
            session=session,
            history=history,
            provider=self.provider,
            model=self.model,
            estimated_before_tokens=estimated_before,
            max_summary_tokens=min(1200, max(256, self.max_tokens // 2)),
        )

        if compact is None:
            logger.warning("Context compaction skipped/failed; continuing with original history")
            return history, initial_messages

        previous_count = len(session.messages)
        previous_context_cursor = session.context_compacted_cursor
        session.context_compacted_cursor = previous_count
        session.messages.append(compact.seed_message.to_dict())
        session.updated_at = datetime.now()

        compaction_meta = session.metadata.get("compaction")
        compaction_meta = compaction_meta if isinstance(compaction_meta, dict) else {}
        compaction_meta.update(
            {
                "version": 1,
                "last_at": datetime.now().isoformat(),
                "covered_messages": compact.covered_messages,
                "previous_context_cursor": previous_context_cursor,
                "context_cursor_after": session.context_compacted_cursor,
                "memory_cursor_after": session.memory_consolidated_cursor,
                "session_messages_before": previous_count,
                "session_messages_after": len(session.messages),
                "estimated_prompt_tokens_before": compact.estimated_before_tokens,
                "estimated_prompt_tokens_after": compact.estimated_after_tokens,
                "summary_preview": compact.summary[:400],
            }
        )
        session.metadata["compaction"] = compaction_meta

        history = session.get_history()
        initial_messages = self.context.build_messages(
            history=history,
            current_message=current_message,
            media=media,
            channel=channel,
            chat_id=chat_id,
        )
        if not self.compactor.can_fit(
            initial_messages, self.max_context, self.max_tokens, **fit_params
        ):
            initial_messages = self.compactor.shrink_messages_for_runtime(
                initial_messages,
                self.max_context,
                self.max_tokens,
                **fit_params,
            )
        logger.info(
            "Context compacted: covered={} messages, rebuilt_history={}",
            compact.covered_messages,
            len(history),
        )
        return history, initial_messages

    async def _run_agent_loop(
        self,
        session: Session,
        initial_messages: list[ChatMessage],
        on_progress: Callable[..., Awaitable[None]] | None = None,
    ) -> tuple[str | None, list[str], list[ChatMessage], dict[str, int]]:
        """Run the agent iteration loop. Returns (final_content, tools_used, messages, turn_usage)."""
        messages = initial_messages
        fit_params = self._get_context_fit_params(session)
        iteration = 0
        final_content = None
        tools_used: list[str] = []
        turn_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        while iteration < self.max_iterations:
            iteration += 1

            if not self.compactor.can_fit(
                messages, self.max_context, self.max_tokens, **fit_params
            ):
                estimated = self.compactor.estimate_tokens(
                    messages, estimate_multiplier=fit_params["estimate_multiplier"]
                )
                shrunk = self.compactor.shrink_messages_for_runtime(
                    messages,
                    self.max_context,
                    self.max_tokens,
                    **fit_params,
                )
                if shrunk is not messages:
                    logger.info(
                        "Applied runtime context shrink before LLM call #{} (est_prompt={})",
                        iteration,
                        estimated,
                    )
                    messages = shrunk
                if not self.compactor.can_fit(
                    messages, self.max_context, self.max_tokens, **fit_params
                ):
                    hard_shrunk = self.compactor.shrink_messages_for_runtime(
                        messages,
                        self.max_context,
                        self.max_tokens,
                        estimate_multiplier=max(
                            1.0, float(fit_params["estimate_multiplier"]) * 1.1
                        ),
                        safety_tokens=int(fit_params["safety_tokens"]) + 256,
                        safety_ratio=float(fit_params["safety_ratio"]),
                    )
                    if hard_shrunk is not messages:
                        messages = hard_shrunk
                if not self.compactor.can_fit(
                    messages, self.max_context, self.max_tokens, **fit_params
                ):
                    logger.error(
                        "Context exceeds budget after hard shrink (est_prompt={}, budget={}), aborting call",
                        self.compactor.estimate_tokens(
                            messages, estimate_multiplier=fit_params["estimate_multiplier"]
                        ),
                        max(0, self.max_context - self.max_tokens),
                    )
                    final_content = (
                        "Sorry, the current context is too large to process safely. "
                        "Please run /new or reduce the task scope, then try again."
                    )
                    break

            estimated_prompt = self.compactor.estimate_tokens(
                messages, estimate_multiplier=fit_params["estimate_multiplier"]
            )

            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                reasoning_effort=self.reasoning_effort,
            )
            usage = self._normalize_usage(response.usage)
            self._record_estimation_error(
                session,
                estimated_prompt_tokens=estimated_prompt,
                actual_prompt_tokens=usage["prompt_tokens"],
            )
            fit_params = self._get_context_fit_params(session)
            turn_usage["prompt_tokens"] += usage["prompt_tokens"]
            turn_usage["completion_tokens"] += usage["completion_tokens"]
            turn_usage["total_tokens"] += usage["total_tokens"]
            logger.debug(
                "LLM usage call #{}: prompt={}, completion={}, total={}",
                iteration,
                usage["prompt_tokens"],
                usage["completion_tokens"],
                usage["total_tokens"],
            )

            if response.has_tool_calls:
                if on_progress:
                    clean = self._strip_think(response.content)
                    if clean:
                        await on_progress(clean)
                    await on_progress(self._tool_hint(response.tool_calls), tool_hint=True)

                messages = self.context.add_assistant_message(
                    messages,
                    response.content,
                    response.tool_calls,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )

                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info("Tool call: {}({})", tool_call.name, args_str[:200])
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                clean = self._strip_think(response.content)
                # Don't persist error responses to session history — they can
                # poison the context and cause permanent 400 loops (#1303).
                if response.finish_reason == "error":
                    logger.error("LLM returned error: {}", (clean or "")[:200])
                    final_content = clean or "Sorry, I encountered an error calling the AI model."
                    break
                messages = self.context.add_assistant_message(
                    messages,
                    clean,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )
                final_content = clean
                break

        if final_content is None and iteration >= self.max_iterations:
            logger.warning("Max iterations ({}) reached", self.max_iterations)
            final_content = (
                f"I reached the maximum number of tool call iterations ({self.max_iterations}) "
                "without completing the task. You can try breaking the task into smaller steps."
            )

        logger.info(
            "LLM usage turn total: prompt={}, completion={}, total={}",
            turn_usage["prompt_tokens"],
            turn_usage["completion_tokens"],
            turn_usage["total_tokens"],
        )
        return final_content, tools_used, messages, turn_usage

    async def run(self) -> None:
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        self._running = True
        await self._connect_mcp()
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if msg.content.strip().lower() == "/stop":
                await self._handle_stop(msg)
            else:
                task = asyncio.create_task(self._dispatch(msg))
                self._active_tasks.setdefault(msg.session_key, []).append(task)
                task.add_done_callback(
                    lambda t, k=msg.session_key: (
                        self._active_tasks.get(k, []) and self._active_tasks[k].remove(t)
                        if t in self._active_tasks.get(k, [])
                        else None
                    )
                )

    async def _handle_stop(self, msg: InboundMessage) -> None:
        """Cancel all active tasks and subagents for the session."""
        tasks = self._active_tasks.pop(msg.session_key, [])
        cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        sub_cancelled = await self.subagents.cancel_by_session(msg.session_key)
        total = cancelled + sub_cancelled
        content = f"⏹ Stopped {total} task(s)." if total else "No active task to stop."
        await self.bus.publish_outbound(
            OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=content,
            )
        )

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Process a message under the global lock."""
        async with self._processing_lock:
            try:
                response = await self._process_message(msg)
                if response is not None:
                    await self.bus.publish_outbound(response)
                elif msg.channel == "cli":
                    await self.bus.publish_outbound(
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content="",
                            metadata=msg.metadata or {},
                        )
                    )
            except asyncio.CancelledError:
                logger.info("Task cancelled for session {}", msg.session_key)
                raise
            except Exception:
                logger.exception("Error processing message for session {}", msg.session_key)
                await self.bus.publish_outbound(
                    OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="Sorry, I encountered an error.",
                    )
                )

    async def close_mcp(self) -> None:
        """Close MCP connections."""
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        # System messages: parse origin from chat_id ("channel:chat_id")
        if msg.channel == "system":
            channel, chat_id = (
                msg.chat_id.split(":", 1) if ":" in msg.chat_id else ("cli", msg.chat_id)
            )
            logger.info("Processing system message from {}", msg.sender_id)
            key = f"{channel}:{chat_id}"
            session = self.sessions.get_or_create(key)
            self._set_tool_context(channel, chat_id, msg.metadata.get("message_id"))
            history, messages = await self._build_initial_messages_with_compaction(
                session,
                msg.content,
                channel=channel,
                chat_id=chat_id,
            )
            final_content, _, all_msgs, turn_usage = await self._run_agent_loop(session, messages)
            self._save_turn(session, all_msgs, 1 + len(history))
            self._record_session_token_usage(session, turn_usage)
            self.sessions.save(session)
            return OutboundMessage(
                channel=channel,
                chat_id=chat_id,
                content=final_content or "Background task completed.",
            )

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)

        # Slash commands
        cmd = msg.content.strip().lower()
        if cmd == "/new":
            try:
                # /new keeps memory-only archival semantics; no context compaction.
                if not await self._consolidate_memory(session, archive_all=True):
                    return OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="Memory archival failed, session not cleared. Please try again.",
                    )
            except Exception:
                logger.exception("/new archival failed for {}", session.key)
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="Memory archival failed, session not cleared. Please try again.",
                )
            session.clear()
            self.sessions.save(session)
            self.sessions.invalidate(session.key)
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content="New session started."
            )
        if cmd == "/help":
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="🧶 weavbot commands:\n/new — Start a new conversation\n/stop — Stop the current task\n/help — Show available commands",
            )

        self._set_tool_context(msg.channel, msg.chat_id, msg.metadata.get("message_id"))
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.start_turn()

        history, initial_messages = await self._build_initial_messages_with_compaction(
            session,
            msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
        )

        async def _bus_progress(content: str, *, tool_hint: bool = False) -> None:
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            meta["_tool_hint"] = tool_hint
            await self.bus.publish_outbound(
                OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=content,
                    metadata=meta,
                )
            )

        final_content, _, all_msgs, turn_usage = await self._run_agent_loop(
            session,
            initial_messages,
            on_progress=on_progress or _bus_progress,
        )

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        self._save_turn(session, all_msgs, 1 + len(history))
        self._record_session_token_usage(session, turn_usage)
        self.sessions.save(session)

        if (mt := self.tools.get("message")) and isinstance(mt, MessageTool) and mt._sent_in_turn:
            return None

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info("Response to {}:{}: {}", msg.channel, msg.sender_id, preview)
        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata=msg.metadata or {},
        )

    def _save_turn(self, session: Session, messages: list[ChatMessage], skip: int) -> None:
        """Save new-turn messages into session."""
        for msg in messages[skip:]:
            if msg.role == "assistant" and not msg.content and not msg.tool_calls:
                continue
            if msg.role == "user" and msg.content and "</context>" in msg.content:
                content = msg.content.split("</context>", 1)[1].strip() or None
                if not content:
                    continue
                msg = msg.with_content(content)
            if not msg.timestamp:
                msg = msg.with_timestamp(datetime.now().isoformat())
            session.messages.append(msg.to_dict())
        session.updated_at = datetime.now()

    async def _consolidate_memory(
        self, session: Session, archive_all: bool = False, up_to_index: int | None = None
    ) -> bool:
        """Delegate to MemoryStore.consolidate(). Returns True on success."""
        return await MemoryStore(self.workspace).consolidate(
            session,
            self.provider,
            self.model,
            archive_all=archive_all,
            up_to_index=up_to_index,
        )

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """Process a message directly (for CLI or cron usage)."""
        await self._connect_mcp()
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)
        response = await self._process_message(
            msg, session_key=session_key, on_progress=on_progress
        )
        return response.content if response else ""
