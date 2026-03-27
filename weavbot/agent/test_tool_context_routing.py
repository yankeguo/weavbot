import asyncio

import pytest

from weavbot.agent.tools.add_cron import AddCronTool
from weavbot.agent.tools.base import ToolExecutionContext
from weavbot.agent.tools.message import MessageTool
from weavbot.agent.tools.spawn import SpawnTool
from weavbot.bus.events import OutboundMessage
from weavbot.channels.store import ChannelTarget
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


class _FakeChannelStore:
    def __init__(self, mapping: dict[str, ChannelTarget] | None = None):
        self.mapping = dict(mapping or {})

    def resolve(self, session_key: str):
        return self.mapping.get(session_key)


def test_spawn_tool_uses_execution_context_for_origin() -> None:
    manager = _FakeSpawnManager()
    store = _FakeChannelStore(
        {
            "telegram_chan-1_thread-9": ChannelTarget(
                channel="telegram",
                chat_id="u1",
                metadata={"slack": {"thread_ts": "thread-9"}},
            )
        }
    )
    tool = SpawnTool(manager=manager, channel_store=store)
    ctx = ToolExecutionContext(session_key="telegram_chan-1_thread-9")
    out = asyncio.run(tool.execute(context=ctx, task="summarize logs", label="logs"))
    assert out == "spawned"
    assert manager.last_call is not None
    assert manager.last_call["origin_channel"] == "telegram"
    assert manager.last_call["origin_chat_id"] == "u1"
    assert manager.last_call["session_key"] == "telegram_chan-1_thread-9"
    assert manager.last_call["origin_metadata"] == {"slack": {"thread_ts": "thread-9"}}


def test_add_cron_tool_routes_delivery_from_execution_context() -> None:
    svc = _FakeCronService()
    store = _FakeChannelStore(
        {
            "wechat_peer-1": ChannelTarget(channel="wechat", chat_id="peer-1", metadata={}),
            "wechat_bot-a_peer-1": ChannelTarget(
                channel="wechat",
                chat_id="peer-1",
                metadata={"wechat": {"account_key": "bot-a"}},
            ),
        }
    )
    tool = AddCronTool(svc, channel_store=store)
    ctx = ToolExecutionContext(
        session_key="wechat_peer-1",
        interactive_session_key="wechat_bot-a_peer-1",
    )
    out = asyncio.run(tool.execute(context=ctx, message="drink water", interval=60))
    assert out.startswith("Created job")
    assert svc.last_channel == "wechat"
    assert svc.last_to == "peer-1"
    assert svc.last_interactive_channel == "wechat"
    assert svc.last_interactive_chat_id == "peer-1"
    assert svc.last_interactive_session_key == "wechat_bot-a_peer-1"
    assert svc.last_interactive_metadata == {"wechat": {"account_key": "bot-a"}}


@pytest.mark.asyncio
async def test_message_tool_context_isolation_across_concurrent_tasks() -> None:
    sent: list[OutboundMessage] = []

    async def _send(msg: OutboundMessage) -> None:
        sent.append(msg)

    store = _FakeChannelStore(
        {
            "telegram_user-a": ChannelTarget(channel="telegram", chat_id="user-a"),
            "slack_user-b": ChannelTarget(channel="slack", chat_id="user-b"),
        }
    )
    tool = MessageTool(send_callback=_send, channel_store=store)
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

    store = _FakeChannelStore(
        {
            "slack_C111_T222": ChannelTarget(channel="slack", chat_id="C111"),
            "telegram_user-9": ChannelTarget(channel="telegram", chat_id="user-9"),
        }
    )
    tool = MessageTool(send_callback=_send, channel_store=store)
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

    store = _FakeChannelStore(
        {
            "heartbeat_slack_C111_2026-03-27": ChannelTarget(channel="cli", chat_id="direct"),
            "slack_C111_T333": ChannelTarget(
                channel="slack",
                chat_id="C111",
                metadata={"slack": {"thread_ts": "T333", "channel_type": "channel"}},
            ),
        }
    )
    tool = MessageTool(send_callback=_send, channel_store=store)
    ctx = ToolExecutionContext(
        session_key="heartbeat_slack_C111_2026-03-27",
        interactive_session_key="slack_C111_T333",
        message_id="m-hb",
    )
    await tool.execute(context=ctx, content="heartbeat ping")
    assert len(sent) == 1
    msg = sent[0]
    assert msg.session_key == "slack_C111_T333"
    assert msg.metadata.get("message_id") == "m-hb"


def test_spawn_tool_fails_when_channel_target_missing() -> None:
    manager = _FakeSpawnManager()
    tool = SpawnTool(manager=manager, channel_store=_FakeChannelStore({}))
    ctx = ToolExecutionContext(session_key="missing_session")
    out = asyncio.run(tool.execute(context=ctx, task="summarize logs"))
    assert out == "Error: no channel target found for session missing_session"
