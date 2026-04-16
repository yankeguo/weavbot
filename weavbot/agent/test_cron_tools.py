import asyncio
from typing import cast

from weavbot.agent.tools.add_cron import AddCronTool
from weavbot.agent.tools.list_cron import ListCronTool
from weavbot.agent.tools.remove_cron import RemoveCronTool
from weavbot.cron.service import CronService
from weavbot.cron.types import CronJob, CronPayload, CronSchedule


class _FakeCronService:
    def __init__(self):
        self.jobs: list[CronJob] = []
        self.removed_ids: set[str] = set()
        self.last_added: dict | None = None

    def add_job(
        self,
        *,
        name: str,
        schedule: CronSchedule,
        message: str,
        deliver: bool,
        channel: str,
        to: str,
        delete_after_run: bool,
    ) -> CronJob:
        self.last_added = {
            "name": name,
            "schedule": schedule,
            "message": message,
            "deliver": deliver,
            "channel": channel,
            "to": to,
            "delete_after_run": delete_after_run,
        }
        job = CronJob(
            id=f"job-{len(self.jobs) + 1}",
            name=name,
            schedule=schedule,
            payload=CronPayload(message=message, deliver=deliver, channel=channel, to=to),
            delete_after_run=delete_after_run,
        )
        self.jobs.append(job)
        return job

    def list_jobs(self):
        return [job for job in self.jobs if job.id not in self.removed_ids]

    def remove_job(self, job_id: str) -> bool:
        exists = any(job.id == job_id for job in self.jobs)
        if exists:
            self.removed_ids.add(job_id)
        return exists


def test_add_cron_requires_message_and_context():
    svc = _FakeCronService()
    tool = AddCronTool(cast(CronService, svc))
    assert (
        asyncio.run(tool.execute(message="", interval=60)) == "Error: message is required for add"
    )
    assert (
        asyncio.run(tool.execute(message="hi", interval=60))
        == "Error: no session context (channel/chat_id)"
    )


def test_add_cron_rejects_tz_without_expr_and_unknown_tz():
    svc = _FakeCronService()
    tool = AddCronTool(cast(CronService, svc))
    tool.set_context("telegram", "u1")

    assert (
        asyncio.run(tool.execute(message="hi", interval=60, tz="America/Vancouver"))
        == "Error: tz can only be used with expr"
    )
    assert (
        asyncio.run(tool.execute(message="hi", expr="0 9 * * *", tz="Nope/Timezone"))
        == "Error: unknown timezone 'Nope/Timezone'"
    )


def test_add_cron_adds_interval_job():
    svc = _FakeCronService()
    tool = AddCronTool(cast(CronService, svc))
    tool.set_context("telegram", "u1")

    out = asyncio.run(tool.execute(message="Take a break", interval=120))
    assert out.startswith("Created job 'Take a break'")
    assert svc.last_added is not None
    assert svc.last_added["channel"] == "telegram"
    assert svc.last_added["to"] == "u1"
    assert svc.last_added["schedule"].kind == "every"
    assert svc.last_added["schedule"].every_ms == 120_000


def test_add_cron_blocks_nested_schedule():
    svc = _FakeCronService()
    tool = AddCronTool(cast(CronService, svc))
    tool.set_context("telegram", "u1")
    token = tool.set_cron_context(True)
    try:
        out = asyncio.run(tool.execute(message="Nested", interval=60))
    finally:
        tool.reset_cron_context(token)
    assert out == "Error: cannot schedule new jobs from within a cron job execution"


def test_list_cron_outputs_jobs():
    svc = _FakeCronService()
    add_tool = AddCronTool(cast(CronService, svc))
    add_tool.set_context("telegram", "u1")
    asyncio.run(add_tool.execute(message="job one", interval=60))

    list_tool = ListCronTool(cast(CronService, svc))
    out = asyncio.run(list_tool.execute())
    assert "Scheduled jobs:" in out
    assert "job one" in out


def test_remove_cron_requires_job_id_and_handles_missing():
    svc = _FakeCronService()
    tool = RemoveCronTool(cast(CronService, svc))
    assert asyncio.run(tool.execute()) == "Error: job_id is required for remove"
    assert asyncio.run(tool.execute(job_id="missing")) == "Job missing not found"


def test_remove_cron_removes_existing_job():
    svc = _FakeCronService()
    add_tool = AddCronTool(cast(CronService, svc))
    add_tool.set_context("telegram", "u1")
    asyncio.run(add_tool.execute(message="job one", interval=60))
    job_id = svc.jobs[0].id

    remove_tool = RemoveCronTool(cast(CronService, svc))
    out = asyncio.run(remove_tool.execute(job_id=job_id))
    assert out == f"Removed job {job_id}"
