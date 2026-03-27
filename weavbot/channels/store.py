"""Persistent channel target store keyed by session_key."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles
import aiofiles.os
import aiofiles.ospath
from loguru import logger

from weavbot.utils.helpers import build_session_key


@dataclass
class ChannelTarget:
    """Resolved outbound delivery target for a session."""

    channel: str
    chat_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "chat_id": self.chat_id,
            "metadata": dict(self.metadata or {}),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "ChannelTarget | None":
        payload = raw if isinstance(raw, dict) else {}
        channel = str(payload.get("channel") or "").strip()
        chat_id = str(payload.get("chat_id") or "").strip()
        if not channel or not chat_id:
            return None
        metadata = payload.get("metadata")
        return cls(
            channel=channel,
            chat_id=chat_id,
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
            updated_at=str(payload.get("updated_at") or datetime.now().isoformat()),
        )


class ChannelStore:
    """Session-key to channel target mapping with per-session JSON file persistence."""

    def __init__(self, dir: Path):
        self.dir = dir
        self._targets: dict[str, ChannelTarget] = {}
        self._targets_lock = asyncio.Lock()
        self._key_locks_lock = asyncio.Lock()
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._load_lock = asyncio.Lock()
        self._loaded = False

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        await self.load()

    async def _get_key_lock(self, key: str) -> asyncio.Lock:
        async with self._key_locks_lock:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._key_locks[key] = lock
            return lock

    async def load(self) -> None:
        async with self._load_lock:
            exists = await aiofiles.ospath.exists(self.dir)
            if not exists:
                async with self._targets_lock:
                    self._targets = {}
                self._loaded = True
                return

            try:
                names = await aiofiles.os.listdir(self.dir)
            except FileNotFoundError:
                async with self._targets_lock:
                    self._targets = {}
                self._loaded = True
                return
            files = [self.dir / name for name in names if name.endswith(".json")]
            parsed: dict[str, ChannelTarget] = {}
            for f in files:
                try:
                    key = build_session_key(f.stem)
                except ValueError:
                    continue
                try:
                    async with aiofiles.open(f, encoding="utf-8") as af:
                        content = await af.read()
                    raw = json.loads(content)
                    target = ChannelTarget.from_dict(raw if isinstance(raw, dict) else None)
                    if target:
                        parsed[key] = target
                except Exception as e:
                    logger.warning("ChannelStore load failed for {}: {}", f, e)
            async with self._targets_lock:
                self._targets = parsed
            self._loaded = True

    async def upsert(self, session_key: str, target: ChannelTarget) -> None:
        await self._ensure_loaded()
        try:
            key = build_session_key(str(session_key or "").strip())
        except ValueError as e:
            logger.warning(
                "ChannelStore upsert ignored invalid session_key '{}': {}", session_key, e
            )
            return
        key_lock = await self._get_key_lock(key)
        async with key_lock:
            target.updated_at = datetime.now().isoformat()
            await aiofiles.os.makedirs(self.dir, exist_ok=True)
            dest = self.dir / f"{key}.json"
            tmp = self.dir / f".{key}.json.tmp"
            payload = json.dumps(target.to_dict(), indent=2, ensure_ascii=False)
            try:
                async with aiofiles.open(tmp, "w", encoding="utf-8") as af:
                    await af.write(payload)
                await aiofiles.os.replace(tmp, dest)
            except Exception as e:
                logger.error("ChannelStore upsert failed for key '{}': {}", key, e)
                try:
                    await aiofiles.os.remove(tmp)
                except FileNotFoundError:
                    pass
                except Exception:
                    pass
                return
            async with self._targets_lock:
                self._targets[key] = target

    async def delete(self, session_key: str) -> None:
        await self._ensure_loaded()
        try:
            key = build_session_key(str(session_key or "").strip())
        except ValueError as e:
            logger.warning(
                "ChannelStore delete ignored invalid session_key '{}': {}", session_key, e
            )
            return
        key_lock = await self._get_key_lock(key)
        async with key_lock:
            should_delete_file = False
            async with self._targets_lock:
                if key in self._targets:
                    del self._targets[key]
                    should_delete_file = True
            if should_delete_file:
                try:
                    await aiofiles.os.remove(self.dir / f"{key}.json")
                except FileNotFoundError:
                    pass

    async def resolve(self, session_key: str) -> ChannelTarget | None:
        await self._ensure_loaded()
        try:
            key = build_session_key(str(session_key or "").strip())
        except ValueError as e:
            logger.warning(
                "ChannelStore resolve ignored invalid session_key '{}': {}", session_key, e
            )
            return None
        async with self._targets_lock:
            return self._targets.get(key)
