from __future__ import annotations

from typing import Any

import pytest

from weavbot.agent.loop import AgentLoop
from weavbot.agent.messages import ChatMessage
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
async def test_system_message_upserts_internal_session_with_origin_route(tmp_path) -> None:
    loop = AgentLoop(
        bus=MessageBus(),
        provider=_FakeProvider(),
        workspace=tmp_path,
        channel_store=ChannelStore(tmp_path / "channels"),
    )
    session_key = build_session_key("system", build_session_key("slack", "C999"))
    msg = InboundMessage(
        channel="system",
        sender_id="subagent",
        chat_id=build_session_key("slack", "C999"),
        session_key=session_key,
        content="subagent done",
        metadata={
            "_origin_channel": "slack",
            "_origin_chat_id": "C999",
            "slack": {"thread_ts": "T111", "channel_type": "channel"},
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
