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
    ) -> str:
        self.last_call = {
            "task": task,
            "label": label,
            "origin_channel": origin_channel,
            "origin_chat_id": origin_chat_id,
            "session_key": session_key,
        }
        return "spawned"


class _FakeCronService:
    def __init__(self):
        self.last_channel = ""
        self.last_to = ""

    def add_job(
        self,
        *,
        name: str,
        schedule: CronSchedule,
        message: str,
        deliver: bool,
        channel: str,
        to: str,
        delete_after_run: bool,
    ) -> CronJob:
        self.last_channel = channel
        self.last_to = to
        return CronJob(
            id="job-1",
            name=name,
            schedule=schedule,
            payload=CronPayload(message=message, deliver=deliver, channel=channel, to=to),
            delete_after_run=delete_after_run,
        )


def test_spawn_tool_uses_execution_context_for_origin() -> None:
    manager = _FakeSpawnManager()
    tool = SpawnTool(manager=manager)
    ctx = ToolExecutionContext(channel="telegram", chat_id="u1", session_key="telegram:u1")
    out = asyncio.run(tool.execute(context=ctx, task="summarize logs", label="logs"))
    assert out == "spawned"
    assert manager.last_call is not None
    assert manager.last_call["origin_channel"] == "telegram"
    assert manager.last_call["origin_chat_id"] == "u1"
    assert manager.last_call["session_key"] == "telegram:u1"


def test_add_cron_tool_routes_delivery_from_execution_context() -> None:
    svc = _FakeCronService()
    tool = AddCronTool(svc)
    ctx = ToolExecutionContext(channel="wechat", chat_id="peer-1", session_key="wechat:peer-1")
    out = asyncio.run(tool.execute(context=ctx, message="drink water", interval=60))
    assert out.startswith("Created job")
    assert svc.last_channel == "wechat"
    assert svc.last_to == "peer-1"


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
    )

    async def _turn(ctx: ToolExecutionContext, text: str) -> bool:
        tool.start_turn()
        await tool.execute(context=ctx, content=text)
        return tool._sent_in_turn

    sent_flags = await asyncio.gather(
        _turn(ctx_a, "hello-a"),
        _turn(ctx_b, "hello-b"),
    )

    assert sent_flags == [True, True]
    assert sorted((m.channel, m.chat_id, m.content) for m in sent) == [
        ("slack", "user-b", "hello-b"),
        ("telegram", "user-a", "hello-a"),
    ]
