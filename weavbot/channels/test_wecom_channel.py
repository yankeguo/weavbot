import asyncio

import pytest

from weavbot.bus.events import OutboundMessage
from weavbot.bus.queue import MessageBus
from weavbot.channels.wecom import EVENT_ENTER_CHAT, WeComChannel
from weavbot.config.schema import WeComConfig


def _make_channel(tmp_path):
    cfg = WeComConfig(bot_id="bot-id", secret="bot-secret")
    return WeComChannel(cfg, MessageBus(), tmp_path)


def test_parse_mixed_message(tmp_path):
    channel = _make_channel(tmp_path)
    body = {
        "msgtype": "mixed",
        "mixed": {
            "msg_item": [
                {"msgtype": "text", "text": {"content": "hello"}},
                {
                    "msgtype": "image",
                    "image": {"url": "https://img.example/a.png", "aeskey": "abc123"},
                },
            ]
        },
    }
    content, media = channel._parse_inbound_message_body(body, "mixed")
    assert "hello" in content
    assert "image:https://img.example/a.png" in content
    assert media == ["https://img.example/a.png"]


def test_extract_req_id_via_message_id_cache(tmp_path):
    channel = _make_channel(tmp_path)
    channel._remember_msgid_reqid("m1", "r1")
    req_id = channel._extract_req_id({"message_id": "m1"}, {})
    assert req_id == "r1"


def test_rate_limit(tmp_path):
    channel = _make_channel(tmp_path)
    channel.config.per_chat_per_minute = 2
    channel.config.per_chat_per_hour = 10
    assert channel._within_rate_limit("chat-a") is True
    assert channel._within_rate_limit("chat-a") is True
    assert channel._within_rate_limit("chat-a") is False


def test_guess_media_type(tmp_path):
    channel = _make_channel(tmp_path)
    assert channel._guess_media_type(tmp_path / "a.jpg") == "image"
    assert channel._guess_media_type(tmp_path / "a.amr") == "voice"
    assert channel._guess_media_type(tmp_path / "a.mp4") == "video"
    assert channel._guess_media_type(tmp_path / "a.bin") == "file"


def test_event_callback_publishes_inbound(tmp_path):
    channel = _make_channel(tmp_path)

    async def run_case():
        frame = {
            "cmd": "aibot_event_callback",
            "headers": {"req_id": "req-1"},
            "body": {
                "msgid": "msg-1",
                "chattype": "single",
                "from": {"userid": "u1"},
                "event": {"eventtype": "feedback_event"},
            },
        }
        await channel._handle_event_callback(frame)
        msg = await channel.bus.consume_inbound()
        return msg

    inbound = asyncio.run(run_case())
    assert inbound.channel == "wecom"
    assert inbound.sender_id == "u1"
    assert inbound.metadata["req_id"] == "req-1"
    assert inbound.metadata["wecom"]["event_type"] == "feedback_event"


def test_send_enter_chat_uses_welcome_command(tmp_path):
    channel = _make_channel(tmp_path)
    channel._ws = object()
    captured = {}

    async def fake_send_reply(*, req_id: str, cmd: str, body: dict):
        captured["req_id"] = req_id
        captured["cmd"] = cmd
        captured["body"] = body
        return {"errcode": 0}

    channel._send_reply = fake_send_reply  # type: ignore[method-assign]

    async def run_case():
        await channel.send(
            OutboundMessage(
                channel="wecom",
                chat_id="user-1",
                content="hello",
                metadata={
                    "wecom": {"req_id": "req-2", "event_type": EVENT_ENTER_CHAT},
                },
            )
        )

    asyncio.run(run_case())
    assert captured["req_id"] == "req-2"
    assert captured["cmd"] == "aibot_respond_welcome_msg"
    assert captured["body"]["text"]["content"] == "hello"


def test_build_safe_media_path_strips_parent_dirs(tmp_path):
    channel = _make_channel(tmp_path)
    safe = channel._build_safe_media_path("../nested/evil.bin")
    assert safe.parent.resolve() == channel._temp_media_dir.resolve()
    assert safe.name == "evil.bin"


def test_decrypt_media_data_invalid_base64_raises():
    try:
        import cryptography  # noqa: F401
    except ImportError:
        pytest.skip("cryptography not installed")

    with pytest.raises(ValueError, match="base64"):
        WeComChannel.decrypt_media_data(b"0123456789abcdef", "%%%bad%%%")
