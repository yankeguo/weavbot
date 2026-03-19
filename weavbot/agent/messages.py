"""Typed message structures for the agent pipeline."""

from __future__ import annotations

import json
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

        def _coerce_str(v: Any) -> str | None:
            if v is None:
                return None
            return v if isinstance(v, str) else str(v)

        def _coerce_media(v: Any) -> list[str]:
            if v is None:
                return []
            if isinstance(v, str):
                return [v]
            if isinstance(v, list):
                return [str(x) for x in v if x is not None]
            return [str(v)]

        def _coerce_tool_calls(v: Any) -> list[dict[str, Any]]:
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
            if isinstance(v, dict):
                return [v]
            return []

        def _coerce_bool(v: Any) -> bool:
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                return v.strip().lower() in {"1", "true", "yes", "on"}
            if isinstance(v, (int, float)):
                return v != 0
            return bool(v)

        content = data.get("content")
        if isinstance(content, list):
            # Legacy content arrays are often OpenAI/Anthropic blocks; extract text when possible.
            text_parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        text_parts.append(text)
            content = "\n".join(text_parts) if text_parts else str(content)
        else:
            content = _coerce_str(content)

        tool_calls: list[ToolCallRequest] = []
        for tc in _coerce_tool_calls(data.get("tool_calls")):
            # Support both flat {"id","name","arguments"} and legacy {"function":{"name","arguments"}}
            func = tc.get("function", {}) if "function" in tc else tc
            args = func.get("arguments", {})
            if isinstance(args, str):
                try:
                    parsed = json.loads(args)
                    args = parsed if isinstance(parsed, dict) else {}
                except Exception:
                    args = {}
            tool_calls.append(
                ToolCallRequest(
                    id=_coerce_str(tc.get("id")) or "",
                    name=_coerce_str(func.get("name")) or "",
                    arguments=args if isinstance(args, dict) else {},
                )
            )

        return cls(
            role=_coerce_str(data.get("role")) or "user",
            content=content,
            media=_coerce_media(data.get("media")),
            tool_calls=tool_calls,
            tool_call_id=_coerce_str(data.get("tool_call_id")),
            tool_name=_coerce_str(data.get("tool_name")) or _coerce_str(data.get("name")),
            reasoning_content=_coerce_str(data.get("reasoning_content")),
            thinking_blocks=(
                data.get("thinking_blocks")
                if isinstance(data.get("thinking_blocks"), list)
                else None
            ),
            timestamp=_coerce_str(data.get("timestamp")),
            is_compaction_seed=_coerce_bool(data.get("is_compaction_seed")),
        )
