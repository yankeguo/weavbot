"""Wechat QR-login flow helpers."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from rich.console import Console

from weavbot.channels.wechat.api import WechatApiClient


@dataclass(slots=True)
class LoginResult:
    account_id: str
    token: str
    base_url: str
    user_id: str


def _render_qr_if_possible(console: Console, qr_url: str) -> None:
    """Best-effort terminal QR rendering, fallback to URL."""
    try:
        import qrcode
    except ImportError:
        console.print(f"[cyan]QR URL:[/cyan] {qr_url}")
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(qr_url)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    for row in matrix:
        line = "".join("██" if cell else "  " for cell in row)
        console.print(line)
    console.print(f"[cyan]QR URL:[/cyan] {qr_url}")


async def wechat_qr_login(
    *,
    api: WechatApiClient,
    console: Console,
    timeout_ms: int = 480_000,
    bot_type: str = "3",
) -> LoginResult:
    """Execute qrcode login flow and return credentials."""
    qr = await api.get_bot_qrcode(bot_type=bot_type)
    qr_url = str(qr.get("qrcode_img_content", "")).strip()
    qrcode = str(qr.get("qrcode", "")).strip()
    if not qr_url or not qrcode:
        raise RuntimeError(f"get_bot_qrcode returned invalid payload: {qr}")

    console.print("\n[bold]使用微信扫描二维码完成登录：[/bold]\n")
    _render_qr_if_possible(console, qr_url)
    console.print("\n[dim]等待扫码确认...[/dim]\n")

    loop = asyncio.get_running_loop()
    deadline = loop.time() + (max(1, timeout_ms) / 1000.0)
    while loop.time() < deadline:
        status = await api.get_qrcode_status(qrcode=qrcode)
        state = str(status.get("status", "wait")).strip().lower()
        if state in {"wait", ""}:
            await asyncio.sleep(1.0)
            continue
        if state == "scaned":
            console.print("[dim]已扫码，等待手机确认...[/dim]")
            await asyncio.sleep(1.0)
            continue
        if state == "confirmed":
            token = str(status.get("bot_token", "")).strip()
            account_id = str(status.get("ilink_bot_id", "")).strip()
            base_url = str(status.get("baseurl", "")).strip() or api.base_url
            user_id = str(status.get("ilink_user_id", "")).strip()
            if not token or not account_id:
                raise RuntimeError(f"confirmed without token/account_id: {status}")
            return LoginResult(
                account_id=account_id,
                token=token,
                base_url=base_url.rstrip("/"),
                user_id=user_id,
            )
        if state == "expired":
            raise RuntimeError("二维码已过期，请重新执行登录命令")
        raise RuntimeError(f"未知二维码状态: {state} ({status})")
    raise TimeoutError("扫码登录超时，请重试")


def account_key_from_account_id(account_id: str) -> str:
    safe = account_id.strip().replace("@", "-").replace(".", "-")
    return safe or f"wechat-{uuid.uuid4().hex[:8]}"
