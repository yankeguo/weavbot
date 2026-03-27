"""Message tool for sending messages to users."""

from typing import Any, Awaitable, Callable

from weavbot.agent.tools.base import Tool, ToolExecutionContext
from weavbot.bus.events import OutboundMessage


class MessageTool(Tool):
    """Tool to send messages to users on chat channels."""

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
    ):
        self._send_callback = send_callback

    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        """Set the callback for sending messages."""
        self._send_callback = callback

    @property
    def name(self) -> str:
        return "message"

    @property
    def description(self) -> str:
        return (
            "Send a message to a specific chat channel. Use this only when targeting a different "
            "channel/chat than the current conversation, or when explicitly asked to send a message. "
            "For normal replies in the current conversation, respond with text directly."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Message content to send"},
                "channel": {
                    "type": "string",
                    "description": "Target channel (e.g. telegram, discord)",
                },
                "chat_id": {"type": "string", "description": "Target chat or user ID"},
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
        channel: str | None = None,
        chat_id: str | None = None,
        message_id: str | None = None,
        media: list[str] | None = None,
        **kwargs: Any,
    ) -> str:
        channel = channel or context.channel
        chat_id = chat_id or context.chat_id
        message_id = message_id or context.message_id
        metadata = dict(context.metadata or {})
        metadata["message_id"] = message_id

        if not channel or not chat_id:
            return "Error: No target channel/chat specified"

        if not self._send_callback:
            return "Error: Message sending not configured"

        msg = OutboundMessage(
            channel=channel,
            chat_id=chat_id,
            content=content,
            media=media or [],
            metadata=metadata,
        )

        try:
            await self._send_callback(msg)
            if channel == context.channel and chat_id == context.chat_id:
                context.metadata["_message_sent_in_turn"] = True
            media_info = f" with {len(media)} attachments" if media else ""
            return f"Message sent to {channel}:{chat_id}{media_info}"
        except Exception as e:
            return f"Error sending message: {str(e)}"
