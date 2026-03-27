"""Event types for the message bus.

Inbound messages are produced by channel adapters (or internal publishers such as
subagents) and queued for the agent. Outbound messages are produced by the agent
(or tools) and queued for delivery; the consumer resolves ``session_key`` via
:class:`~weavbot.channels.store.ChannelStore` to obtain a :class:`~weavbot.channels.store.ChannelTarget`.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class InboundMessage:
    """Message received from a chat channel or injected on the inbound queue.

    ``session_key`` is the stable partition for conversation state; channel
    adapters typically build it with :func:`~weavbot.utils.helpers.build_session_key`,
    but callers may set a custom key when they need a distinct session (e.g. multi-account).

    Internal channels include ``system`` (e.g. subagent handoff with
    ``metadata["_original_session_key"]`` for routing) and ``cli`` for terminal
    runs. ``sender_id`` identifies who sent the message for allowlists and logs;
    delivery routing uses ``session_key`` and the store, not ``sender_id``.
    """

    channel: str  # Platform name: telegram, slack, wecom, system, cli, ...
    # Sender identity for auth/allowlist and observability.
    # It is not used as the session partition key or outbound delivery target.
    sender_id: str
    chat_id: (
        str  # Opaque chat/thread id from the platform (also embedded in session_key when default).
    )
    session_key: (
        str  # Stable partition key for Session state; must be non-empty and store-normalized.
    )
    content: str  # User-visible message text (may be a synthetic command for some channels).
    timestamp: datetime = field(default_factory=datetime.now)
    media: list[str] = field(default_factory=list)  # Local image file paths for multimodal input
    metadata: dict[str, Any] = field(
        default_factory=dict
    )  # e.g. message_id, channel-specific blobs, _progress


@dataclass
class OutboundMessage:
    """Message queued for sending to a chat; resolved through ``session_key`` → ChannelTarget."""

    session_key: str  # Lookup key for outbound routing (same namespace as inbound).
    content: str  # Body to send; may be empty when only metadata matters (e.g. typing signals).
    reply_to: str | None = None  # Platform message id to reply in-thread (Discord, Mochat, etc.).
    media: list[str] = field(default_factory=list)  # Local paths for attachments to send
    metadata: dict[str, Any] = field(
        default_factory=dict
    )  # Echo/propagate inbound fields; e.g. message_id for Telegram quotes
