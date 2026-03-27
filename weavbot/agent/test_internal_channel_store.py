from __future__ import annotations

import asyncio
from typing import Any

import pytest

from weavbot.agent.loop import AgentLoop
from weavbot.agent.messages import ChatMessage, ToolCallRequest
from weavbot.bus.events import InboundMessage
from weavbot.bus.queue import MessageBus
from weavbot.channels.store import ChannelStore, ChannelTarget
from weavbot.providers.base import LLMProvider, LLMResponse
from weavbot.utils.helpers import build_session_key


class _FakeProvider(LLMProvider):
    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        return LLMResponse(content="ok")

    def get_default_model(self) -> str:
        return "fake-model"


class _MessageToolProvider(LLMProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="sending",
                tool_calls=[
                    ToolCallRequest(
                        id="call-1", name="message", arguments={"content": "cron notify"}
                    )
                ],
            )
        return LLMResponse(content="done")

    def get_default_model(self) -> str:
        return "fake-model"


@pytest.mark.asyncio
async def test_process_direct_upserts_cli_internal_session_to_channel_store(tmp_path) -> None:
    loop = AgentLoop(
        bus=MessageBus(),
        provider=_FakeProvider(),
        workspace=tmp_path,
        channel_store=ChannelStore(tmp_path / "channels"),
    )
    session_key = build_session_key("cli", "direct")

    out = await loop.process_direct(
        "hello", session_key=session_key, channel="cli", chat_id="direct"
    )

    assert out == "ok"
    target = loop.channel_store.resolve(session_key) if loop.channel_store else None
    assert target is not None
    assert target.channel == "cli"
    assert target.chat_id == "direct"
    assert target.metadata == {}


@pytest.mark.asyncio
async def test_process_direct_prefers_interactive_route_for_cron_internal_session(tmp_path) -> None:
    loop = AgentLoop(
        bus=MessageBus(),
        provider=_FakeProvider(),
        workspace=tmp_path,
        channel_store=ChannelStore(tmp_path / "channels"),
    )
    session_key = build_session_key("cron", "job-1")
    interactive_session_key = build_session_key("slack", "C111", "T333")
    assert loop.channel_store is not None
    loop.channel_store.upsert(
        interactive_session_key,
        ChannelTarget(
            channel="slack",
            chat_id="C111",
            metadata={
                "slack": {"thread_ts": "T333", "channel_type": "channel", "unused": "drop-me"},
                "extra": "drop-me",
            },
        ),
    )

    out = await loop.process_direct(
        "cron task",
        session_key=session_key,
        channel="cli",
        chat_id="direct",
        interactive_session_key=interactive_session_key,
    )

    assert out == "ok"
    target = loop.channel_store.resolve(session_key) if loop.channel_store else None
    assert target is not None
    assert target.channel == "slack"
    assert target.chat_id == "C111"
    assert target.metadata == {"slack": {"thread_ts": "T333", "channel_type": "channel"}}


@pytest.mark.asyncio
async def test_system_message_upserts_internal_session_with_original_session_key(
    tmp_path,
) -> None:
    loop = AgentLoop(
        bus=MessageBus(),
        provider=_FakeProvider(),
        workspace=tmp_path,
        channel_store=ChannelStore(tmp_path / "channels"),
    )
    original_key = build_session_key("slack", "C999", "T111")
    session_key = build_session_key("system", "sub", "task-42")
    assert loop.channel_store is not None
    loop.channel_store.upsert(
        original_key,
        ChannelTarget(
            channel="slack",
            chat_id="C999",
            metadata={"slack": {"thread_ts": "T111", "channel_type": "channel"}},
        ),
    )
    msg = InboundMessage(
        channel="system",
        sender_id="subagent",
        chat_id="subagent",
        session_key=session_key,
        content="subagent done",
        metadata={
            "_original_session_key": original_key,
        },
    )

    out = await loop._process_message(msg)

    assert out is not None
    assert out.content == "ok"
    target = loop.channel_store.resolve(session_key) if loop.channel_store else None
    assert target is not None
    assert target.channel == "slack"
    assert target.chat_id == "C999"
    assert target.metadata == {"slack": {"thread_ts": "T111", "channel_type": "channel"}}


@pytest.mark.asyncio
async def test_process_direct_message_tool_to_interactive_target_skips_extra_final_reply(
    tmp_path,
) -> None:
    bus = MessageBus()
    loop = AgentLoop(
        bus=bus,
        provider=_MessageToolProvider(),
        workspace=tmp_path,
        channel_store=ChannelStore(tmp_path / "channels"),
    )
    internal_key = build_session_key("cron", "job-42")
    interactive_key = build_session_key("slack", "C111", "T333")

    out = await loop.process_direct(
        "run cron",
        session_key=internal_key,
        channel="cli",
        chat_id="direct",
        interactive_session_key=interactive_key,
    )

    assert out == ""
    pushed: list = []
    while bus.outbound_size:
        pushed.append(await asyncio.wait_for(bus.consume_outbound(), timeout=1.0))
    sent_messages = [m for m in pushed if not bool((m.metadata or {}).get("_progress"))]
    assert len(sent_messages) == 1
    assert sent_messages[0].session_key == interactive_key
    assert sent_messages[0].content == "cron notify"


@pytest.mark.asyncio
async def test_system_message_prefers_channel_store_target_over_chat_id_split(tmp_path) -> None:
    store = ChannelStore(tmp_path / "channels")
    loop = AgentLoop(
        bus=MessageBus(),
        provider=_FakeProvider(),
        workspace=tmp_path,
        channel_store=store,
    )
    session_key = build_session_key("system", build_session_key("slack", "C999", "T111"))
    store.upsert(
        session_key,
        ChannelTarget(
            channel="slack",
            chat_id="C999",
            metadata={"slack": {"thread_ts": "T111", "channel_type": "channel"}},
        ),
    )
    msg = InboundMessage(
        channel="system",
        sender_id="subagent",
        chat_id=build_session_key("slack", "C999", "T111"),
        session_key=session_key,
        content="subagent done",
        metadata={},
    )

    out = await loop._process_message(msg)

    assert out is not None
    target = store.resolve(session_key)
    assert target is not None
    assert target.chat_id == "C999"


@pytest.mark.asyncio
async def test_system_message_uses_original_session_key_routing(tmp_path) -> None:
    store = ChannelStore(tmp_path / "channels")
    loop = AgentLoop(
        bus=MessageBus(),
        provider=_FakeProvider(),
        workspace=tmp_path,
        channel_store=store,
    )
    original_key = build_session_key("slack", "C777", "T888")
    sub_key = build_session_key("system", "sub", "task-1")
    store.upsert(
        original_key,
        ChannelTarget(
            channel="slack",
            chat_id="C777",
            metadata={"slack": {"thread_ts": "T888", "channel_type": "channel"}},
        ),
    )
    msg = InboundMessage(
        channel="system",
        sender_id="subagent",
        chat_id="subagent",
        session_key=sub_key,
        content="subagent done",
        metadata={"_original_session_key": original_key},
    )

    out = await loop._process_message(msg)

    assert out is not None
    assert out.content == "ok"
    target = store.resolve(sub_key)
    assert target is not None
    assert target.channel == "slack"
    assert target.chat_id == "C777"
    assert target.metadata == {"slack": {"thread_ts": "T888", "channel_type": "channel"}}


@pytest.mark.asyncio
async def test_system_message_returns_error_when_route_unresolved(tmp_path) -> None:
    loop = AgentLoop(
        bus=MessageBus(),
        provider=_FakeProvider(),
        workspace=tmp_path,
        channel_store=ChannelStore(tmp_path / "channels"),
    )
    msg = InboundMessage(
        channel="system",
        sender_id="subagent",
        chat_id="slack_C999",
        session_key=build_session_key("system", "missing-target"),
        content="subagent done",
        metadata={},
    )

    out = await loop._process_message(msg)

    assert out is not None
    assert out.content == "System message dropped: unresolved target session."
