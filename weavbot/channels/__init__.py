"""Chat channels module with plugin architecture."""

from weavbot.channels.base import BaseChannel
from weavbot.channels.manager import ChannelManager
from weavbot.channels.store import ChannelEndpoint, ChannelStore

__all__ = ["BaseChannel", "ChannelManager", "ChannelStore", "ChannelEndpoint"]
