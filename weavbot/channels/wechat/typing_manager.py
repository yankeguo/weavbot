"""Typing status helpers for Wechat channel."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from loguru import logger

from weavbot.channels.wechat.api import WechatApiClient
from weavbot.channels.wechat.types import TYPING_STATUS_CANCEL, TYPING_STATUS_TYPING

_INITIAL_RETRY_DELAY_SEC = 2.0
_MAX_RETRY_DELAY_SEC = 3600.0


@dataclass(slots=True)
class _TypingCacheEntry:
    ticket: str
    updated_at: float
    ever_succeeded: bool
    next_fetch_at: float
    retry_delay_sec: float = _INITIAL_RETRY_DELAY_SEC


class TypingManager:
    """Cache typing tickets and send typing/cancel events."""

    def __init__(self, ttl_sec: int = 300):
        self.ttl_sec = max(10, ttl_sec)
        self._cache: dict[str, _TypingCacheEntry] = {}

    def _cache_key(self, account_key: str, user_id: str) -> str:
        return f"{account_key}:{user_id}"

    async def get_ticket(
        self, api: WechatApiClient, account_key: str, user_id: str, context_token: str | None
    ) -> str | None:
        key = self._cache_key(account_key, user_id)
        now = time.time()
        entry = self._cache.get(key)
        should_fetch = not entry or now >= entry.next_fetch_at

        if should_fetch:
            fetch_ok = False
            try:
                resp = await api.get_config(user_id, context_token=context_token)
                if int(resp.get("ret", 0) or 0) == 0:
                    ticket = str(resp.get("typing_ticket", "")).strip()
                    if ticket:
                        jittered_ttl = self.ttl_sec * random.uniform(0.5, 1.0)
                        self._cache[key] = _TypingCacheEntry(
                            ticket=ticket,
                            updated_at=now,
                            ever_succeeded=True,
                            next_fetch_at=now + jittered_ttl,
                            retry_delay_sec=_INITIAL_RETRY_DELAY_SEC,
                        )
                        fetch_ok = True
            except Exception as exc:
                logger.debug("Wechat getConfig failed for typing: {}", exc)

            if not fetch_ok:
                prev_delay = entry.retry_delay_sec if entry else _INITIAL_RETRY_DELAY_SEC
                next_delay = min(prev_delay * 2, _MAX_RETRY_DELAY_SEC)
                if entry:
                    entry.next_fetch_at = now + next_delay
                    entry.retry_delay_sec = next_delay
                else:
                    self._cache[key] = _TypingCacheEntry(
                        ticket="",
                        updated_at=now,
                        ever_succeeded=False,
                        next_fetch_at=now + _INITIAL_RETRY_DELAY_SEC,
                        retry_delay_sec=_INITIAL_RETRY_DELAY_SEC,
                    )

        cached = self._cache.get(key)
        return cached.ticket if cached and cached.ticket else None

    async def send_typing(
        self, api: WechatApiClient, account_key: str, user_id: str, context_token: str | None
    ) -> str | None:
        if not user_id:
            return None
        ticket = await self.get_ticket(api, account_key, user_id, context_token)
        if not ticket:
            return None
        try:
            await api.send_typing(user_id, ticket, TYPING_STATUS_TYPING)
            return ticket
        except Exception as exc:
            logger.debug("Wechat sendTyping(typing) failed: {}", exc)
            return None

    async def cancel_typing(
        self,
        api: WechatApiClient,
        account_key: str,
        user_id: str,
        context_token: str | None,
        *,
        ticket: str | None = None,
    ) -> None:
        if not user_id:
            return
        resolved_ticket = ticket or await self.get_ticket(api, account_key, user_id, context_token)
        if not resolved_ticket:
            return
        try:
            await api.send_typing(user_id, resolved_ticket, TYPING_STATUS_CANCEL)
        except Exception as exc:
            logger.debug("Wechat sendTyping(cancel) failed: {}", exc)
