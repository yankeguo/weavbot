"""Wechat protocol and runtime helper types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

UPLOAD_MEDIA_IMAGE = 1
UPLOAD_MEDIA_VIDEO = 2
UPLOAD_MEDIA_FILE = 3
UPLOAD_MEDIA_VOICE = 4

MESSAGE_TYPE_USER = 1
MESSAGE_TYPE_BOT = 2

MESSAGE_STATE_NEW = 0
MESSAGE_STATE_GENERATING = 1
MESSAGE_STATE_FINISH = 2

ITEM_TYPE_TEXT = 1
ITEM_TYPE_IMAGE = 2
ITEM_TYPE_VOICE = 3
ITEM_TYPE_FILE = 4
ITEM_TYPE_VIDEO = 5

TYPING_STATUS_TYPING = 1
TYPING_STATUS_CANCEL = 2

SESSION_EXPIRED_ERRCODE = -14

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
DEFAULT_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"


class CdnMedia(TypedDict, total=False):
    encrypt_query_param: str
    aes_key: str
    encrypt_type: int


class MessageItem(TypedDict, total=False):
    type: int
    text_item: dict[str, Any]
    image_item: dict[str, Any]
    voice_item: dict[str, Any]
    file_item: dict[str, Any]
    video_item: dict[str, Any]
    ref_msg: dict[str, Any]


class WechatMessage(TypedDict, total=False):
    seq: int
    message_id: int
    from_user_id: str
    to_user_id: str
    create_time_ms: int
    session_id: str
    group_id: str
    message_type: int
    message_state: int
    item_list: list[MessageItem]
    context_token: str


class GetUpdatesResp(TypedDict, total=False):
    ret: int
    errcode: int
    errmsg: str
    msgs: list[WechatMessage]
    get_updates_buf: str
    longpolling_timeout_ms: int


@dataclass(slots=True)
class ResolvedWechatAccount:
    """Runtime resolved account profile."""

    key: str
    account_id: str
    token: str
    base_url: str
    cdn_base_url: str
    route_tag: str | None
    allow_from: list[str]
    enabled: bool = True
