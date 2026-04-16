"""Wechat QR-login flow helpers."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
from loguru import logger
from rich.console import Console

from weavbot.channels.wechat.api import WechatApiClient, _common_headers
from weavbot.channels.wechat.types import DEFAULT_BASE_URL

FIXED_BASE_URL = DEFAULT_BASE_URL
QR_LONG_POLL_TIMEOUT_MS = 35_000
MAX_QR_REFRESH_COUNT = 3
DEFAULT_ILINK_BOT_TYPE = "3"
ACTIVE_LOGIN_TTL_MS = 5 * 60_000

_active_logins: dict[str, dict] = {}


@dataclass(slots=True)
class LoginResult:
    account_id: str
    token: str
    base_url: str
    user_id: str


def _render_qr_if_possible(console: Console, qr_url: str) -> None:
    """Best-effort terminal QR rendering, fallback to URL."""
    try:
        import qrcode as _qrcode  # type: ignore
    except ImportError:
        console.print(f"[cyan]QR URL:[/cyan] {qr_url}")
        return
    qr = _qrcode.QRCode(border=1)
    qr.add_data(qr_url)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    for row in matrix:
        line = "".join("██" if cell else "  " for cell in row)
        console.print(line)
    console.print(f"[cyan]QR URL:[/cyan] {qr_url}")


def _is_login_fresh(login: dict) -> bool:
    return asyncio.get_event_loop().time() * 1000 - login["started_at"] < ACTIVE_LOGIN_TTL_MS


def _purge_expired_logins() -> None:
    now = asyncio.get_event_loop().time() * 1000
    stale = [k for k, v in _active_logins.items() if now - v["started_at"] >= ACTIVE_LOGIN_TTL_MS]
    for k in stale:
        del _active_logins[k]


async def _fetch_qr_code(base_url: str, bot_type: str, route_tag: str | None) -> dict[str, str]:
    headers = _common_headers()
    if route_tag:
        headers["SKRouteTag"] = route_tag
    url = f"{base_url.rstrip('/')}/ilink/bot/get_bot_qrcode?bot_type={quote(bot_type, safe='')}"
    logger.info("Fetching QR code from: {} bot_type={}", base_url, bot_type)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # No client-side timeout per upstream 2.1.4 change.
        resp = await client.get(url, headers=headers, timeout=None)
        resp.raise_for_status()
        data = resp.json()
        return {
            "qrcode": str(data.get("qrcode", "")).strip(),
            "qrcode_img_content": str(data.get("qrcode_img_content", "")).strip(),
        }


async def _poll_qr_status(base_url: str, qrcode: str, route_tag: str | None) -> dict[str, Any]:
    headers = _common_headers()
    if route_tag:
        headers["SKRouteTag"] = route_tag
    url = f"{base_url.rstrip('/')}/ilink/bot/get_qrcode_status?qrcode={quote(qrcode, safe='')}"
    logger.debug("Long-poll QR status from: {} qrcode=***", base_url)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            resp = await client.get(
                url,
                headers=headers,
                timeout=httpx.Timeout(QR_LONG_POLL_TIMEOUT_MS / 1000.0),
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            logger.debug("pollQRStatus: client-side timeout, returning wait")
            return {"status": "wait"}
        except httpx.HTTPError as exc:
            logger.warning("pollQRStatus: network/gateway error, will retry: {}", exc)
            return {"status": "wait"}


async def wechat_qr_login(
    *,
    api: WechatApiClient,
    console: Console,
    timeout_ms: int = 480_000,
    bot_type: str = "3",
) -> LoginResult:
    """Execute qrcode login flow and return credentials.

    Compatible with upstream protocol including IDC redirect and QR refresh.
    """
    session_key = uuid.uuid4().hex
    route_tag = api.route_tag

    _purge_expired_logins()

    # 1. Fetch initial QR code from fixed base URL.
    qr_data = await _fetch_qr_code(FIXED_BASE_URL, bot_type, route_tag)
    qrcode = qr_data["qrcode"]
    qr_url = qr_data["qrcode_img_content"]
    if not qrcode or not qr_url:
        raise RuntimeError(f"get_bot_qrcode returned invalid payload: {qr_data}")

    _active_logins[session_key] = {
        "session_key": session_key,
        "id": uuid.uuid4().hex,
        "qrcode": qrcode,
        "qrcode_url": qr_url,
        "started_at": asyncio.get_event_loop().time() * 1000,
        "current_api_base_url": FIXED_BASE_URL,
    }

    console.print("\n[bold]使用微信扫描二维码完成登录：[/bold]\n")
    _render_qr_if_possible(console, qr_url)
    console.print("\n[dim]等待扫码确认...[/dim]\n")

    # 2. Poll status.
    deadline = asyncio.get_event_loop().time() + (max(1, timeout_ms) / 1000.0)
    scanned_printed = False
    qr_refresh_count = 1
    login = _active_logins[session_key]

    while asyncio.get_event_loop().time() < deadline:
        if not _is_login_fresh(login):
            del _active_logins[session_key]
            raise RuntimeError("二维码已过期，请重新执行登录命令")

        current_base_url = login.get("current_api_base_url") or FIXED_BASE_URL
        status_resp = await _poll_qr_status(current_base_url, login["qrcode"], route_tag)
        status = str(status_resp.get("status", "wait")).strip().lower()
        logger.debug(
            "pollQRStatus: status={} hasBotToken={} hasBotId={}",
            status,
            bool(status_resp.get("bot_token")),
            bool(status_resp.get("ilink_bot_id")),
        )

        if status == "wait":
            await asyncio.sleep(1.0)
            continue

        if status == "scaned":
            if not scanned_printed:
                console.print("[dim]已扫码，等待手机确认...[/dim]")
                scanned_printed = True
            await asyncio.sleep(1.0)
            continue

        if status == "expired":
            qr_refresh_count += 1
            if qr_refresh_count > MAX_QR_REFRESH_COUNT:
                logger.warning(
                    "waitForWeixinLogin: QR expired {} times, giving up", MAX_QR_REFRESH_COUNT
                )
                del _active_logins[session_key]
                raise RuntimeError("登录超时：二维码多次过期，请重新开始登录流程")

            console.print(
                f"\n[dim]二维码已过期，正在刷新...({qr_refresh_count}/{MAX_QR_REFRESH_COUNT})[/dim]\n"
            )
            logger.info(
                "waitForWeixinLogin: QR expired, refreshing ({}/{})",
                qr_refresh_count,
                MAX_QR_REFRESH_COUNT,
            )
            try:
                new_qr = await _fetch_qr_code(FIXED_BASE_URL, bot_type, route_tag)
                login["qrcode"] = new_qr["qrcode"]
                login["qrcode_url"] = new_qr["qrcode_img_content"]
                login["started_at"] = asyncio.get_event_loop().time() * 1000
                scanned_printed = False
                logger.info("waitForWeixinLogin: new QR code obtained")
                console.print("[dim]新二维码已生成，请重新扫描[/dim]\n")
                _render_qr_if_possible(console, login["qrcode_url"])
            except Exception as refresh_err:
                logger.error("waitForWeixinLogin: failed to refresh QR code: {}", refresh_err)
                del _active_logins[session_key]
                raise RuntimeError(f"刷新二维码失败: {refresh_err}") from refresh_err
            continue

        if status == "scaned_but_redirect":
            redirect_host = str(status_resp.get("redirect_host", "")).strip()
            if redirect_host:
                new_base_url = f"https://{redirect_host}"
                login["current_api_base_url"] = new_base_url
                logger.info(
                    "waitForWeixinLogin: IDC redirect, switching polling host to {}", redirect_host
                )
            else:
                logger.warning(
                    "waitForWeixinLogin: received scaned_but_redirect but redirect_host is missing"
                )
            continue

        if status == "confirmed":
            if not status_resp.get("ilink_bot_id"):
                del _active_logins[session_key]
                raise RuntimeError("登录失败：服务器未返回 ilink_bot_id")

            token = str(status_resp.get("bot_token", "")).strip()
            account_id = str(status_resp.get("ilink_bot_id", "")).strip()
            user_id = str(status_resp.get("ilink_user_id", "")).strip()
            del _active_logins[session_key]
            logger.info(
                "Login confirmed! ilink_bot_id={} ilink_user_id={}",
                account_id,
                user_id,
            )
            if not token or not account_id:
                raise RuntimeError(f"confirmed without token/account_id: {status_resp}")
            return LoginResult(
                account_id=account_id,
                token=token,
                base_url=DEFAULT_BASE_URL,
                user_id=user_id,
            )

        # Unknown status
        del _active_logins[session_key]
        raise RuntimeError(f"未知二维码状态: {status} ({status_resp})")

    del _active_logins[session_key]
    raise TimeoutError("扫码登录超时，请重试")


def account_key_from_account_id(account_id: str) -> str:
    safe = account_id.strip().replace("@", "-").replace(".", "-")
    return safe or f"wechat-{uuid.uuid4().hex[:8]}"
