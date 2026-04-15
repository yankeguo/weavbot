"""Persistent channel state store backed by a JSON file."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

from weavbot.utils.helpers import ensure_data_path

_SAVE_DEBOUNCE_S = 1.0


class ChannelStateStore:
    """Persistent key-value store for channel-specific send state per chat_id."""

    def __init__(self, path: Path | None = None):
        self._path = path or (ensure_data_path() / "channels.json")
        self._lock = asyncio.Lock()
        self._cache: dict[str, dict[str, dict[str, Any]]] = {}
        self._save_task: asyncio.Task[None] | None = None
        self._load()

    async def get(self, channel: str, chat_id: str) -> dict[str, Any]:
        async with self._lock:
            return dict(self._cache.get(channel, {}).get(chat_id, {}))

    async def set(self, channel: str, chat_id: str, data: dict[str, Any]) -> None:
        async with self._lock:
            self._cache.setdefault(channel, {})[chat_id] = dict(data)
            self._schedule_save_unlocked()

    async def update(self, channel: str, chat_id: str, data: dict[str, Any]) -> None:
        async with self._lock:
            self._cache.setdefault(channel, {}).setdefault(chat_id, {}).update(data)
            self._schedule_save_unlocked()

    async def remove(self, channel: str, chat_id: str) -> None:
        async with self._lock:
            if channel in self._cache and chat_id in self._cache[channel]:
                del self._cache[channel][chat_id]
                self._schedule_save_unlocked()

    def _schedule_save_unlocked(self) -> None:
        if self._save_task is not None and not self._save_task.done():
            self._save_task.cancel()
        self._save_task = asyncio.create_task(self._save_after_delay())

    async def _save_after_delay(self) -> None:
        try:
            await asyncio.sleep(_SAVE_DEBOUNCE_S)
        except asyncio.CancelledError:
            return
        async with self._lock:
            await self._save_unlocked()

    async def _save_unlocked(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(self._cache, ensure_ascii=False, indent=2)
            fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".json")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)
                await asyncio.to_thread(os.replace, tmp, self._path)
            except asyncio.CancelledError:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
                raise
            except Exception:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
                raise
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Failed to save channel state: {}", e)

    @staticmethod
    def _normalize_cache(data: Any) -> dict[str, dict[str, dict[str, Any]]]:
        if not isinstance(data, dict):
            return {}
        normalized: dict[str, dict[str, dict[str, Any]]] = {}
        for channel, channel_data in data.items():
            if not isinstance(channel, str) or not isinstance(channel_data, dict):
                continue
            normalized_channel: dict[str, dict[str, Any]] = {}
            for chat_id, chat_data in channel_data.items():
                if not isinstance(chat_id, str):
                    continue
                normalized_channel[chat_id] = dict(chat_data) if isinstance(chat_data, dict) else {}
            normalized[channel] = normalized_channel
        return normalized

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text("utf-8"))
            self._cache = self._normalize_cache(data)
        except Exception as e:
            logger.warning("Failed to load channel state: {}", e)
            self._cache = {}
