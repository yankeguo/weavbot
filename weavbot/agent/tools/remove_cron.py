"""Tool for removing cron jobs."""

from typing import Any

from weavbot.agent.tools.base import Tool
from weavbot.cron.service import CronService


class RemoveCronTool(Tool):
    """Tool to remove scheduled jobs by id."""

    def __init__(self, cron_service: CronService):
        self._cron = cron_service

    @property
    def name(self) -> str:
        return "remove_cron"

    @property
    def description(self) -> str:
        return "Remove a scheduled cron job by job_id."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID to remove"},
            },
            "required": ["job_id"],
        }

    async def execute(self, job_id: str | None = None, *args: Any, **kwargs: Any) -> str:
        if not job_id:
            return "Error: job_id is required for remove"
        if self._cron.remove_job(job_id):
            return f"Removed job {job_id}"
        return f"Job {job_id} not found"
