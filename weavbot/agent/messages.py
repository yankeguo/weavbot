"""Typed message structures for the agent pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass
class ToolCallRequest:
    """A tool call request from the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatMessage:
    """A typed message in the conversation pipeline.

    Media files are stored as file paths throughout the pipeline.
    Base64 encoding happens only at the Provider layer.
    """

    role: str
    content: str | None = None
    media: list[str] = field(default_factory=list)
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: str | None = None
    reasoning_content: str | None = None
    thinking_blocks: list[dict] | None = None
    timestamp: str | None = None
    is_compaction_seed: bool = False

    def with_content(self, content: str | None) -> ChatMessage:
        """Return a copy with replaced content."""
        return replace(self, content=content)

    def with_timestamp(self, timestamp: str) -> ChatMessage:
        """Return a copy with replaced timestamp."""
        return replace(self, timestamp=timestamp)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSONL session storage."""
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.media:
            d["media"] = list(self.media)
        if self.tool_calls:
            d["tool_calls"] = [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in self.tool_calls
            ]
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        if self.tool_name is not None:
            d["tool_name"] = self.tool_name
        if self.reasoning_content is not None:
            d["reasoning_content"] = self.reasoning_content
        if self.thinking_blocks is not None:
            d["thinking_blocks"] = self.thinking_blocks
        if self.timestamp is not None:
            d["timestamp"] = self.timestamp
        if self.is_compaction_seed:
            d["is_compaction_seed"] = True
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChatMessage:
        """Deserialize from dict."""
        content = data.get("content")
        if content is not None and not isinstance(content, str):
            content = str(content)

        tool_calls = [
            ToolCallRequest(
                id=tc.get("id", ""),
                name=tc.get("name", ""),
                arguments=tc.get("arguments") if isinstance(tc.get("arguments"), dict) else {},
            )
            for tc in data.get("tool_calls", [])
            if isinstance(tc, dict)
        ]

        return cls(
            role=data.get("role", "user"),
            content=content,
            media=list(data.get("media") or []),
            tool_calls=tool_calls,
            tool_call_id=data.get("tool_call_id"),
            tool_name=data.get("tool_name"),
            reasoning_content=data.get("reasoning_content"),
            thinking_blocks=data.get("thinking_blocks"),
            timestamp=data.get("timestamp"),
            is_compaction_seed=bool(data.get("is_compaction_seed")),
        )
