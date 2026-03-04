"""Message bus module for decoupled channel-agent communication."""

from weavbot.bus.events import InboundMessage, OutboundMessage
from weavbot.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
