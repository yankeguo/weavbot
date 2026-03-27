"""Spawn tool for creating background subagents."""

from typing import TYPE_CHECKING, Any

from weavbot.agent.tools.base import Tool, ToolExecutionContext
from weavbot.channels.store import ChannelStore

if TYPE_CHECKING:
    from weavbot.agent.subagent import SubagentManager


class SpawnTool(Tool):
    """Tool to spawn a subagent for background task execution."""

    def __init__(self, manager: "SubagentManager", channel_store: ChannelStore | None = None):
        self._manager = manager
        self._channel_store = channel_store

    @property
    def name(self) -> str:
        return "spawn"

    @property
    def description(self) -> str:
        return (
            "Spawn an in-process subagent to handle a task in the background. "
            "Use this for complex or time-consuming tasks that can run independently. "
            "The subagent has access to file tools, shell, and fetch, "
            "but NOT message, spawn, add_cron, list_cron, or remove_cron. "
            "It runs as an async task in the same process (not a separate OS process—do not use ps/top to check). "
            "Wait for the completion message in this chat to know when it finishes."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Task description for the subagent",
                },
                "label": {
                    "type": "string",
                    "description": "Short display label for the task",
                },
            },
            "required": ["task"],
        }

    async def execute(
        self,
        *,
        context: ToolExecutionContext,
        task: str,
        label: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Spawn a subagent to execute the given task."""
        if not self._channel_store:
            return "Error: channel target store is not configured"
        target = self._channel_store.resolve(context.session_key)
        if not target:
            return f"Error: no channel target found for session {context.session_key}"
        return await self._manager.spawn(
            task=task,
            label=label,
            origin_channel=target.channel,
            origin_chat_id=target.chat_id,
            session_key=context.session_key,
            origin_metadata=target.metadata,
        )
