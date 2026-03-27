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
        origin_channel: str = "cli",
        origin_chat_id: str = "direct",
        session_key: str | None = None,
        origin_metadata: dict | None = None,
    ) -> str:
        self.last_call = {
            "task": task,
            "label": label,
            "origin_channel": origin_channel,
            "origin_chat_id": origin_chat_id,
            "session_key": session_key,
            "origin_metadata": origin_metadata or {},
        }
        return "spawned"


class _FakeCronService:
    def __init__(self):
        self.last_channel = ""
        self.last_to = ""
        self.last_interactive_channel = ""
        self.last_interactive_chat_id = ""
        self.last_interactive_session_key = ""
        self.last_interactive_metadata: dict = {}

    def add_job(
        self,
        *,
        name: str,
        schedule: CronSchedule,
        message: str,
        deliver: bool,
        channel: str,
        to: str,
        interactive_channel: str | None = None,
        interactive_chat_id: str | None = None,
        interactive_session_key: str | None = None,
        interactive_metadata: dict | None = None,
        delete_after_run: bool,
    ) -> CronJob:
        self.last_channel = channel
        self.last_to = to
        self.last_interactive_channel = interactive_channel or ""
        self.last_interactive_chat_id = interactive_chat_id or ""
        self.last_interactive_session_key = interactive_session_key or ""
        self.last_interactive_metadata = interactive_metadata or {}
        return CronJob(
            id="job-1",
            name=name,
            schedule=schedule,
            payload=CronPayload(
                message=message,
                deliver=deliver,
                channel=channel,
                to=to,
                interactive_channel=interactive_channel,
                interactive_chat_id=interactive_chat_id,
                interactive_session_key=interactive_session_key,
                interactive_metadata=interactive_metadata or {},
            ),
            delete_after_run=delete_after_run,
        )


def test_spawn_tool_uses_execution_context_for_origin() -> None:
    manager = _FakeSpawnManager()
    tool = SpawnTool(manager=manager)
    ctx = ToolExecutionContext(
        channel="telegram",
        chat_id="u1",
        session_key="telegram:chan-1:thread-9",
        metadata={"slack": {"thread_ts": "thread-9"}},
    )
    out = asyncio.run(tool.execute(context=ctx, task="summarize logs", label="logs"))
    assert out == "spawned"
    assert manager.last_call is not None
    assert manager.last_call["origin_channel"] == "telegram"
    assert manager.last_call["origin_chat_id"] == "u1"
    assert manager.last_call["session_key"] == "telegram:chan-1:thread-9"
    assert manager.last_call["origin_metadata"] == {"slack": {"thread_ts": "thread-9"}}


def test_add_cron_tool_routes_delivery_from_execution_context() -> None:
    svc = _FakeCronService()
    tool = AddCronTool(svc)
    ctx = ToolExecutionContext(
        channel="wechat",
        chat_id="peer-1",
        session_key="wechat:peer-1",
        interactive_channel="wechat",
        interactive_chat_id="peer-1",
        interactive_session_key="wechat:bot-a:peer-1",
        interactive_metadata={"wechat": {"account_key": "bot-a"}},
    )
    out = asyncio.run(tool.execute(context=ctx, message="drink water", interval=60))
    assert out.startswith("Created job")
    assert svc.last_channel == "wechat"
    assert svc.last_to == "peer-1"
    assert svc.last_interactive_channel == "wechat"
    assert svc.last_interactive_chat_id == "peer-1"
    assert svc.last_interactive_session_key == "wechat:bot-a:peer-1"
    assert svc.last_interactive_metadata == {"wechat": {"account_key": "bot-a"}}


@pytest.mark.asyncio
async def test_message_tool_context_isolation_across_concurrent_tasks() -> None:
    sent: list[OutboundMessage] = []

    async def _send(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = MessageTool(send_callback=_send)
    ctx_a = ToolExecutionContext(
        channel="telegram",
        chat_id="user-a",
        session_key="telegram:user-a",
        message_id="m-a",
    )
    ctx_b = ToolExecutionContext(
        channel="slack",
        chat_id="user-b",
        session_key="slack:user-b",
        message_id="m-b",
        metadata={"slack": {"thread_ts": "thread-123"}, "channel_type": "group"},
    )

    async def _turn(ctx: ToolExecutionContext, text: str) -> bool:
        ctx.metadata["_message_sent_in_turn"] = False
        await tool.execute(context=ctx, content=text)
        return bool(ctx.metadata.get("_message_sent_in_turn"))

    sent_flags = await asyncio.gather(
        _turn(ctx_a, "hello-a"),
        _turn(ctx_b, "hello-b"),
    )

    assert sent_flags == [True, True]
    assert sorted((m.channel, m.chat_id, m.content) for m in sent) == [
        ("slack", "user-b", "hello-b"),
        ("telegram", "user-a", "hello-a"),
    ]
    b_msg = next(m for m in sent if m.channel == "slack")
    assert b_msg.metadata.get("message_id") == "m-b"
    assert b_msg.metadata.get("slack") == {"thread_ts": "thread-123"}
    assert b_msg.metadata.get("channel_type") == "group"


@pytest.mark.asyncio
async def test_message_tool_does_not_leak_metadata_when_target_differs_from_context() -> None:
    sent: list[OutboundMessage] = []

    async def _send(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = MessageTool(send_callback=_send)
    ctx = ToolExecutionContext(
        channel="slack",
        chat_id="C111",
        session_key="slack:C111:T222",
        message_id="m-orig",
        metadata={"slack": {"thread_ts": "T222"}, "channel_type": "group"},
    )
    await tool.execute(
        context=ctx,
        content="ping elsewhere",
        channel="telegram",
        chat_id="user-9",
    )
    assert len(sent) == 1
    msg = sent[0]
    assert msg.channel == "telegram"
    assert msg.chat_id == "user-9"
    assert msg.metadata.get("slack") is None
    assert msg.metadata.get("channel_type") is None
    assert msg.metadata.get("message_id") == "m-orig"


@pytest.mark.asyncio
async def test_message_tool_prefers_interactive_target_from_context() -> None:
    sent: list[OutboundMessage] = []

    async def _send(msg: OutboundMessage) -> None:
        sent.append(msg)

    tool = MessageTool(send_callback=_send)
    ctx = ToolExecutionContext(
        channel="cli",
        chat_id="direct",
        session_key="heartbeat:slack:C111:2026-03-27",
        message_id="m-hb",
        metadata={"_cron_in_job": True},
        interactive_channel="slack",
        interactive_chat_id="C111",
        interactive_session_key="slack:C111:T333",
        interactive_metadata={"slack": {"thread_ts": "T333", "channel_type": "channel"}},
    )
    await tool.execute(context=ctx, content="heartbeat ping")
    assert len(sent) == 1
    msg = sent[0]
    assert msg.channel == "slack"
    assert msg.chat_id == "C111"
    assert msg.metadata.get("slack") == {"thread_ts": "T333", "channel_type": "channel"}
    assert msg.metadata.get("message_id") == "m-hb"
