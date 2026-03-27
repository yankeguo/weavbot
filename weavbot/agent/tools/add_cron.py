"""Tool for adding cron jobs."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from weavbot.agent.tools.base import Tool, ToolExecutionContext
from weavbot.cron.service import CronService
from weavbot.cron.types import CronSchedule


class AddCronTool(Tool):
    """Tool to schedule reminders and recurring tasks."""

    def __init__(self, cron_service: CronService):
        self._cron = cron_service

    @property
    def name(self) -> str:
        return "add_cron"

    @property
    def description(self) -> str:
        return "Add a scheduled reminder/task. Supports interval, cron expression, or one-time datetime."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Reminder message"},
                "interval": {
                    "type": "integer",
                    "description": "Repeat interval in seconds",
                },
                "expr": {
                    "type": "string",
                    "description": "Cron expression (e.g. 0 9 * * *)",
                },
                "tz": {
                    "type": "string",
                    "description": "IANA timezone (e.g. America/Vancouver), only valid with expr",
                },
                "at": {
                    "type": "string",
                    "description": "ISO datetime for one-time execution (e.g. '2026-02-12T10:30:00')",
                },
            },
            "required": ["message"],
        }

    async def execute(
        self,
        *,
        context: ToolExecutionContext,
        message: str,
        interval: int | None = None,
        expr: str | None = None,
        tz: str | None = None,
        at: str | None = None,
        **kwargs: Any,
    ) -> str:
        if context.session_key.startswith("cron_"):
            return "Error: cannot schedule new jobs from within a cron job execution"
        if not message:
            return "Error: message is required for add"
        original_session_key_for_cron = context.original_session_key or context.session_key
        if tz and not expr:
            return "Error: tz can only be used with expr"
        if tz:
            try:
                ZoneInfo(tz)
            except (KeyError, Exception):
                return f"Error: unknown timezone '{tz}'"

        delete_after = False
        if interval:
            schedule = CronSchedule(kind="every", every_ms=interval * 1000)
        elif expr:
            schedule = CronSchedule(kind="cron", expr=expr, tz=tz)
        elif at:
            dt = datetime.fromisoformat(at)
            at_ms = int(dt.timestamp() * 1000)
            schedule = CronSchedule(kind="at", at_ms=at_ms)
            delete_after = True
        else:
            return "Error: either interval, expr, or at is required"

        job = self._cron.add_job(
            name=message[:30],
            schedule=schedule,
            message=message,
            deliver=True,
            original_session_key=original_session_key_for_cron,
            interactive_session_key=original_session_key_for_cron,
            delete_after_run=delete_after,
        )
        return f"Created job '{job.name}' (id: {job.id})"
