"""Tool for listing cron jobs."""

from typing import Any

from weavbot.agent.tools.base import Tool, ToolExecutionContext
from weavbot.cron.service import CronService


class ListCronTool(Tool):
    """Tool to list scheduled jobs."""

    def __init__(self, cron_service: CronService):
        self._cron = cron_service

    @property
    def name(self) -> str:
        return "list_cron"

    @property
    def description(self) -> str:
        return "List scheduled cron jobs."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, *, context: ToolExecutionContext, **kwargs: Any) -> str:
        _ = context
        jobs = self._cron.list_jobs()
        if not jobs:
            return "No scheduled jobs."
        lines = [f"- {job.name} (id: {job.id}, {job.schedule.kind})" for job in jobs]
        return "Scheduled jobs:\n" + "\n".join(lines)
