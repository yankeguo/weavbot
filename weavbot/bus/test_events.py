from weavbot.bus.events import InboundMessage


def test_inbound_message_default_session_key() -> None:
    key = InboundMessage.default_session_key("slack", "C123")
    assert key == "slack:C123"


def test_inbound_message_keeps_explicit_session_key() -> None:
    msg = InboundMessage(
        channel="cli",
        sender_id="user",
        chat_id="direct",
        session_key="cli:direct:custom",
        content="hello",
    )
    assert msg.session_key == "cli:direct:custom"
