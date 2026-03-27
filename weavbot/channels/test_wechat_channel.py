import asyncio
from pathlib import Path

from weavbot.bus.events import OutboundMessage
from weavbot.bus.queue import MessageBus
from weavbot.channels.store import ChannelEndpoint, ChannelStore
from weavbot.channels.wechat.accounts import resolve_accounts
from weavbot.channels.wechat.channel import WechatChannel
from weavbot.channels.wechat.session_guard import SessionGuard
from weavbot.channels.wechat.types import (
    ITEM_TYPE_IMAGE,
    ITEM_TYPE_TEXT,
    ITEM_TYPE_VOICE,
    ResolvedWechatAccount,
)
from weavbot.config.schema import WechatAccountConfig, WechatConfig


def test_resolve_accounts_with_default_and_sub_accounts():
    cfg = WechatConfig(
        token="token-default",
        account_id="default@im.bot",
        enabled_accounts=["acc-a"],
        accounts={
            "acc-a": WechatAccountConfig(token="token-a", account_id="a@im.bot"),
            "acc-b": WechatAccountConfig(token="token-b", account_id="b@im.bot"),
        },
    )
    out = resolve_accounts(cfg)
    assert len(out) == 1
    assert out[0].key == "acc-a"
    assert out[0].account_id == "a@im.bot"


def test_session_guard_pause_and_expire():
    guard = SessionGuard(pause_minutes=1)
    guard.pause("k1")
    assert guard.is_paused("k1") is True
    assert guard.remaining_seconds("k1") > 0
    guard._paused_until["k1"] = 0
    assert guard.is_paused("k1") is False


def test_handle_inbound_sets_account_scoped_session_key(tmp_path: Path):
    bus = MessageBus()
    store = ChannelStore(tmp_path / "channels")
    cfg = WechatConfig(enabled=True, token="t", account_id="acc@im.bot")
    ch = WechatChannel(cfg, bus, tmp_path, channel_store=store)
    account = ResolvedWechatAccount(
        key="acc-key",
        account_id="acc@im.bot",
        token="t",
        base_url="https://ilinkai.weixin.qq.com",
        cdn_base_url="https://novac2c.cdn.weixin.qq.com/c2c",
        route_tag=None,
        allow_from=[],
    )

    async def run_case():
        await ch._handle_inbound(
            account,
            {
                "from_user_id": "u1@im.wechat",
                "message_id": 1,
                "context_token": "ctx-1",
                "item_list": [{"type": ITEM_TYPE_TEXT, "text_item": {"text": "hello"}}],
            },
        )
        inbound = await bus.consume_inbound()
        ep = await store.resolve(inbound.session_key)
        return inbound, ep

    inbound, ep = asyncio.run(run_case())
    assert inbound.channel == "wechat"
    assert inbound.chat_id == "u1@im.wechat"
    assert inbound.session_key == "wechat_acc-key_u1@im.wechat"
    assert inbound.metadata["message_id"] == 1
    assert ep is not None
    assert ep.metadata["wechat"]["context_token"] == "ctx-1"


def test_send_text_routes_to_selected_account(tmp_path: Path):
    class _FakeApi:
        def __init__(self):
            self.sent = []

        async def send_message(self, msg):
            self.sent.append(msg)
            return {"ret": 0}

        async def get_config(self, *_args, **_kwargs):
            return {}

    bus = MessageBus()
    cfg = WechatConfig(enabled=True, token="t", account_id="acc@im.bot")
    ch = WechatChannel(cfg, bus, tmp_path)
    ch._accounts = {
        "acc-key": ResolvedWechatAccount(
            key="acc-key",
            account_id="acc@im.bot",
            token="t",
            base_url="https://ilinkai.weixin.qq.com",
            cdn_base_url="https://novac2c.cdn.weixin.qq.com/c2c",
            route_tag=None,
            allow_from=[],
        )
    }
    api = _FakeApi()
    ch._apis = {"acc-key": api}  # type: ignore[assignment]
    msg = OutboundMessage(
        session_key="wechat:acc-key:u1@im.wechat",
        content="pong",
        metadata={},
    )
    asyncio.run(
        ch.send(
            msg,
            ChannelEndpoint(
                channel="wechat",
                chat_id="u1@im.wechat",
                metadata={"wechat": {"account_key": "acc-key", "context_token": "ctx-1"}},
            ),
        )
    )
    assert len(api.sent) == 1
    assert api.sent[0]["to_user_id"] == "u1@im.wechat"
    assert api.sent[0]["context_token"] == "ctx-1"


def test_send_falls_back_to_single_account_when_default_missing(tmp_path: Path):
    class _FakeApi:
        def __init__(self):
            self.sent = []

        async def send_message(self, msg):
            self.sent.append(msg)
            return {"ret": 0}

        async def get_config(self, *_args, **_kwargs):
            return {}

    bus = MessageBus()
    cfg = WechatConfig(enabled=True, token="", account_id="")
    ch = WechatChannel(cfg, bus, tmp_path)
    ch._accounts = {
        "acc-x": ResolvedWechatAccount(
            key="acc-x",
            account_id="x@im.bot",
            token="tok",
            base_url="https://ilinkai.weixin.qq.com",
            cdn_base_url="https://novac2c.cdn.weixin.qq.com/c2c",
            route_tag=None,
            allow_from=[],
        )
    }
    api = _FakeApi()
    ch._apis = {"acc-x": api}  # type: ignore[assignment]

    # Simulate message-tool style send without account metadata.
    msg = OutboundMessage(session_key="wechat:acc-x:u2@im.wechat", content="hello", metadata={})
    asyncio.run(
        ch.send(
            msg,
            ChannelEndpoint(channel="wechat", chat_id="u2@im.wechat", metadata={}),
        )
    )

    assert len(api.sent) == 1
    assert api.sent[0]["to_user_id"] == "u2@im.wechat"


def test_send_skips_when_account_paused(tmp_path: Path):
    class _FakeApi:
        def __init__(self):
            self.sent = []

        async def send_message(self, msg):
            self.sent.append(msg)
            return {"ret": 0}

        async def get_config(self, *_args, **_kwargs):
            return {}

    bus = MessageBus()
    cfg = WechatConfig(enabled=True, token="", account_id="")
    ch = WechatChannel(cfg, bus, tmp_path)
    ch._accounts = {
        "acc-x": ResolvedWechatAccount(
            key="acc-x",
            account_id="x@im.bot",
            token="tok",
            base_url="https://ilinkai.weixin.qq.com",
            cdn_base_url="https://novac2c.cdn.weixin.qq.com/c2c",
            route_tag=None,
            allow_from=[],
        )
    }
    api = _FakeApi()
    ch._apis = {"acc-x": api}  # type: ignore[assignment]
    ch._guard.pause("acc-x")

    asyncio.run(
        ch.send(
            OutboundMessage(session_key="wechat:acc-x:u2@im.wechat", content="hello"),
            ChannelEndpoint(channel="wechat", chat_id="u2@im.wechat", metadata={}),
        )
    )

    assert api.sent == []


def test_send_ignores_non_dict_metadata(tmp_path: Path):
    class _FakeApi:
        def __init__(self):
            self.sent = []

        async def send_message(self, msg):
            self.sent.append(msg)
            return {"ret": 0}

        async def get_config(self, *_args, **_kwargs):
            return {}

    bus = MessageBus()
    cfg = WechatConfig(enabled=True, token="", account_id="")
    ch = WechatChannel(cfg, bus, tmp_path)
    ch._accounts = {
        "acc-x": ResolvedWechatAccount(
            key="acc-x",
            account_id="x@im.bot",
            token="tok",
            base_url="https://ilinkai.weixin.qq.com",
            cdn_base_url="https://novac2c.cdn.weixin.qq.com/c2c",
            route_tag=None,
            allow_from=[],
        )
    }
    api = _FakeApi()
    ch._apis = {"acc-x": api}  # type: ignore[assignment]

    msg = OutboundMessage(session_key="wechat:acc-x:u3@im.wechat", content="hello")
    msg.metadata = "bad-metadata"  # type: ignore[assignment]
    asyncio.run(
        ch.send(
            msg,
            ChannelEndpoint(channel="wechat", chat_id="u3@im.wechat", metadata={}),
        )
    )

    assert len(api.sent) == 1


def test_handle_inbound_rejects_sender_not_in_allow_list(tmp_path: Path):
    bus = MessageBus()
    cfg = WechatConfig(enabled=True, token="t", account_id="acc@im.bot")
    ch = WechatChannel(cfg, bus, tmp_path)
    account = ResolvedWechatAccount(
        key="acc-key",
        account_id="acc@im.bot",
        token="t",
        base_url="https://ilinkai.weixin.qq.com",
        cdn_base_url="https://novac2c.cdn.weixin.qq.com/c2c",
        route_tag=None,
        allow_from=["friend@im.wechat"],
    )

    async def run_case():
        await ch._handle_inbound(
            account,
            {
                "from_user_id": "stranger@im.wechat",
                "item_list": [{"type": ITEM_TYPE_TEXT, "text_item": {"text": "hello"}}],
            },
        )
        try:
            return await asyncio.wait_for(bus.consume_inbound(), timeout=0.05)
        except asyncio.TimeoutError:
            return None

    inbound = asyncio.run(run_case())
    assert inbound is None


def test_handle_inbound_skips_when_sender_id_missing(tmp_path: Path):
    bus = MessageBus()
    cfg = WechatConfig(enabled=True, token="t", account_id="acc@im.bot")
    ch = WechatChannel(cfg, bus, tmp_path)
    account = ResolvedWechatAccount(
        key="acc-key",
        account_id="acc@im.bot",
        token="t",
        base_url="https://ilinkai.weixin.qq.com",
        cdn_base_url="https://novac2c.cdn.weixin.qq.com/c2c",
        route_tag=None,
        allow_from=[],
    )

    async def run_case():
        await ch._handle_inbound(account, {"item_list": []})
        try:
            return await asyncio.wait_for(bus.consume_inbound(), timeout=0.05)
        except asyncio.TimeoutError:
            return None

    inbound = asyncio.run(run_case())
    assert inbound is None


def test_extract_inbound_media_download_failure_placeholder(tmp_path: Path, monkeypatch):
    bus = MessageBus()
    cfg = WechatConfig(enabled=True, token="t", account_id="acc@im.bot")
    ch = WechatChannel(cfg, bus, tmp_path)
    account = ResolvedWechatAccount(
        key="acc-key",
        account_id="acc@im.bot",
        token="t",
        base_url="https://ilinkai.weixin.qq.com",
        cdn_base_url="https://novac2c.cdn.weixin.qq.com/c2c",
        route_tag=None,
        allow_from=[],
    )

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("download failed")

    monkeypatch.setattr("weavbot.channels.wechat.channel.download_media_file", _boom)

    content, media = asyncio.run(
        ch._extract_inbound_content(
            account,
            {
                "message_id": 9,
                "item_list": [
                    {
                        "type": ITEM_TYPE_IMAGE,
                        "image_item": {"media": {"encrypt_query_param": "abc", "aes_key": "AA=="}},
                    }
                ],
            },
        )
    )
    assert media == []
    assert "[wechat:image:download_failed]" in content


def test_extract_inbound_voice_marker(tmp_path: Path):
    bus = MessageBus()
    cfg = WechatConfig(enabled=True, token="t", account_id="acc@im.bot")
    ch = WechatChannel(cfg, bus, tmp_path)
    account = ResolvedWechatAccount(
        key="acc-key",
        account_id="acc@im.bot",
        token="t",
        base_url="https://ilinkai.weixin.qq.com",
        cdn_base_url="https://novac2c.cdn.weixin.qq.com/c2c",
        route_tag=None,
        allow_from=[],
    )
    content, _media = asyncio.run(
        ch._extract_inbound_content(
            account, {"item_list": [{"type": ITEM_TYPE_VOICE, "voice_item": {}}]}
        )
    )
    assert "[wechat:voice]" in content
