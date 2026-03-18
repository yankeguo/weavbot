"""WeCom channel implementation using the long WebSocket connection protocol."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import random
import string
import time
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any

from loguru import logger

from weavbot.bus.events import OutboundMessage
from weavbot.bus.queue import MessageBus
from weavbot.channels.base import BaseChannel
from weavbot.config.schema import WeComConfig

try:
    import websockets
    from websockets.exceptions import ConnectionClosed

    WECOM_AVAILABLE = True
except ImportError:
    WECOM_AVAILABLE = False
    websockets = None  # type: ignore[assignment]
    ConnectionClosed = Exception  # type: ignore[assignment,misc]


CMD_SUBSCRIBE = "aibot_subscribe"
CMD_MSG_CALLBACK = "aibot_msg_callback"
CMD_EVENT_CALLBACK = "aibot_event_callback"
CMD_RESPOND_MSG = "aibot_respond_msg"
CMD_RESPOND_WELCOME = "aibot_respond_welcome_msg"
CMD_RESPOND_UPDATE = "aibot_respond_update_msg"
CMD_SEND_MSG = "aibot_send_msg"
CMD_PING = "ping"
CMD_UPLOAD_INIT = "aibot_upload_media_init"
CMD_UPLOAD_CHUNK = "aibot_upload_media_chunk"
CMD_UPLOAD_FINISH = "aibot_upload_media_finish"

EVENT_ENTER_CHAT = "enter_chat"
EVENT_TEMPLATE_CARD = "template_card_event"
EVENT_FEEDBACK = "feedback_event"
EVENT_DISCONNECTED = "disconnected_event"


class WeComChannel(BaseChannel):
    """WeCom channel using WebSocket long connection."""

    name = "wecom"

    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif"}
    _VOICE_EXTS = {".amr"}
    _VIDEO_EXTS = {".mp4"}

    def __init__(self, config: WeComConfig, bus: MessageBus, workspace: Path):
        super().__init__(config, bus, workspace)
        self.config: WeComConfig = config

        self._ws: Any = None
        self._receiver_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._disconnect_event = asyncio.Event()
        self._stopping = False

        self._pending_acks: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._pending_ack_lock = asyncio.Lock()

        self._missed_pong_count = 0
        self._rate_window_minute: dict[str, deque[float]] = {}
        self._rate_window_hour: dict[str, deque[float]] = {}

        self._stream_ids_by_req_id: OrderedDict[str, str] = OrderedDict()
        self._msgid_to_reqid: OrderedDict[str, str] = OrderedDict()

        media_subdir = Path(self.config.temp_media_dir)
        if media_subdir.is_absolute():
            self._temp_media_dir = media_subdir
        else:
            self._temp_media_dir = self.workspace / media_subdir
        self._temp_media_dir.mkdir(parents=True, exist_ok=True)

    async def start(self) -> None:
        """Start the WeCom channel and keep reconnecting until stopped."""
        if not WECOM_AVAILABLE:
            logger.error("websockets is not installed. Please install dependency first.")
            return
        if not self.config.bot_id or not self.config.secret:
            logger.error("WeCom bot_id and secret are required.")
            return

        self._running = True
        self._stopping = False
        reconnect_attempt = 0

        while self._running:
            try:
                await self._run_connection_once()
                reconnect_attempt = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("WeCom connection cycle ended with error: {}", exc)

            if not self._running:
                break

            reconnect_attempt += 1
            if (
                self.config.max_reconnect_attempts != -1
                and reconnect_attempt > self.config.max_reconnect_attempts
            ):
                logger.error(
                    "WeCom reconnect attempts exceeded max_reconnect_attempts={}",
                    self.config.max_reconnect_attempts,
                )
                break

            delay_ms = min(
                self.config.reconnect_base_ms * (2 ** max(0, reconnect_attempt - 1)),
                self.config.reconnect_max_ms,
            )
            logger.info(
                "Reconnecting WeCom websocket in {}ms (attempt {})",
                delay_ms,
                reconnect_attempt,
            )
            await asyncio.sleep(delay_ms / 1000)

        self._running = False

    async def stop(self) -> None:
        """Stop WeCom channel and close websocket gracefully."""
        self._running = False
        self._stopping = True
        self._disconnect_event.set()
        await self._stop_heartbeat()
        await self._close_ws()
        await self._cancel_receiver()

    async def send(self, msg: OutboundMessage) -> None:
        """Send outbound message through WeCom websocket."""
        if not self._ws:
            logger.warning("WeCom websocket is not connected.")
            return

        metadata = msg.metadata or {}
        wecom_meta = metadata.get("wecom", {}) if isinstance(metadata.get("wecom"), dict) else {}
        req_id = self._extract_req_id(metadata, wecom_meta)
        chat_type = self._infer_chat_type(msg.chat_id, metadata, wecom_meta)

        if not self._within_rate_limit(msg.chat_id):
            logger.warning("WeCom outbound dropped due to rate-limit for chat_id={}", msg.chat_id)
            return

        if msg.media:
            for media_ref in msg.media:
                await self._send_media_message(
                    media_ref=media_ref,
                    req_id=req_id,
                    chat_id=msg.chat_id,
                    chat_type=chat_type,
                    metadata=metadata,
                    wecom_meta=wecom_meta,
                )

        content = (msg.content or "").strip()
        if not content:
            return

        if metadata.get("_progress"):
            await self._send_stream_progress(
                content, req_id=req_id, chat_id=msg.chat_id, chat_type=chat_type
            )
            return

        if req_id and req_id in self._stream_ids_by_req_id:
            await self._send_stream_finish(
                content, req_id=req_id, chat_id=msg.chat_id, chat_type=chat_type
            )
            self._stream_ids_by_req_id.pop(req_id, None)
            return

        cmd_override = str(wecom_meta.get("command", "")).strip()
        body_override = wecom_meta.get("body")
        if cmd_override and body_override is not None:
            await self._send_custom_command(
                cmd=cmd_override,
                req_id=req_id,
                body=body_override,
                chat_id=msg.chat_id,
                chat_type=chat_type,
            )
            return

        if wecom_meta.get("event_type") == EVENT_ENTER_CHAT and req_id:
            body = {"msgtype": "text", "text": {"content": content}}
            await self._send_reply(req_id=req_id, cmd=CMD_RESPOND_WELCOME, body=body)
            return

        if req_id:
            body = {"msgtype": "text", "text": {"content": content}}
            await self._send_reply(req_id=req_id, cmd=CMD_RESPOND_MSG, body=body)
            return

        proactive_body = {
            "chatid": msg.chat_id,
            "chat_type": chat_type,
            "msgtype": "markdown",
            "markdown": {"content": content},
        }
        await self._send_request(cmd=CMD_SEND_MSG, body=proactive_body)

    async def _run_connection_once(self) -> None:
        """Open one websocket session and run until disconnected."""
        self._disconnect_event = asyncio.Event()
        ws_url = self.config.ws_url or "wss://openws.work.weixin.qq.com"
        logger.info("Connecting WeCom websocket: {}", ws_url)
        self._ws = await websockets.connect(ws_url, ping_interval=None, ping_timeout=None)
        self._missed_pong_count = 0

        try:
            await self._subscribe()
            self._receiver_task = asyncio.create_task(self._receiver_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            await self._disconnect_event.wait()
        finally:
            await self._stop_heartbeat()
            await self._cancel_receiver()
            await self._close_ws()
            self._reject_pending_acks("wecom websocket disconnected")

    async def _subscribe(self) -> None:
        """Authenticate via aibot_subscribe."""
        body = {"bot_id": self.config.bot_id, "secret": self.config.secret}
        ack = await self._send_request(cmd=CMD_SUBSCRIBE, body=body)
        if int(ack.get("errcode", -1)) != 0:
            raise RuntimeError(
                f"WeCom subscribe failed: errcode={ack.get('errcode')} errmsg={ack.get('errmsg')}"
            )
        logger.info("WeCom subscribe authenticated")

    async def _heartbeat_loop(self) -> None:
        """Send heartbeat ping frames at fixed intervals."""
        try:
            while self._running and self._ws:
                await asyncio.sleep(max(1, self.config.heartbeat_interval_sec))

                if self._missed_pong_count >= max(1, self.config.max_missed_pong):
                    logger.warning(
                        "WeCom heartbeat lost {} consecutive pong(s), reconnecting",
                        self._missed_pong_count,
                    )
                    self._disconnect_event.set()
                    return

                self._missed_pong_count += 1
                try:
                    await self._send_request(
                        cmd=CMD_PING, body=None, timeout_s=self.config.request_timeout_sec
                    )
                    self._missed_pong_count = 0
                except Exception as exc:
                    logger.warning("WeCom heartbeat ping failed: {}", exc)
        except asyncio.CancelledError:
            return

    async def _receiver_loop(self) -> None:
        """Receive websocket frames and dispatch them."""
        try:
            async for raw in self._ws:
                frame = self._decode_frame(raw)
                if not frame:
                    continue
                await self._handle_frame(frame)
        except asyncio.CancelledError:
            return
        except ConnectionClosed as exc:
            logger.warning("WeCom websocket closed: {}", exc)
        except Exception as exc:
            logger.warning("WeCom receiver loop error: {}", exc)
        finally:
            self._disconnect_event.set()

    async def _handle_frame(self, frame: dict[str, Any]) -> None:
        """Handle callback frames and ack frames."""
        cmd = frame.get("cmd")
        if cmd == CMD_MSG_CALLBACK:
            await self._handle_message_callback(frame)
            return
        if cmd == CMD_EVENT_CALLBACK:
            await self._handle_event_callback(frame)
            return

        req_id = self._get_req_id(frame)
        if req_id:
            future = self._pending_acks.pop(req_id, None)
            if future and not future.done():
                future.set_result(frame)
                return
            if req_id.startswith(f"{CMD_PING}_"):
                self._missed_pong_count = 0
                return

        logger.debug("Ignored WeCom frame without routing target: {}", frame)

    async def _handle_message_callback(self, frame: dict[str, Any]) -> None:
        """Map aibot_msg_callback to InboundMessage."""
        body = frame.get("body", {})
        req_id = self._get_req_id(frame)
        msg_id = str(body.get("msgid", "")).strip()
        if req_id and msg_id:
            self._remember_msgid_reqid(msg_id, req_id)

        from_info = body.get("from", {}) if isinstance(body.get("from"), dict) else {}
        sender_id = str(from_info.get("userid", "")).strip()
        chat_type = str(body.get("chattype", "single")).strip() or "single"
        group_chat_id = str(body.get("chatid", "")).strip()
        chat_id = group_chat_id if chat_type == "group" and group_chat_id else sender_id
        msg_type = str(body.get("msgtype", "")).strip()

        content, media = self._parse_inbound_message_body(body, msg_type)
        if not content and not media:
            content = f"[wecom:{msg_type}]"

        session_key = (
            f"wecom:{group_chat_id}"
            if chat_type == "group" and group_chat_id
            else f"wecom:{sender_id}"
        )
        metadata = {
            "message_id": msg_id,
            "req_id": req_id,
            "msg_id": msg_id,
            "chat_type": chat_type,
            "msg_type": msg_type,
            "wecom": {
                "req_id": req_id,
                "msg_id": msg_id,
                "chat_type": chat_type,
                "chat_id": group_chat_id,
                "sender_id": sender_id,
                "msg_type": msg_type,
                "raw_body": body,
            },
        }

        await self._handle_message(
            sender_id=sender_id or "unknown",
            chat_id=chat_id or sender_id or "unknown",
            content=content,
            media=media,
            metadata=metadata,
            session_key=session_key,
        )

    async def _handle_event_callback(self, frame: dict[str, Any]) -> None:
        """Map aibot_event_callback to InboundMessage."""
        body = frame.get("body", {})
        req_id = self._get_req_id(frame)
        msg_id = str(body.get("msgid", "")).strip()
        if req_id and msg_id:
            self._remember_msgid_reqid(msg_id, req_id)

        from_info = body.get("from", {}) if isinstance(body.get("from"), dict) else {}
        sender_id = str(from_info.get("userid", "")).strip()
        chat_type = str(body.get("chattype", "single")).strip() or "single"
        group_chat_id = str(body.get("chatid", "")).strip()
        chat_id = group_chat_id if chat_type == "group" and group_chat_id else sender_id
        event = body.get("event", {}) if isinstance(body.get("event"), dict) else {}
        event_type = str(event.get("eventtype", "")).strip()

        if event_type == EVENT_DISCONNECTED and self.config.single_instance_guard:
            logger.warning("Received disconnected_event from WeCom, reconnecting")
            self._disconnect_event.set()
            return

        session_key = (
            f"wecom:{group_chat_id}"
            if chat_type == "group" and group_chat_id
            else f"wecom:{sender_id}"
        )
        content = f"[wecom:event:{event_type}]"
        metadata = {
            "message_id": msg_id,
            "req_id": req_id,
            "msg_id": msg_id,
            "chat_type": chat_type,
            "msg_type": "event",
            "wecom": {
                "req_id": req_id,
                "msg_id": msg_id,
                "chat_type": chat_type,
                "chat_id": group_chat_id,
                "sender_id": sender_id,
                "event_type": event_type,
                "raw_body": body,
            },
        }

        await self._handle_message(
            sender_id=sender_id or "unknown",
            chat_id=chat_id or sender_id or "unknown",
            content=content,
            metadata=metadata,
            session_key=session_key,
        )

    def _parse_inbound_message_body(
        self, body: dict[str, Any], msg_type: str
    ) -> tuple[str, list[str]]:
        """Extract text representation and media list from inbound message body."""
        media: list[str] = []

        if msg_type == "text":
            text = body.get("text", {}) if isinstance(body.get("text"), dict) else {}
            return str(text.get("content", "")).strip(), media

        if msg_type == "voice":
            voice = body.get("voice", {}) if isinstance(body.get("voice"), dict) else {}
            content = str(voice.get("content", "") or voice.get("recognize", "")).strip()
            return (content or "[voice]"), media

        if msg_type == "mixed":
            mixed = body.get("mixed", {}) if isinstance(body.get("mixed"), dict) else {}
            items = mixed.get("msg_item", []) if isinstance(mixed.get("msg_item"), list) else []
            parts: list[str] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("msgtype", "")).strip()
                if item_type == "text":
                    text = item.get("text", {}) if isinstance(item.get("text"), dict) else {}
                    parts.append(str(text.get("content", "")).strip())
                elif item_type == "image":
                    image = item.get("image", {}) if isinstance(item.get("image"), dict) else {}
                    url = str(image.get("url", "")).strip()
                    aeskey = str(image.get("aeskey", "")).strip()
                    if url:
                        parts.append(f"[image:{url}]")
                        media.append(url)
                        if aeskey:
                            parts.append(f"[image_aeskey:{aeskey[:8]}...]")
            return "\n".join(p for p in parts if p), media

        if msg_type in {"image", "file", "video"}:
            data = body.get(msg_type, {}) if isinstance(body.get(msg_type), dict) else {}
            url = str(data.get("url", "")).strip()
            aeskey = str(data.get("aeskey", "")).strip()
            if url:
                media.append(url)
            marker = f"[{msg_type}]"
            if url:
                marker = f"[{msg_type}:{url}]"
            if aeskey:
                marker += f" [aeskey:{aeskey[:8]}...]"
            return marker, media

        return f"[wecom:{msg_type}]", media

    async def _send_stream_progress(
        self, content: str, req_id: str | None, chat_id: str, chat_type: int
    ) -> None:
        """Send streaming progress; use aibot_send_msg when callback req_id is unavailable."""
        if req_id:
            stream_id = self._stream_ids_by_req_id.get(req_id)
            if not stream_id:
                stream_id = self._new_stream_id()
                self._remember_stream_id(req_id, stream_id)
            body = {
                "msgtype": "stream",
                "stream": {"id": stream_id, "finish": False, "content": content},
            }
            await self._send_reply(req_id=req_id, cmd=CMD_RESPOND_MSG, body=body)
            return

        proactive_body = {
            "chatid": chat_id,
            "chat_type": chat_type,
            "msgtype": "markdown",
            "markdown": {"content": content},
        }
        await self._send_request(cmd=CMD_SEND_MSG, body=proactive_body)

    async def _send_stream_finish(
        self, content: str, req_id: str, chat_id: str, chat_type: int
    ) -> None:
        """Finish existing stream for a req_id."""
        stream_id = self._stream_ids_by_req_id.get(req_id)
        if not stream_id:
            await self._send_stream_progress(
                content, req_id=req_id, chat_id=chat_id, chat_type=chat_type
            )
            return
        body = {
            "msgtype": "stream",
            "stream": {"id": stream_id, "finish": True, "content": content},
        }
        await self._send_reply(req_id=req_id, cmd=CMD_RESPOND_MSG, body=body)

    async def _send_media_message(
        self,
        media_ref: str,
        req_id: str | None,
        chat_id: str,
        chat_type: int,
        metadata: dict[str, Any],
        wecom_meta: dict[str, Any],
    ) -> None:
        """Upload local media and send the message."""
        media_path = self.resolve_media_path(media_ref)
        if not media_path.is_file():
            logger.warning("WeCom media path not found: {}", media_path)
            return

        msg_type = self._guess_media_type(media_path)
        media_id = await self._upload_media_file(media_path=media_path, msg_type=msg_type)
        if not media_id:
            return

        body: dict[str, Any] = {"msgtype": msg_type, msg_type: {"media_id": media_id}}
        if msg_type == "video":
            body[msg_type]["title"] = media_path.stem
            body[msg_type]["description"] = media_path.name

        cmd_override = str(wecom_meta.get("command", "")).strip()
        if cmd_override in {CMD_RESPOND_WELCOME, CMD_RESPOND_UPDATE, CMD_RESPOND_MSG} and req_id:
            await self._send_reply(req_id=req_id, cmd=cmd_override, body=body)
            return

        if req_id:
            await self._send_reply(req_id=req_id, cmd=CMD_RESPOND_MSG, body=body)
            return

        proactive_body = {"chatid": chat_id, "chat_type": chat_type, **body}
        await self._send_request(cmd=CMD_SEND_MSG, body=proactive_body)

    async def _send_custom_command(
        self,
        cmd: str,
        req_id: str | None,
        body: Any,
        chat_id: str,
        chat_type: int,
    ) -> None:
        """Send explicit command from metadata."""
        if cmd in {CMD_RESPOND_MSG, CMD_RESPOND_WELCOME, CMD_RESPOND_UPDATE}:
            if not req_id:
                logger.warning(
                    "WeCom custom command {} requires callback req_id, fallback to send_msg", cmd
                )
                if isinstance(body, dict):
                    proactive_body = {"chatid": chat_id, "chat_type": chat_type, **body}
                    await self._send_request(cmd=CMD_SEND_MSG, body=proactive_body)
                return
            await self._send_reply(req_id=req_id, cmd=cmd, body=body)
            return

        if cmd == CMD_SEND_MSG:
            if isinstance(body, dict):
                payload = {"chatid": chat_id, "chat_type": chat_type, **body}
                await self._send_request(cmd=CMD_SEND_MSG, body=payload)
            return

        # Unknown command: try as generic request with generated req_id.
        if isinstance(body, dict):
            await self._send_request(cmd=cmd, body=body)

    async def _send_reply(self, req_id: str, cmd: str, body: dict[str, Any]) -> dict[str, Any]:
        """Send reply-style command with callback req_id."""
        frame = {"cmd": cmd, "headers": {"req_id": req_id}, "body": body}
        return await self._send_frame_wait_ack(
            frame=frame, timeout_s=self.config.request_timeout_sec
        )

    async def _send_request(
        self, cmd: str, body: dict[str, Any] | None, timeout_s: int | None = None
    ) -> dict[str, Any]:
        """Send command with generated req_id and wait for ack."""
        req_id = self._new_req_id(prefix=cmd)
        frame: dict[str, Any] = {"cmd": cmd, "headers": {"req_id": req_id}}
        if body is not None:
            frame["body"] = body
        return await self._send_frame_wait_ack(
            frame=frame, timeout_s=timeout_s or self.config.request_timeout_sec
        )

    async def _send_frame_wait_ack(self, frame: dict[str, Any], timeout_s: int) -> dict[str, Any]:
        """Low-level send + ack await."""
        req_id = self._get_req_id(frame)
        if not req_id:
            raise RuntimeError("frame.headers.req_id is required")
        if not self._ws:
            raise RuntimeError("wecom websocket is not connected")

        async with self._pending_ack_lock:
            if req_id in self._pending_acks:
                raise RuntimeError(f"duplicate pending req_id: {req_id}")
            future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
            self._pending_acks[req_id] = future

        try:
            payload = json.dumps(frame, ensure_ascii=False)
            await self._ws.send(payload)
            ack = await asyncio.wait_for(future, timeout=float(timeout_s))
            errcode = int(ack.get("errcode", -1))
            if errcode != 0:
                raise RuntimeError(f"wecom ack error errcode={errcode} errmsg={ack.get('errmsg')}")
            return ack
        finally:
            self._pending_acks.pop(req_id, None)

    async def _upload_media_file(self, media_path: Path, msg_type: str) -> str | None:
        """Upload a local media file via init/chunk/finish commands."""
        file_type = "file"
        if msg_type == "image":
            file_type = "image"
        elif msg_type == "voice":
            file_type = "voice"
        elif msg_type == "video":
            file_type = "video"

        data = await asyncio.to_thread(media_path.read_bytes)
        if not data:
            logger.warning("WeCom upload skipped empty file: {}", media_path)
            return None

        chunk_size = min(max(1, self.config.upload_chunk_size), 512 * 1024)
        total_chunks = (len(data) + chunk_size - 1) // chunk_size
        if total_chunks > 100:
            logger.error("WeCom upload failed: too many chunks (>100) for {}", media_path)
            return None

        file_md5 = hashlib.md5(data).hexdigest()
        init_body = {
            "type": file_type,
            "filename": media_path.name,
            "total_size": len(data),
            "total_chunks": total_chunks,
            "md5": file_md5,
        }
        init_ack = await self._send_request(cmd=CMD_UPLOAD_INIT, body=init_body)
        upload_id = str((init_ack.get("body") or {}).get("upload_id", "")).strip()
        if not upload_id:
            logger.error("WeCom upload init returned empty upload_id")
            return None

        for index, start in enumerate(range(0, len(data), chunk_size)):
            chunk = data[start : start + chunk_size]
            chunk_body = {
                "upload_id": upload_id,
                "chunk_index": index,
                "base64_data": base64.b64encode(chunk).decode("ascii"),
            }
            await self._send_request(cmd=CMD_UPLOAD_CHUNK, body=chunk_body)

        finish_ack = await self._send_request(cmd=CMD_UPLOAD_FINISH, body={"upload_id": upload_id})
        media_id = str((finish_ack.get("body") or {}).get("media_id", "")).strip()
        if not media_id:
            logger.error("WeCom upload finish returned empty media_id")
            return None
        return media_id

    async def download_media_resource(
        self, url: str, aeskey: str, filename: str | None = None
    ) -> Path:
        """Download encrypted media and decrypt with AES-256-CBC (requires cryptography)."""
        import httpx

        async with httpx.AsyncClient(timeout=self.config.request_timeout_sec) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            encrypted_data = resp.content

        decrypted = self.decrypt_media_data(encrypted_data, aeskey)
        target_path = self._build_safe_media_path(filename)
        await asyncio.to_thread(target_path.write_bytes, decrypted)
        return target_path

    def _build_safe_media_path(self, filename: str | None) -> Path:
        """Build a safe output path constrained under the temp media directory."""
        if filename:
            target_name = Path(filename).name
            if not target_name:
                target_name = f"wecom_media_{int(time.time())}"
        else:
            target_name = f"wecom_media_{int(time.time())}"

        base_dir = self._temp_media_dir.resolve()
        target_path = (base_dir / target_name).resolve()
        try:
            target_path.relative_to(base_dir)
        except ValueError as exc:
            raise ValueError(f"unsafe filename outside media dir: {filename}") from exc
        return target_path

    @staticmethod
    def decrypt_media_data(encrypted_data: bytes, aeskey: str) -> bytes:
        """Decrypt media content with AES-256-CBC + PKCS#7 padding."""
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        except ImportError as exc:
            raise RuntimeError(
                "decrypt_media_data requires optional dependency 'cryptography'"
            ) from exc

        if not encrypted_data:
            raise ValueError("encrypted_data is empty")
        if not aeskey:
            raise ValueError("aeskey is empty")

        padded = aeskey + "=" * ((4 - len(aeskey) % 4) % 4)
        try:
            key = base64.b64decode(padded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("aeskey is not valid base64") from exc
        if len(key) != 32:
            raise ValueError(f"invalid aeskey length: expected 32 bytes, got {len(key)}")
        iv = key[:16]

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(encrypted_data) + decryptor.finalize()
        if not decrypted:
            raise ValueError("decrypted payload is empty")

        pad = decrypted[-1]
        if pad < 1 or pad > 32 or pad > len(decrypted):
            raise ValueError(f"invalid PKCS#7 padding length: {pad}")
        if any(x != pad for x in decrypted[-pad:]):
            raise ValueError("invalid PKCS#7 padding")
        return decrypted[:-pad]

    async def _stop_heartbeat(self) -> None:
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        self._heartbeat_task = None

    async def _cancel_receiver(self) -> None:
        if self._receiver_task and not self._receiver_task.done():
            self._receiver_task.cancel()
            try:
                await self._receiver_task
            except asyncio.CancelledError:
                pass
        self._receiver_task = None

    async def _close_ws(self) -> None:
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None

    def _reject_pending_acks(self, reason: str) -> None:
        for req_id, fut in list(self._pending_acks.items()):
            if not fut.done():
                fut.set_exception(RuntimeError(reason))
            self._pending_acks.pop(req_id, None)

    def _extract_req_id(self, metadata: dict[str, Any], wecom_meta: dict[str, Any]) -> str | None:
        req_id = (
            str(wecom_meta.get("req_id", "")).strip() or str(metadata.get("req_id", "")).strip()
        )
        if req_id:
            return req_id
        message_id = str(metadata.get("message_id", "")).strip()
        if message_id:
            return self._msgid_to_reqid.get(message_id)
        return None

    def _infer_chat_type(
        self, chat_id: str, metadata: dict[str, Any], wecom_meta: dict[str, Any]
    ) -> int:
        chat_type_raw = wecom_meta.get("chat_type") or metadata.get("chat_type")
        if isinstance(chat_type_raw, int):
            return 2 if chat_type_raw == 2 else 1
        if isinstance(chat_type_raw, str):
            val = chat_type_raw.strip().lower()
            if val in {"2", "group"}:
                return 2
        if "group" in (chat_id or "").lower():
            return 2
        return 1

    def _within_rate_limit(self, chat_id: str) -> bool:
        now = time.time()
        per_min = max(1, self.config.per_chat_per_minute)
        per_hour = max(1, self.config.per_chat_per_hour)

        minute_q = self._rate_window_minute.setdefault(chat_id, deque())
        while minute_q and now - minute_q[0] > 60:
            minute_q.popleft()
        if len(minute_q) >= per_min:
            return False

        hour_q = self._rate_window_hour.setdefault(chat_id, deque())
        while hour_q and now - hour_q[0] > 3600:
            hour_q.popleft()
        if len(hour_q) >= per_hour:
            return False

        minute_q.append(now)
        hour_q.append(now)
        return True

    @staticmethod
    def _decode_frame(raw: Any) -> dict[str, Any] | None:
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8")
            except UnicodeDecodeError:
                return None
        if not isinstance(raw, str):
            return None
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(decoded, dict):
            return decoded
        return None

    @staticmethod
    def _get_req_id(frame: dict[str, Any]) -> str:
        headers = frame.get("headers", {})
        if not isinstance(headers, dict):
            return ""
        req_id = headers.get("req_id", "")
        return str(req_id).strip()

    @staticmethod
    def _new_req_id(prefix: str) -> str:
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return f"{prefix}_{int(time.time() * 1000)}_{suffix}"

    def _new_stream_id(self) -> str:
        return f"stream_{int(time.time() * 1000)}_{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}"

    def _remember_stream_id(self, req_id: str, stream_id: str) -> None:
        self._stream_ids_by_req_id[req_id] = stream_id
        while len(self._stream_ids_by_req_id) > 1024:
            self._stream_ids_by_req_id.popitem(last=False)

    def _remember_msgid_reqid(self, msg_id: str, req_id: str) -> None:
        self._msgid_to_reqid[msg_id] = req_id
        while len(self._msgid_to_reqid) > 2048:
            self._msgid_to_reqid.popitem(last=False)

    def _guess_media_type(self, media_path: Path) -> str:
        ext = media_path.suffix.lower()
        if ext in self._IMAGE_EXTS:
            return "image"
        if ext in self._VOICE_EXTS:
            return "voice"
        if ext in self._VIDEO_EXTS:
            return "video"
        return "file"
