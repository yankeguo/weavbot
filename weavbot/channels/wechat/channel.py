"""Wechat channel implementation (HTTP POST + long poll)."""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path
from typing import Any

from loguru import logger

from weavbot.bus.events import OutboundMessage
from weavbot.bus.queue import MessageBus
from weavbot.channels.base import BaseChannel
from weavbot.channels.store import ChannelStore, ChannelTarget
from weavbot.channels.wechat.accounts import resolve_accounts, resolve_state_dir
from weavbot.channels.wechat.api import WechatApiClient
from weavbot.channels.wechat.media import (
    download_media_file,
    ensure_local_media_path,
    upload_media_file,
)
from weavbot.channels.wechat.polling import run_long_poll
from weavbot.channels.wechat.session_guard import SessionGuard
from weavbot.channels.wechat.types import (
    ITEM_TYPE_FILE,
    ITEM_TYPE_IMAGE,
    ITEM_TYPE_TEXT,
    ITEM_TYPE_VIDEO,
    ITEM_TYPE_VOICE,
    MESSAGE_STATE_FINISH,
    MESSAGE_TYPE_BOT,
    MessageItem,
    ResolvedWechatAccount,
    WechatMessage,
)
from weavbot.channels.wechat.typing_manager import TypingManager
from weavbot.config.schema import WechatConfig
from weavbot.utils.helpers import normalize_session_key


class WechatChannel(BaseChannel):
    """Wechat channel powered by HTTP APIs and getUpdates long-poll."""

    name = "wechat"

    def __init__(
        self,
        config: WechatConfig,
        bus: MessageBus,
        workspace: Path,
        channel_store: ChannelStore | None = None,
    ):
        super().__init__(config, bus, workspace, channel_store=channel_store)
        self.config: WechatConfig = config
        self._state_dir = resolve_state_dir(workspace, config.state_dir)
        self._accounts: dict[str, ResolvedWechatAccount] = {}
        self._apis: dict[str, WechatApiClient] = {}
        self._poll_tasks: list[asyncio.Task[None]] = []
        self._stop_event = asyncio.Event()
        self._guard = SessionGuard(config.session_pause_minutes)
        self._typing = TypingManager(ttl_sec=max(30, config.typing_keepalive_sec * 2))
        self._context_tokens: dict[str, str] = {}  # "{account}:{user}" -> context_token

    async def start(self) -> None:
        self._running = True
        self._stop_event = asyncio.Event()
        resolved = resolve_accounts(self.config)
        if not resolved:
            logger.error("Wechat enabled but no valid account/token configured")
            self._running = False
            return
        self._accounts = {a.key: a for a in resolved}
        self._apis = {
            a.key: WechatApiClient(
                base_url=a.base_url,
                token=a.token,
                request_timeout_sec=self.config.request_timeout_sec,
                long_poll_timeout_ms=self.config.long_poll_timeout_ms,
                route_tag=a.route_tag,
            )
            for a in resolved
        }
        self._poll_tasks = [
            asyncio.create_task(
                run_long_poll(
                    account=account,
                    api=self._apis[account.key],
                    state_dir=self._state_dir,
                    guard=self._guard,
                    poll_retry_delay_ms=self.config.poll_retry_delay_ms,
                    max_consecutive_failures=self.config.max_consecutive_failures,
                    on_message=self._handle_inbound,
                    stop_event=self._stop_event,
                )
            )
            for account in resolved
        ]
        logger.info("Wechat channel started with {} account(s)", len(self._poll_tasks))
        try:
            await asyncio.gather(*self._poll_tasks)
        finally:
            self._running = False

    async def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        for task in self._poll_tasks:
            task.cancel()
        for task in self._poll_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Wechat poll task shutdown error")
        self._poll_tasks.clear()

    async def send(self, msg: OutboundMessage, target: ChannelTarget) -> None:
        metadata, wechat_meta = self._extract_send_metadata(target.metadata or {})
        requested_account_key = (
            str(wechat_meta.get("account_key", "")).strip()
            or str(metadata.get("account_key", "")).strip()
            or "default"
        )
        account_key = self._resolve_outbound_account_key(requested_account_key, target.chat_id)
        account = self._accounts.get(account_key)
        api = self._apis.get(account_key)
        if not account or not api:
            logger.warning(
                "Wechat outbound dropped, unknown account_key={} requested={} chat_id={}",
                account_key,
                requested_account_key,
                target.chat_id,
            )
            return
        if self._guard.is_paused(account_key):
            logger.warning("Wechat outbound skipped, account paused: {}", account_key)
            return

        chat_id = target.chat_id
        # Reply token is scoped by account+peer and can be supplied explicitly by callers.
        context_token = (
            str(wechat_meta.get("context_token", "")).strip()
            or str(metadata.get("context_token", "")).strip()
            or self._context_tokens.get(f"{account_key}:{chat_id}", "")
        )
        typing_ticket = await self._typing.send_typing(
            api, account_key, chat_id, context_token or None
        )

        try:
            if msg.media:
                for media_ref in msg.media:
                    path = ensure_local_media_path(self.workspace, media_ref)
                    if not path.is_file():
                        logger.warning("Wechat media file not found: {}", path)
                        continue
                    _media_type, media_item = await upload_media_file(
                        api, account.cdn_base_url, path, chat_id
                    )
                    await api.send_message(
                        self._build_bot_message(
                            to_user_id=chat_id,
                            context_token=context_token or None,
                            item_list=[media_item],
                        )
                    )

            text = (msg.content or "").strip()
            if text:
                text_item = {"type": ITEM_TYPE_TEXT, "text_item": {"text": text}}
                await api.send_message(
                    self._build_bot_message(
                        to_user_id=chat_id,
                        context_token=context_token or None,
                        item_list=[text_item],
                    )
                )
        finally:
            await self._typing.cancel_typing(
                api,
                account_key,
                chat_id,
                context_token or None,
                ticket=typing_ticket,
            )

    @staticmethod
    def _extract_send_metadata(
        metadata_raw: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        metadata = metadata_raw if isinstance(metadata_raw, dict) else {}
        wechat_meta = metadata.get("wechat", {}) if isinstance(metadata.get("wechat"), dict) else {}
        return metadata, wechat_meta

    def _resolve_outbound_account_key(self, requested: str, chat_id: str) -> str:
        """Resolve outbound account key with safe fallbacks.

        Priority:
        1) Explicit requested key if exists.
        2) Most recent inbound context token mapping by chat_id.
        3) Single-account fallback when only one account is active.
        4) Keep requested key (will be logged by caller).
        """
        if requested in self._accounts:
            return requested

        if chat_id:
            for key in self._accounts:
                if f"{key}:{chat_id}" in self._context_tokens:
                    return key

        if len(self._accounts) == 1:
            return next(iter(self._accounts.keys()))

        return requested

    @staticmethod
    def _build_bot_message(
        *, to_user_id: str, context_token: str | None, item_list: list[MessageItem]
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": f"weavbot-{secrets.token_hex(8)}",
            "message_type": MESSAGE_TYPE_BOT,
            "message_state": MESSAGE_STATE_FINISH,
            "item_list": item_list,
        }
        if context_token:
            payload["context_token"] = context_token
        return payload

    async def _handle_inbound(self, account: ResolvedWechatAccount, msg: WechatMessage) -> None:
        sender_id = str(msg.get("from_user_id", "")).strip()
        if not sender_id:
            return
        if account.allow_from and sender_id not in account.allow_from:
            return

        context_token = str(msg.get("context_token", "")).strip()
        if context_token:
            self._context_tokens[f"{account.key}:{sender_id}"] = context_token

        content, media = await self._extract_inbound_content(account, msg)
        if not content and not media:
            content = "[wechat:empty]"

        metadata = {
            "account_key": account.key,
            "account_id": account.account_id,
            "message_id": msg.get("message_id"),
            "context_token": context_token,
            "wechat": {
                "account_key": account.key,
                "account_id": account.account_id,
                "context_token": context_token,
                "session_id": msg.get("session_id"),
                "message_type": msg.get("message_type"),
                "message_state": msg.get("message_state"),
            },
        }
        await self._handle_message(
            sender_id=sender_id,
            chat_id=sender_id,
            content=content,
            media=media,
            metadata=metadata,
            # Include account key in session namespace for multi-account isolation.
            session_key=normalize_session_key(f"wechat:{account.key}:{sender_id}"),
        )

    async def _extract_inbound_content(
        self, account: ResolvedWechatAccount, msg: WechatMessage
    ) -> tuple[str, list[str]]:
        parts: list[str] = []
        media_paths: list[str] = []
        item_list = msg.get("item_list")
        if not isinstance(item_list, list):
            return "", []

        for idx, item in enumerate(item_list):
            if not isinstance(item, dict):
                continue
            item_type = int(item.get("type", 0) or 0)
            if item_type == ITEM_TYPE_TEXT:
                text_item = item.get("text_item")
                if isinstance(text_item, dict):
                    text = str(text_item.get("text", "")).strip()
                    if text:
                        parts.append(text)
                continue

            media_node, marker = self._resolve_media_node(item, item_type)

            if not media_node:
                parts.append(f"[wechat:{marker}]")
                continue

            media_ref = media_node.get("media") if isinstance(media_node.get("media"), dict) else {}
            encrypt_param = str(media_ref.get("encrypt_query_param", "")).strip()
            aes_key = str(media_ref.get("aes_key", "")).strip() or None
            if not encrypt_param:
                parts.append(f"[wechat:{marker}]")
                continue

            suffix = ".bin"
            if marker == "image":
                suffix = ".jpg"
            elif marker == "video":
                suffix = ".mp4"
            out = (
                self.media_dir / f"wechat_{account.key}_{msg.get('message_id', 'm')}_{idx}{suffix}"
            )
            try:
                path = await download_media_file(account.cdn_base_url, encrypt_param, aes_key, out)
                media_paths.append(str(path))
                parts.append(f"[wechat:{marker}]")
            except Exception as exc:
                logger.warning("Wechat inbound media download failed: {}", exc)
                parts.append(f"[wechat:{marker}:download_failed]")

        return "\n".join(parts), media_paths

    @staticmethod
    def _resolve_media_node(item: MessageItem, item_type: int) -> tuple[dict[str, Any] | None, str]:
        if item_type == ITEM_TYPE_IMAGE:
            node = item.get("image_item") if isinstance(item.get("image_item"), dict) else None
            return node, "image"
        if item_type == ITEM_TYPE_FILE:
            node = item.get("file_item") if isinstance(item.get("file_item"), dict) else None
            return node, "file"
        if item_type == ITEM_TYPE_VIDEO:
            node = item.get("video_item") if isinstance(item.get("video_item"), dict) else None
            return node, "video"
        if item_type == ITEM_TYPE_VOICE:
            node = item.get("voice_item") if isinstance(item.get("voice_item"), dict) else None
            return node, "voice"
        return None, "file"
