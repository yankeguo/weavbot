import pytest

from weavbot.bus.events import InboundMessage


def test_inbound_message_default_session_key() -> None:
    key = InboundMessage.default_session_key("slack", "C123")
    assert key == "slack:C123"


def test_inbound_message_requires_non_empty_session_key() -> None:
    with pytest.raises(ValueError, match="session_key must be non-empty"):
        InboundMessage(
            channel="cli",
            sender_id="user",
            chat_id="direct",
            session_key="",
            content="hello",
        )
