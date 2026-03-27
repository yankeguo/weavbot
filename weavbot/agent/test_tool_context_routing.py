import asyncio

import pytest

from weavbot.agent.tools.add_cron import AddCronTool
from weavbot.agent.tools.base import ToolExecutionContext
from weavbot.agent.tools.message import MessageTool
from weavbot.agent.tools.spawn import SpawnTool
from weavbot.bus.events import OutboundMessage
from weavbot.cron.types import CronJob, CronPayload, CronSchedule


class _FakeSpawnManager:
    def __init__(self):
        self.last_call: dict | None = None

    async def spawn(
        self,
        task: str,
        label: str | None = None,
        original_session_key: str = "cli_direct",
    ) -> str:
        self.last_call = {
            "task": task,
            "label": label,
            "original_session_key": original_session_key,
        }
        return "spawned"


class _FakeCronService:
    def __init__(self):
        self.last_session_key = ""
        self.last_interactive_session_key = ""

    def add_job(
        self,
        *,
        name: str,
        schedule: CronSchedule,
        message: str,
        deliver: bool,
        original_session_key: str | None = None,
        interactive_session_key: str | None = None,
        delete_after_run: bool,
    ) -> CronJob:
        self.last_session_key = original_session_key or ""
        self.last_interactive_session_key = interactive_session_key or ""
        return CronJob(
            id="job-1",
            name=name,
            schedule=schedule,
            payload=CronPayload(
                message=message,
                deliver=deliver,
                original_session_key=original_session_key,
                interactive_session_key=interactive_session_key,
            ),
            delete_after_run=delete_after_run,
        )


def test_spawn_tool_uses_execution_context_for_origin() -> None:
    manager = _FakeSpawnManager()
    tool = SpawnTool(manager=manager)
    ctx = ToolExecutionContext(session_key="telegram_chan-1_thread-9")
    out = asyncio.run(tool.execute(context=ctx, task="summarize logs", label="logs"))
    assert out == "spawned"
    assert manager.last_call is not None
    assert manager.last_call["original_session_key"] == "telegram_chan-1_thread-9"
    assert manager.last_call["task"] == "summarize logs"
    assert manager.last_call["label"] == "logs"


def test_add_cron_tool_routes_delivery_from_execution_context() -> None:
    svc = _FakeCronService()
    tool = AddCronTool(svc)
    ctx = ToolExecutionContext(
        session_key="wechat_peer-1",
        original_session_key="wechat_bot-a_peer-1",
    )
    out = asyncio.run(tool.execute(context=ctx, message="drink water", interval=60))
    assert out.startswith("Created job")
    assert svc.last_session_key == "wechat_bot-a_peer-1"
    assert svc.last_interactive_session_key == "wechat_bot-a_peer-1"


@pytest.mark.asyncio
async def test_message_tool_context_isolation_across_concurrent_tasks() -> None:
    sent: list[OutboundMessage] = []

    async def _send(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = MessageTool(send_callback=_send)
    ctx_a = ToolExecutionContext(session_key="telegram_user-a", message_id="m-a")
    ctx_b = ToolExecutionContext(session_key="slack_user-b", message_id="m-b")

    async def _turn(ctx: ToolExecutionContext, text: str) -> str:
        await tool.execute(context=ctx, content=text)
        return "done"

    sent_flags = await asyncio.gather(
        _turn(ctx_a, "hello-a"),
        _turn(ctx_b, "hello-b"),
    )

    assert sent_flags == ["done", "done"]
    assert sorted((m.session_key, m.content) for m in sent) == [
        ("slack_user-b", "hello-b"),
        ("telegram_user-a", "hello-a"),
    ]
    b_msg = next(m for m in sent if m.session_key == "slack_user-b")
    assert b_msg.metadata.get("message_id") == "m-b"


@pytest.mark.asyncio
async def test_message_tool_does_not_leak_metadata_when_target_differs_from_context() -> None:
    sent: list[OutboundMessage] = []

    async def _send(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = MessageTool(send_callback=_send)
    ctx = ToolExecutionContext(
        session_key="slack_C111_T222",
        message_id="m-orig",
    )
    await tool.execute(
        context=ctx,
        content="ping elsewhere",
        session_key="telegram_user-9",
    )
    assert len(sent) == 1
    msg = sent[0]
    assert msg.session_key == "telegram_user-9"
    assert msg.metadata.get("message_id") == "m-orig"


@pytest.mark.asyncio
async def test_message_tool_prefers_interactive_target_from_context() -> None:
    sent: list[OutboundMessage] = []

    async def _send(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = MessageTool(send_callback=_send)
    ctx = ToolExecutionContext(
        session_key="heartbeat_slack_C111_2026-03-27",
        original_session_key="slack_C111_T333",
        message_id="m-hb",
    )
    await tool.execute(context=ctx, content="heartbeat ping")
    assert len(sent) == 1
    msg = sent[0]
    assert msg.session_key == "slack_C111_T333"
    assert msg.metadata.get("message_id") == "m-hb"
