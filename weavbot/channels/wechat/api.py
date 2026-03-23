"""HTTP API client for Wechat openclaw-compatible endpoints."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import random
from typing import Any

import httpx

from weavbot.channels.wechat.types import GetUpdatesResp


def _base_url(url: str) -> str:
    return url.rstrip("/") + "/"


def _random_wechat_uin() -> str:
    return base64.b64encode(str(random.getrandbits(32)).encode("utf-8")).decode("ascii")


def make_headers(token: str, body: str, route_tag: str | None = None) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Content-Length": str(len(body.encode("utf-8"))),
        "X-WECHAT-UIN": _random_wechat_uin(),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if route_tag:
        headers["SKRouteTag"] = route_tag
    return headers


class WechatApiClient:
    """Minimal async API wrapper around Wechat HTTP endpoints."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        request_timeout_sec: int = 15,
        long_poll_timeout_ms: int = 35_000,
        route_tag: str | None = None,
    ):
        self.base_url = _base_url(base_url)
        self.token = token
        self.request_timeout_sec = request_timeout_sec
        self.long_poll_timeout_ms = long_poll_timeout_ms
        self.route_tag = route_tag

    async def _post_json(
        self, endpoint: str, payload: dict[str, Any], timeout_ms: int | None = None
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False)
        headers = make_headers(self.token, body, self.route_tag)
        timeout_s = (timeout_ms / 1000.0) if timeout_ms else float(self.request_timeout_sec)
        timeout = httpx.Timeout(timeout_s)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.post(
                self.base_url + endpoint.lstrip("/"), content=body, headers=headers
            )
            resp.raise_for_status()
            return resp.json()

    async def get_updates(self, get_updates_buf: str) -> GetUpdatesResp:
        payload = {"get_updates_buf": get_updates_buf, "base_info": {"channel_version": "weavbot"}}
        try:
            return await self._post_json(
                "ilink/bot/getupdates", payload, timeout_ms=self.long_poll_timeout_ms
            )
        except httpx.TimeoutException:
            return {"ret": 0, "msgs": [], "get_updates_buf": get_updates_buf}

    async def send_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        payload = {"msg": msg, "base_info": {"channel_version": "weavbot"}}
        return await self._post_json("ilink/bot/sendmessage", payload)

    async def get_upload_url(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = dict(payload)
        body["base_info"] = {"channel_version": "weavbot"}
        return await self._post_json("ilink/bot/getuploadurl", body)

    async def get_config(
        self, ilink_user_id: str, context_token: str | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "ilink_user_id": ilink_user_id,
            "base_info": {"channel_version": "weavbot"},
        }
        if context_token:
            body["context_token"] = context_token
        return await self._post_json("ilink/bot/getconfig", body)

    async def send_typing(
        self, ilink_user_id: str, typing_ticket: str, status: int
    ) -> dict[str, Any]:
        body = {
            "ilink_user_id": ilink_user_id,
            "typing_ticket": typing_ticket,
            "status": status,
            "base_info": {"channel_version": "weavbot"},
        }
        return await self._post_json("ilink/bot/sendtyping", body)

    async def get_bot_qrcode(self, bot_type: str = "3") -> dict[str, Any]:
        headers: dict[str, str] = {}
        if self.route_tag:
            headers["SKRouteTag"] = self.route_tag
        url = self.base_url + f"ilink/bot/get_bot_qrcode?bot_type={bot_type}"
        timeout = httpx.Timeout(float(self.request_timeout_sec))
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def get_qrcode_status(self, qrcode: str, timeout_ms: int = 35_000) -> dict[str, Any]:
        headers = {"iLink-App-ClientVersion": "1"}
        if self.route_tag:
            headers["SKRouteTag"] = self.route_tag
        url = self.base_url + f"ilink/bot/get_qrcode_status?qrcode={qrcode}"
        timeout = httpx.Timeout(timeout_ms / 1000.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            try:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                return resp.json()
            except httpx.TimeoutException:
                return {"status": "wait"}


def default_state_dir() -> str:
    return os.path.expanduser("~/.weavbot/wechat")


async def sleep_ms(ms: int) -> None:
    await asyncio.sleep(max(0, ms) / 1000.0)
