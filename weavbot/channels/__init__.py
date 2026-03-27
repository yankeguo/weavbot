"""Chat channels module with plugin architecture."""

from weavbot.channels.base import BaseChannel
from weavbot.channels.manager import ChannelManager
from weavbot.channels.store import ChannelStore, ChannelTarget

__all__ = ["BaseChannel", "ChannelManager", "ChannelStore", "ChannelTarget"]
