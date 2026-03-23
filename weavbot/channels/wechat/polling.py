"""Long-poll loop for Wechat getUpdates."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from loguru import logger

from weavbot.channels.wechat.accounts import load_sync_buf, save_sync_buf
from weavbot.channels.wechat.api import WechatApiClient
from weavbot.channels.wechat.session_guard import SessionGuard
from weavbot.channels.wechat.types import SESSION_EXPIRED_ERRCODE, ResolvedWechatAccount

OnMessage = Callable[[ResolvedWechatAccount, dict[str, Any]], Awaitable[None]]


async def run_long_poll(
    *,
    account: ResolvedWechatAccount,
    api: WechatApiClient,
    state_dir,
    guard: SessionGuard,
    poll_retry_delay_ms: int,
    max_consecutive_failures: int,
    on_message: OnMessage,
    stop_event: asyncio.Event,
) -> None:
    """Run one account long-poll worker until stop_event is set."""
    cursor = load_sync_buf(state_dir, account.key)
    failures = 0

    while not stop_event.is_set():
        if guard.is_paused(account.key):
            remain = guard.remaining_seconds(account.key)
            logger.warning(
                "Wechat account {} paused by session_guard, remaining={}s",
                account.key,
                remain,
            )
            await asyncio.sleep(min(remain, 5))
            continue
        try:
            resp = await api.get_updates(cursor)
            ret = int(resp.get("ret", 0) or 0)
            errcode = int(resp.get("errcode", 0) or 0)
            if ret != 0 or errcode != 0:
                if errcode == SESSION_EXPIRED_ERRCODE or ret == SESSION_EXPIRED_ERRCODE:
                    guard.pause(account.key)
                    failures = 0
                    continue
                failures += 1
                logger.warning(
                    "Wechat getUpdates failed account={} ret={} errcode={} errmsg={}",
                    account.key,
                    ret,
                    errcode,
                    resp.get("errmsg"),
                )
                if failures >= max_consecutive_failures:
                    failures = 0
                    await asyncio.sleep(max(1, poll_retry_delay_ms * 3) / 1000.0)
                else:
                    await asyncio.sleep(max(1, poll_retry_delay_ms) / 1000.0)
                continue

            failures = 0
            next_cursor = str(resp.get("get_updates_buf", "")).strip()
            if next_cursor:
                cursor = next_cursor
                save_sync_buf(state_dir, account.key, cursor)

            for msg in resp.get("msgs") or []:
                try:
                    await on_message(account, msg)
                except Exception:
                    logger.exception("Wechat on_message failed for account {}", account.key)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failures += 1
            logger.warning("Wechat long-poll error for {}: {}", account.key, exc)
            await asyncio.sleep(max(1, poll_retry_delay_ms) / 1000.0)
