"""Wechat account and cursor persistence helpers."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from weavbot.channels.wechat.types import (
    DEFAULT_BASE_URL,
    DEFAULT_CDN_BASE_URL,
    ResolvedWechatAccount,
)
from weavbot.config.schema import WechatAccountConfig, WechatConfig


def resolve_accounts(config: WechatConfig) -> list[ResolvedWechatAccount]:
    """Resolve root + accounts map into runtime account list."""
    resolved: list[ResolvedWechatAccount] = []
    include = set(config.enabled_accounts or [])

    if config.token:
        if not include or "default" in include:
            resolved.append(
                ResolvedWechatAccount(
                    key="default",
                    account_id=config.account_id or "default",
                    token=config.token,
                    base_url=DEFAULT_BASE_URL,
                    cdn_base_url=DEFAULT_CDN_BASE_URL,
                    route_tag=config.route_tag or None,
                    allow_from=list(config.allow_from or []),
                    enabled=True,
                )
            )

    for key, account in (config.accounts or {}).items():
        if include and key not in include:
            continue
        if not account.enabled or not account.token:
            continue
        resolved.append(
            ResolvedWechatAccount(
                key=key,
                account_id=account.account_id or key,
                token=account.token,
                base_url=DEFAULT_BASE_URL,
                cdn_base_url=DEFAULT_CDN_BASE_URL,
                route_tag=account.route_tag or config.route_tag or None,
                allow_from=list(account.allow_from or config.allow_from or []),
                enabled=True,
            )
        )

    return resolved


def account_sync_buf_path(state_dir: Path, account_key: str) -> Path:
    return state_dir / f"{account_key}.sync.json"


def load_sync_buf(state_dir: Path, account_key: str) -> str:
    path = account_sync_buf_path(state_dir, account_key)
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    value = data.get("get_updates_buf")
    return value if isinstance(value, str) else ""


def save_sync_buf(state_dir: Path, account_key: str, value: str) -> None:
    path = account_sync_buf_path(state_dir, account_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"get_updates_buf": value}
    fd, tmp_path = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False))
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def account_credentials_path(state_dir: Path, account_key: str) -> Path:
    accounts_dir = state_dir / "accounts"
    accounts_dir.mkdir(parents=True, exist_ok=True)
    return accounts_dir / f"{account_key}.json"


def save_account_credentials(
    state_dir: Path,
    account_key: str,
    *,
    account_id: str,
    token: str,
    user_id: str = "",
    base_url: str = "",
) -> None:
    path = account_credentials_path(state_dir, account_key)
    payload: dict[str, Any] = {
        "account_id": account_id,
        "token": token,
    }
    if user_id:
        payload["user_id"] = user_id
    if base_url:
        payload["base_url"] = base_url
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def list_account_credentials(state_dir: Path) -> list[dict[str, str]]:
    root = state_dir / "accounts"
    if not root.exists():
        return []
    out: list[dict[str, str]] = []
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append(
            {
                "key": path.stem,
                "account_id": str(data.get("account_id", "")).strip(),
                "user_id": str(data.get("user_id", "")).strip(),
                "base_url": str(data.get("base_url", "")).strip(),
            }
        )
    return out


def upsert_account_config(
    config: WechatConfig, account_key: str, payload: WechatAccountConfig
) -> None:
    if config.accounts is None:
        config.accounts = {}
    config.accounts[account_key] = payload
