from weavbot.bus.events import InboundMessage
from weavbot.utils.helpers import build_session_key


def test_build_session_key_channel_chat_convention() -> None:
    assert build_session_key("slack", "C123") == "slack_C123"


def test_inbound_message_keeps_explicit_session_key() -> None:
    msg = InboundMessage(
        channel="cli",
        sender_id="user",
        chat_id="direct",
        session_key="cli_direct_custom",
        content="hello",
    )
    assert msg.session_key == "cli_direct_custom"
