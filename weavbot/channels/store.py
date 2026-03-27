"""Persistent channel endpoint store keyed by session_key."""

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

_INTERNAL_SESSION_PREFIXES = frozenset({"system", "cli", "cron", "heartbeat"})


def is_internal_session_key(session_key: str) -> bool:
    """True when session_key is a reserved internal partition (cron, heartbeat, ...)."""
    key = (session_key or "").strip()
    if not key:
        return False
    prefix, _, _ = key.partition("_")
    return prefix in _INTERNAL_SESSION_PREFIXES


@dataclass
class ChannelEndpoint:
    """Resolved outbound delivery endpoint for a session."""

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
    def from_dict(cls, raw: dict[str, Any] | None) -> "ChannelEndpoint | None":
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
    """Session-key to channel endpoint mapping with per-session JSON file persistence."""

    def __init__(self, dir: Path):
        self.dir = dir
        self._endpoints: dict[str, ChannelEndpoint] = {}
        self._endpoints_lock = asyncio.Lock()
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
                async with self._endpoints_lock:
                    self._endpoints = {}
                self._loaded = True
                return

            try:
                names = await aiofiles.os.listdir(self.dir)
            except FileNotFoundError:
                async with self._endpoints_lock:
                    self._endpoints = {}
                self._loaded = True
                return
            files = [self.dir / name for name in names if name.endswith(".json")]
            parsed: dict[str, ChannelEndpoint] = {}
            for f in files:
                key = f.stem
                try:
                    async with aiofiles.open(f, encoding="utf-8") as af:
                        content = await af.read()
                    raw = json.loads(content)
                    endpoint = ChannelEndpoint.from_dict(raw if isinstance(raw, dict) else None)
                    if endpoint:
                        parsed[key] = endpoint
                except Exception as e:
                    logger.warning("ChannelStore load failed for {}: {}", f, e)
            async with self._endpoints_lock:
                self._endpoints = parsed
            self._loaded = True

    async def upsert(self, session_key: str, endpoint: ChannelEndpoint) -> None:
        await self._ensure_loaded()
        key = session_key
        key_lock = await self._get_key_lock(key)
        async with key_lock:
            endpoint.updated_at = datetime.now().isoformat()
            await aiofiles.os.makedirs(self.dir, exist_ok=True)
            dest = self.dir / f"{key}.json"
            tmp = self.dir / f".{key}.json.tmp"
            payload = json.dumps(endpoint.to_dict(), indent=2, ensure_ascii=False)
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
            async with self._endpoints_lock:
                self._endpoints[key] = endpoint

    async def delete(self, session_key: str) -> None:
        await self._ensure_loaded()
        key = session_key
        key_lock = await self._get_key_lock(key)
        async with key_lock:
            should_delete_file = False
            async with self._endpoints_lock:
                if key in self._endpoints:
                    del self._endpoints[key]
                    should_delete_file = True
            if should_delete_file:
                try:
                    await aiofiles.os.remove(self.dir / f"{key}.json")
                except FileNotFoundError:
                    pass

    async def resolve(self, session_key: str) -> ChannelEndpoint | None:
        await self._ensure_loaded()
        key = session_key
        async with self._endpoints_lock:
            return self._endpoints.get(key)

    async def most_recent_session_key(
        self,
        *,
        enabled_channels: set[str] | None = None,
        exclude_internal_session_keys: bool = True,
        exclude_channels: frozenset[str] | None = None,
    ) -> str | None:
        """Return session_key with the newest ``updated_at`` among stored endpoints.

        Used for global \"last user-facing interaction\" when no separate pointer file
        is maintained: channel adapters upsert on each message, refreshing ``updated_at``.

        - Skips internal partition keys (``cron_*``, ``heartbeat_*``, ...) when
          ``exclude_internal_session_keys`` is True.
        - Skips endpoints whose ``channel`` is in ``exclude_channels`` (default ``cli``,
          ``system``).
        - When ``enabled_channels`` is set, only considers endpoints whose ``channel`` is
          in that set.
        """
        await self._ensure_loaded()
        skip_ch = exclude_channels if exclude_channels is not None else frozenset({"cli", "system"})
        async with self._endpoints_lock:
            items = list(self._endpoints.items())
        best_key: str | None = None
        best_dt: datetime | None = None
        for sk, ep in items:
            if exclude_internal_session_keys and is_internal_session_key(sk):
                continue
            if ep.channel in skip_ch:
                continue
            if enabled_channels is not None and ep.channel not in enabled_channels:
                continue
            raw = str(ep.updated_at or "").strip()
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            if best_dt is None or dt > best_dt:
                best_dt = dt
                best_key = sk
        return best_key
