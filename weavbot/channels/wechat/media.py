"""Wechat CDN media upload/download helpers."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import mimetypes
import secrets
from pathlib import Path
from urllib.parse import quote

import httpx
from loguru import logger

from weavbot.channels.wechat.api import WechatApiClient
from weavbot.channels.wechat.types import (
    ITEM_TYPE_FILE,
    ITEM_TYPE_IMAGE,
    ITEM_TYPE_VIDEO,
    UPLOAD_MEDIA_FILE,
    UPLOAD_MEDIA_IMAGE,
    UPLOAD_MEDIA_VIDEO,
)


def _aes_ecb_encrypt(data: bytes, key: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Wechat media encryption requires `cryptography`") from exc
    pad_len = 16 - (len(data) % 16)
    padded = data + bytes([pad_len]) * pad_len
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    encryptor = cipher.encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def _aes_ecb_decrypt(data: bytes, key: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Wechat media decryption requires `cryptography`") from exc
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    decryptor = cipher.decryptor()
    plain = decryptor.update(data) + decryptor.finalize()
    pad_len = plain[-1]
    if not 0 < pad_len <= 16:
        raise ValueError("invalid PKCS7 padding")
    return plain[:-pad_len]


def _cipher_size(plain_size: int) -> int:
    return ((plain_size + 16) // 16) * 16


def _guess_media_type(path: Path) -> tuple[int, int]:
    mime, _ = mimetypes.guess_type(path.name)
    if (mime or "").startswith("image/"):
        return ITEM_TYPE_IMAGE, UPLOAD_MEDIA_IMAGE
    if (mime or "").startswith("video/"):
        return ITEM_TYPE_VIDEO, UPLOAD_MEDIA_VIDEO
    return ITEM_TYPE_FILE, UPLOAD_MEDIA_FILE


async def upload_media_file(
    api: WechatApiClient, cdn_base_url: str, file_path: Path, to_user_id: str
) -> tuple[int, dict]:
    raw = await asyncio.to_thread(file_path.read_bytes)
    rawsize = len(raw)
    rawmd5 = hashlib.md5(raw).hexdigest()  # noqa: S324 - protocol requirement
    key = secrets.token_bytes(16)
    key_hex = key.hex()
    filekey = secrets.token_hex(16)
    media_item_type, upload_media_type = _guess_media_type(file_path)

    upload_req = {
        "filekey": filekey,
        "media_type": upload_media_type,
        "to_user_id": to_user_id,
        "rawsize": rawsize,
        "rawfilemd5": rawmd5,
        "filesize": _cipher_size(rawsize),
        "no_need_thumb": True,
        "aeskey": key_hex,
    }
    resp = await api.get_upload_url(upload_req)
    upload_param = str(resp.get("upload_param", "")).strip()
    if not upload_param:
        raise RuntimeError("getUploadUrl returned empty upload_param")

    cipher = _aes_ecb_encrypt(raw, key)
    url = (
        f"{cdn_base_url.rstrip('/')}/upload?encrypted_query_param={quote(upload_param, safe='')}"
        f"&filekey={quote(filekey, safe='')}"
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), follow_redirects=True) as client:
        cdn_resp = await client.post(
            url, content=cipher, headers={"Content-Type": "application/octet-stream"}
        )
        if cdn_resp.status_code != 200:
            raise RuntimeError(f"CDN upload failed: {cdn_resp.status_code} {cdn_resp.text}")
        download_param = cdn_resp.headers.get("x-encrypted-param", "")
        if not download_param:
            raise RuntimeError("CDN upload missing x-encrypted-param")

    if media_item_type == ITEM_TYPE_IMAGE:
        item = {
            "type": ITEM_TYPE_IMAGE,
            "image_item": {
                "media": {
                    "encrypt_query_param": download_param,
                    # Keep npm behavior: base64(hex-string), not base64(raw-bytes).
                    "aes_key": base64.b64encode(key_hex.encode("ascii")).decode("ascii"),
                    "encrypt_type": 1,
                },
                "mid_size": len(cipher),
            },
        }
    elif media_item_type == ITEM_TYPE_VIDEO:
        item = {
            "type": ITEM_TYPE_VIDEO,
            "video_item": {
                "media": {
                    "encrypt_query_param": download_param,
                    # Keep npm behavior: base64(hex-string), not base64(raw-bytes).
                    "aes_key": base64.b64encode(key_hex.encode("ascii")).decode("ascii"),
                    "encrypt_type": 1,
                },
                "video_size": len(cipher),
            },
        }
    else:
        item = {
            "type": ITEM_TYPE_FILE,
            "file_item": {
                "media": {
                    "encrypt_query_param": download_param,
                    "aes_key": base64.b64encode(key_hex.encode("ascii")).decode("ascii"),
                    "encrypt_type": 1,
                },
                "file_name": file_path.name,
                "len": str(rawsize),
            },
        }
    return media_item_type, item


def _parse_aes_key(aes_key: str) -> bytes:
    decoded = base64.b64decode(aes_key)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32:
        try:
            return bytes.fromhex(decoded.decode("ascii"))
        except ValueError as exc:
            raise ValueError("invalid base64 hex aes key") from exc
    raise ValueError(f"invalid aes key length: {len(decoded)}")


async def download_media_file(
    cdn_base_url: str,
    encrypt_query_param: str,
    aes_key: str | None,
    output_path: Path,
) -> Path:
    url = (
        f"{cdn_base_url.rstrip('/')}/download?encrypted_query_param="
        f"{quote(encrypt_query_param, safe='')}"
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0), follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.content
    if aes_key:
        key = _parse_aes_key(aes_key)
        try:
            data = _aes_ecb_decrypt(data, key)
        except Exception as exc:
            logger.warning("Wechat media decrypt failed: {}", exc)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(output_path.write_bytes, data)
    return output_path


def ensure_local_media_path(workspace: Path, media_ref: str) -> Path:
    path = Path(media_ref).expanduser()
    if not path.is_absolute():
        path = workspace / path
    return path.resolve()
