"""Session data model and helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from weavbot.agent.messages import ChatMessage


class ContextFitParams(TypedDict):
    """Typed context-fit params for token budget checks."""

    estimate_multiplier: float
    safety_tokens: int
    safety_ratio: float


@dataclass
class Session:
    """
    A conversation session.

    Stores messages in JSONL format for easy reading and persistence.

    Important: Messages are append-only for LLM cache efficiency.
    The consolidation process writes summaries to MEMORY.md and memory/YYYY-MM-DD.md.
    Context compaction manages active history via a separate cursor.
    """

    key: str  # channel:chat_id
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    memory_consolidated_cursor: int = 0  # Number of messages archived to memory files
    context_compacted_cursor: int = 0  # Start index for active context history

    def append_chat_message(self, message: "ChatMessage") -> None:
        """Append a typed chat message to session storage."""
        msg = message if message.timestamp else message.with_timestamp(datetime.now().isoformat())
        self.messages.append(msg.to_dict())
        self.updated_at = datetime.now()

    def get_history(self, max_messages: int = 500) -> list["ChatMessage"]:
        """Return active messages for LLM input, aligned to a user turn."""
        from weavbot.agent.messages import ChatMessage

        start = max(self.memory_consolidated_cursor, self.context_compacted_cursor)
        if start < 0:
            start = 0
        if start > len(self.messages):
            start = len(self.messages)
        unconsolidated = self.messages[start:]
        sliced = unconsolidated[-max_messages:]

        for i, m in enumerate(sliced):
            if m.get("role") == "user":
                sliced = sliced[i:]
                break

        return [ChatMessage.from_dict(m) for m in sliced]

    def get_context_fit_params(
        self,
        *,
        model: str,
        default_estimate_multiplier: float,
        default_safety_tokens: int,
        default_safety_ratio: float,
    ) -> ContextFitParams:
        """Get conservative context-fit params with per-session calibration when available."""
        estimator_meta = self.metadata.get("token_estimator")
        estimator_meta = estimator_meta if isinstance(estimator_meta, dict) else {}
        model_meta = estimator_meta.get(model)
        model_meta = model_meta if isinstance(model_meta, dict) else {}
        multiplier_raw = model_meta.get("estimate_multiplier", default_estimate_multiplier)
        safety_raw = model_meta.get("safety_tokens", default_safety_tokens)
        try:
            multiplier = float(multiplier_raw)
        except (TypeError, ValueError):
            multiplier = default_estimate_multiplier
        try:
            safety_tokens = int(safety_raw)
        except (TypeError, ValueError):
            safety_tokens = default_safety_tokens
        return {
            "estimate_multiplier": min(3.0, max(1.0, multiplier)),
            "safety_tokens": min(32768, max(256, safety_tokens)),
            "safety_ratio": default_safety_ratio,
        }

    def clear(self) -> None:
        """Clear all messages and reset session to initial state."""
        self.messages = []
        self.memory_consolidated_cursor = 0
        self.context_compacted_cursor = 0
        self.updated_at = datetime.now()
