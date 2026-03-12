from __future__ import annotations

from typing import Any

import pytest

from weavbot.agent.compact import COMPACTION_SYSTEM_PROMPT, ContextCompactor
from weavbot.agent.loop import AgentLoop
from weavbot.bus.queue import MessageBus
from weavbot.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class _FakeProvider(LLMProvider):
    def __init__(self, *, compaction_ok: bool = True, memory_ok: bool = True):
        super().__init__()
        self.compaction_ok = compaction_ok
        self.memory_ok = memory_ok
        self.call_order: list[str] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        if tools and any(t.get("function", {}).get("name") == "save_memory" for t in tools):
            self.call_order.append("memory")
            if self.memory_ok:
                return LLMResponse(
                    content=None,
                    tool_calls=[
                        ToolCallRequest(
                            id="save-1",
                            name="save_memory",
                            arguments={
                                "daily_log_entry": "[2026-03-12 10:00] compact test summary",
                                "long_term_memory": "known facts",
                            },
                        )
                    ],
                )
            return LLMResponse(content=None, finish_reason="error")

        system_text = str(messages[0].get("content", "")) if messages else ""
        if COMPACTION_SYSTEM_PROMPT.strip() in system_text:
            self.call_order.append("compact")
            if self.compaction_ok:
                return LLMResponse(content="Compacted summary for next session.")
            return LLMResponse(content=None, finish_reason="error")
        self.call_order.append("main")
        return LLMResponse(content="ok")

    def get_default_model(self) -> str:
        return "fake-model"


def test_runtime_shrink_drops_old_turns() -> None:
    compactor = ContextCompactor()
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u1 " * 300},
        {"role": "assistant", "content": "a1 " * 300},
        {"role": "user", "content": "u2 " * 300},
        {"role": "assistant", "content": "a2 " * 300},
    ]

    shrunk = compactor.shrink_messages_for_runtime(messages, max_context=220, max_output_tokens=120)
    assert len(shrunk) < len(messages)
    assert shrunk[-1]["role"] == "user"
    assert "u2" in str(shrunk[-1]["content"])


@pytest.mark.asyncio
async def test_build_initial_messages_triggers_compaction(tmp_path) -> None:
    bus = MessageBus()
    provider = _FakeProvider(compaction_ok=True)
    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=tmp_path,
        model="fake-model",
        max_tokens=80,
        max_context=140,
    )
    session = loop.sessions.get_or_create("cli:direct")
    session.add_message("user", "U" * 200)
    session.add_message("assistant", "A" * 200)
    session.add_message("user", "B" * 200)
    before_count = len(session.messages)

    history, initial = await loop._build_initial_messages_with_compaction(
        session,
        "continue task",
        channel="cli",
        chat_id="direct",
    )

    assert len(session.messages) == before_count + 1
    assert session.memory_consolidated_cursor == before_count
    assert session.context_compacted_cursor == before_count
    assert session.messages[-1]["role"] == "user"
    assert session.messages[-1]["content"].startswith(ContextCompactor.SEED_PREFIX)
    assert session.messages[-1]["is_compaction_seed"] is True
    assert isinstance(session.metadata.get("compaction"), dict)
    assert len(history) == 1
    assert initial[0]["role"] == "system"
    assert initial[-1]["role"] == "user"
    assert provider.call_order[:2] == ["memory", "compact"]


@pytest.mark.asyncio
async def test_build_initial_messages_compaction_failure_keeps_history(tmp_path) -> None:
    bus = MessageBus()
    provider = _FakeProvider(compaction_ok=False)
    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=tmp_path,
        model="fake-model",
        max_tokens=80,
        max_context=140,
    )
    session = loop.sessions.get_or_create("cli:direct")
    session.add_message("user", "U" * 200)
    session.add_message("assistant", "A" * 200)
    before = list(session.messages)

    history, _ = await loop._build_initial_messages_with_compaction(
        session,
        "continue task",
        channel="cli",
        chat_id="direct",
    )

    assert session.messages == before
    assert session.metadata.get("compaction") is None
    assert session.context_compacted_cursor == 0
    assert session.memory_consolidated_cursor == len(before)
    assert len(history) == len(before)


@pytest.mark.asyncio
async def test_new_command_keeps_memory_only_archival(tmp_path) -> None:
    bus = MessageBus()
    provider = _FakeProvider(compaction_ok=True, memory_ok=True)
    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=tmp_path,
        model="fake-model",
        max_tokens=80,
        max_context=140,
    )
    session = loop.sessions.get_or_create("cli:direct")
    session.add_message("user", "old message 1")
    session.add_message("assistant", "old message 2")

    content = await loop.process_direct(
        "/new", session_key="cli:direct", channel="cli", chat_id="direct"
    )

    assert content == "New session started."
    assert session.messages == []
    assert session.memory_consolidated_cursor == 0
    assert session.context_compacted_cursor == 0
    assert "memory" in provider.call_order
    assert "compact" not in provider.call_order
