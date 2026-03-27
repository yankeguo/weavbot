"""Persistent channel target store keyed by session_key."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

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
        self.load()

    def load(self) -> None:
        if not self.dir.exists():
            self._targets = {}
            return
        parsed: dict[str, ChannelTarget] = {}
        for f in self.dir.glob("*.json"):
            try:
                key = build_session_key(f.stem)
            except ValueError:
                continue
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                target = ChannelTarget.from_dict(raw if isinstance(raw, dict) else None)
                if target:
                    parsed[key] = target
            except Exception as e:
                logger.warning("ChannelStore load failed for {}: {}", f, e)
        self._targets = parsed

    def upsert(self, session_key: str, target: ChannelTarget) -> None:
        try:
            key = build_session_key(str(session_key or "").strip())
        except ValueError:
            return
        target.updated_at = datetime.now().isoformat()
        self._targets[key] = target
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{key}.json").write_text(
            json.dumps(target.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def delete(self, session_key: str) -> None:
        try:
            key = build_session_key(str(session_key or "").strip())
        except ValueError:
            return
        if key in self._targets:
            del self._targets[key]
            (self.dir / f"{key}.json").unlink(missing_ok=True)

    def resolve(self, session_key: str) -> ChannelTarget | None:
        try:
            key = build_session_key(str(session_key or "").strip())
        except ValueError:
            return None
        return self._targets.get(key)
