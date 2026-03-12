from __future__ import annotations

from typing import Any

import pytest

from weavbot.agent.compact import COMPACTION_SYSTEM_PROMPT, ContextCompactor
from weavbot.agent.loop import AgentLoop
from weavbot.bus.queue import MessageBus
from weavbot.providers.base import LLMProvider, LLMResponse


class _FakeProvider(LLMProvider):
    def __init__(self, *, compaction_ok: bool = True):
        super().__init__()
        self.compaction_ok = compaction_ok

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        system_text = str(messages[0].get("content", "")) if messages else ""
        if COMPACTION_SYSTEM_PROMPT.strip() in system_text:
            if self.compaction_ok:
                return LLMResponse(content="Compacted summary for next session.")
            return LLMResponse(content=None, finish_reason="error")
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
        memory_window=100,
    )
    session = loop.sessions.get_or_create("cli:direct")
    session.add_message("user", "U" * 200)
    session.add_message("assistant", "A" * 200)
    session.add_message("user", "B" * 200)

    history, initial = await loop._build_initial_messages_with_compaction(
        session,
        "continue task",
        channel="cli",
        chat_id="direct",
    )

    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["content"].startswith(ContextCompactor.SEED_PREFIX)
    assert isinstance(session.metadata.get("compaction"), dict)
    assert len(history) == 1
    assert initial[0]["role"] == "system"
    assert initial[-1]["role"] == "user"


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
        memory_window=100,
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
    assert len(history) == len(before)
