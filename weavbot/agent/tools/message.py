"""Message tool for sending messages to users."""

from typing import Any, Awaitable, Callable

from weavbot.agent.tools.base import Tool, ToolExecutionContext
from weavbot.bus.events import OutboundMessage
from weavbot.channels.store import ChannelStore


class MessageTool(Tool):
    """Tool to send messages to users on chat channels."""

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        channel_store: ChannelStore | None = None,
    ):
        self._send_callback = send_callback
        self._channel_store = channel_store

    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        """Set the callback for sending messages."""
        self._send_callback = callback

    @property
    def name(self) -> str:
        return "message"

    @property
    def description(self) -> str:
        return (
            "Send a message to a specific session key. Use this only when targeting a different "
            "session than the current conversation, or when explicitly asked to send a message. "
            "For normal replies in the current conversation, respond with text directly."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Message content to send"},
                "session_key": {
                    "type": "string",
                    "description": "Target session key to deliver the message",
                },
                "media": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File paths to attach (images, audio, documents)",
                },
            },
            "required": ["content"],
        }

    async def execute(
        self,
        *,
        context: ToolExecutionContext,
        content: str,
        session_key: str | None = None,
        message_id: str | None = None,
        media: list[str] | None = None,
        **kwargs: Any,
    ) -> str:
        target_session_key = (
            (session_key or "").strip()
            or (context.interactive_session_key or "").strip()
            or context.session_key
        )
        message_id = message_id or context.message_id
        metadata = {}
        provided_metadata = kwargs.get("metadata")
        if isinstance(provided_metadata, dict):
            metadata.update(provided_metadata)
        if message_id is not None:
            metadata["message_id"] = message_id

        if not target_session_key:
            return "Error: No target session_key specified"

        if not self._channel_store:
            return "Error: channel target store is not configured"
        if not self._channel_store.resolve(target_session_key):
            return f"Error: no channel target found for session {target_session_key}"

        if not self._send_callback:
            return "Error: Message sending not configured"

        msg = OutboundMessage(
            session_key=target_session_key,
            content=content,
            media=media or [],
            metadata=metadata,
        )

        try:
            await self._send_callback(msg)
            media_info = f" with {len(media)} attachments" if media else ""
            return f"Message sent to session {target_session_key}{media_info}"
        except Exception as e:
            return f"Error sending message: {str(e)}"
