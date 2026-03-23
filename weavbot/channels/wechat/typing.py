"""Typing status helpers for Wechat channel."""

from __future__ import annotations

import time
from dataclasses import dataclass

from loguru import logger

from weavbot.channels.wechat.api import WechatApiClient
from weavbot.channels.wechat.types import TYPING_STATUS_CANCEL, TYPING_STATUS_TYPING


@dataclass(slots=True)
class _TypingCacheEntry:
    ticket: str
    updated_at: float


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
        cached = self._cache.get(key)
        now = time.time()
        if cached and (now - cached.updated_at) < self.ttl_sec:
            return cached.ticket
        try:
            resp = await api.get_config(user_id, context_token=context_token)
        except Exception as exc:
            logger.debug("Wechat getConfig failed for typing: {}", exc)
            return None
        ticket = str(resp.get("typing_ticket", "")).strip()
        if ticket:
            self._cache[key] = _TypingCacheEntry(ticket=ticket, updated_at=now)
        return ticket or None

    async def send_typing(
        self, api: WechatApiClient, account_key: str, user_id: str, context_token: str | None
    ) -> None:
        if not user_id:
            return
        ticket = await self.get_ticket(api, account_key, user_id, context_token)
        if not ticket:
            return
        try:
            await api.send_typing(user_id, ticket, TYPING_STATUS_TYPING)
        except Exception as exc:
            logger.debug("Wechat sendTyping(typing) failed: {}", exc)

    async def cancel_typing(
        self, api: WechatApiClient, account_key: str, user_id: str, context_token: str | None
    ) -> None:
        if not user_id:
            return
        ticket = await self.get_ticket(api, account_key, user_id, context_token)
        if not ticket:
            return
        try:
            await api.send_typing(user_id, ticket, TYPING_STATUS_CANCEL)
        except Exception as exc:
            logger.debug("Wechat sendTyping(cancel) failed: {}", exc)
