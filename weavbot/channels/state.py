"""Persistent channel state store backed by a JSON file."""

import asyncio
import json
from pathlib import Path
from typing import Any

from loguru import logger

from weavbot.utils.helpers import ensure_data_path


class ChannelStateStore:
    """Persistent key-value store for channel-specific send state per chat_id."""

    def __init__(self, path: Path | None = None):
        self._path = path or (ensure_data_path() / "channels.json")
        self._lock = asyncio.Lock()
        self._cache: dict[str, dict[str, dict[str, Any]]] = {}
        self._load()

    async def get(self, channel: str, chat_id: str) -> dict[str, Any]:
        async with self._lock:
            return dict(self._cache.get(channel, {}).get(chat_id, {}))

    async def set(self, channel: str, chat_id: str, data: dict[str, Any]) -> None:
        async with self._lock:
            self._cache.setdefault(channel, {})[chat_id] = dict(data)
            await self._save_unlocked()

    async def update(self, channel: str, chat_id: str, data: dict[str, Any]) -> None:
        async with self._lock:
            self._cache.setdefault(channel, {}).setdefault(chat_id, {}).update(data)
            await self._save_unlocked()

    async def remove(self, channel: str, chat_id: str) -> None:
        async with self._lock:
            if channel in self._cache and chat_id in self._cache[channel]:
                del self._cache[channel][chat_id]
                await self._save_unlocked()

    async def _save_unlocked(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(self._cache, ensure_ascii=False, indent=2)
            await asyncio.to_thread(self._path.write_text, content, "utf-8")
        except Exception as e:
            logger.warning("Failed to save channel state: {}", e)

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text("utf-8"))
            if isinstance(data, dict):
                self._cache = data
        except Exception as e:
            logger.warning("Failed to load channel state: {}", e)
            self._cache = {}
