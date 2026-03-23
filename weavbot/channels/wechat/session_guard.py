"""Per-account session pause guard for Wechat API errcode=-14."""

from __future__ import annotations

import time


class SessionGuard:
    """Pause outbound/inbound API calls for a period after session-expired error."""

    def __init__(self, pause_minutes: int = 60):
        self.pause_seconds = max(1, pause_minutes) * 60
        self._paused_until: dict[str, float] = {}

    def pause(self, account_key: str) -> None:
        self._paused_until[account_key] = time.time() + self.pause_seconds

    def is_paused(self, account_key: str) -> bool:
        until = self._paused_until.get(account_key)
        if not until:
            return False
        if time.time() >= until:
            self._paused_until.pop(account_key, None)
            return False
        return True

    def remaining_seconds(self, account_key: str) -> int:
        until = self._paused_until.get(account_key)
        if not until:
            return 0
        remain = int(until - time.time())
        if remain <= 0:
            self._paused_until.pop(account_key, None)
            return 0
        return remain
