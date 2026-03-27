"""Event types for the message bus."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class InboundMessage:
    """Message received from a chat channel."""

    channel: str  # telegram, discord, slack, etc.
    # Sender identity for auth/allowlist and observability.
    # It is not used as the session partition key or outbound delivery target.
    sender_id: str
    chat_id: str  # Chat/channel identifier
    session_key: str  # Explicit session partition key (must be non-empty)
    content: str  # Message text
    timestamp: datetime = field(default_factory=datetime.now)
    media: list[str] = field(default_factory=list)  # Local image file paths for multimodal input
    metadata: dict[str, Any] = field(default_factory=dict)  # Channel-specific data

    @staticmethod
    def default_session_key(channel: str, chat_id: str) -> str:
        """Build the default session key from channel/chat."""
        return f"{channel}:{chat_id}"


@dataclass
class OutboundMessage:
    """Message to send to a chat channel."""

    channel: str
    chat_id: str
    content: str
    reply_to: str | None = None
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
