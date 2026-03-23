import asyncio
from pathlib import Path

from weavbot.bus.events import OutboundMessage
from weavbot.bus.queue import MessageBus
from weavbot.channels.wechat.accounts import resolve_accounts
from weavbot.channels.wechat.channel import WechatChannel
from weavbot.channels.wechat.session_guard import SessionGuard
from weavbot.channels.wechat.types import ITEM_TYPE_TEXT, ResolvedWechatAccount
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
        await ch._handle_inbound(
            account,
            {
                "from_user_id": "u1@im.wechat",
                "message_id": 1,
                "context_token": "ctx-1",
                "item_list": [{"type": ITEM_TYPE_TEXT, "text_item": {"text": "hello"}}],
            },
        )
        return await bus.consume_inbound()

    inbound = asyncio.run(run_case())
    assert inbound.channel == "wechat"
    assert inbound.chat_id == "u1@im.wechat"
    assert inbound.session_key == "wechat:acc-key:u1@im.wechat"
    assert inbound.metadata["wechat"]["context_token"] == "ctx-1"


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
        channel="wechat",
        chat_id="u1@im.wechat",
        content="pong",
        metadata={"wechat": {"account_key": "acc-key", "context_token": "ctx-1"}},
    )
    asyncio.run(ch.send(msg))
    assert len(api.sent) == 1
    assert api.sent[0]["to_user_id"] == "u1@im.wechat"
    assert api.sent[0]["context_token"] == "ctx-1"
