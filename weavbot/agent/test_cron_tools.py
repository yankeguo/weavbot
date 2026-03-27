import asyncio

from weavbot.agent.tools.add_cron import AddCronTool
from weavbot.agent.tools.base import ToolExecutionContext
from weavbot.agent.tools.list_cron import ListCronTool
from weavbot.agent.tools.remove_cron import RemoveCronTool
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
        interactive_channel: str | None = None,
        interactive_chat_id: str | None = None,
        interactive_session_key: str | None = None,
        interactive_metadata: dict | None = None,
        delete_after_run: bool,
    ) -> CronJob:
        self.last_added = {
            "name": name,
            "schedule": schedule,
            "message": message,
            "deliver": deliver,
            "channel": channel,
            "to": to,
            "interactive_channel": interactive_channel,
            "interactive_chat_id": interactive_chat_id,
            "interactive_session_key": interactive_session_key,
            "interactive_metadata": interactive_metadata or {},
            "delete_after_run": delete_after_run,
        }
        job = CronJob(
            id=f"job-{len(self.jobs) + 1}",
            name=name,
            schedule=schedule,
            payload=CronPayload(
                message=message,
                deliver=deliver,
                channel=channel,
                to=to,
                interactive_channel=interactive_channel,
                interactive_chat_id=interactive_chat_id,
                interactive_session_key=interactive_session_key,
                interactive_metadata=interactive_metadata or {},
            ),
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


_CTX = ToolExecutionContext(channel="telegram", chat_id="u1", session_key="telegram:u1")


def test_add_cron_requires_message_and_context():
    svc = _FakeCronService()
    tool = AddCronTool(svc)
    assert (
        asyncio.run(tool.execute(context=_CTX, message="", interval=60))
        == "Error: message is required for add"
    )
    assert (
        asyncio.run(
            tool.execute(
                context=ToolExecutionContext(channel="", chat_id="", session_key="missing"),
                message="hi",
                interval=60,
            )
        )
        == "Error: no session context (channel/chat_id)"
    )


def test_add_cron_rejects_tz_without_expr_and_unknown_tz():
    svc = _FakeCronService()
    tool = AddCronTool(svc)

    assert (
        asyncio.run(tool.execute(context=_CTX, message="hi", interval=60, tz="America/Vancouver"))
        == "Error: tz can only be used with expr"
    )
    assert (
        asyncio.run(tool.execute(context=_CTX, message="hi", expr="0 9 * * *", tz="Nope/Timezone"))
        == "Error: unknown timezone 'Nope/Timezone'"
    )


def test_add_cron_adds_interval_job():
    svc = _FakeCronService()
    tool = AddCronTool(svc)

    out = asyncio.run(tool.execute(context=_CTX, message="Take a break", interval=120))
    assert out.startswith("Created job 'Take a break'")
    assert svc.last_added is not None
    assert svc.last_added["channel"] == "telegram"
    assert svc.last_added["to"] == "u1"
    assert svc.last_added["interactive_channel"] == "telegram"
    assert svc.last_added["interactive_chat_id"] == "u1"
    assert svc.last_added["interactive_session_key"] == "telegram:u1"
    assert svc.last_added["schedule"].kind == "every"
    assert svc.last_added["schedule"].every_ms == 120_000


def test_add_cron_blocks_nested_schedule():
    svc = _FakeCronService()
    tool = AddCronTool(svc)
    nested_ctx = ToolExecutionContext(
        channel="telegram",
        chat_id="u1",
        session_key="telegram:u1",
        metadata={"_cron_in_job": True},
    )
    out = asyncio.run(tool.execute(context=nested_ctx, message="Nested", interval=60))
    assert out == "Error: cannot schedule new jobs from within a cron job execution"


def test_list_cron_outputs_jobs():
    svc = _FakeCronService()
    add_tool = AddCronTool(svc)
    asyncio.run(add_tool.execute(context=_CTX, message="job one", interval=60))

    list_tool = ListCronTool(svc)
    out = asyncio.run(list_tool.execute(context=_CTX))
    assert "Scheduled jobs:" in out
    assert "job one" in out


def test_remove_cron_requires_job_id_and_handles_missing():
    svc = _FakeCronService()
    tool = RemoveCronTool(svc)
    assert asyncio.run(tool.execute(context=_CTX)) == "Error: job_id is required for remove"
    assert asyncio.run(tool.execute(context=_CTX, job_id="missing")) == "Job missing not found"


def test_remove_cron_removes_existing_job():
    svc = _FakeCronService()
    add_tool = AddCronTool(svc)
    asyncio.run(add_tool.execute(context=_CTX, message="job one", interval=60))
    job_id = svc.jobs[0].id

    remove_tool = RemoveCronTool(svc)
    out = asyncio.run(remove_tool.execute(context=_CTX, job_id=job_id))
    assert out == f"Removed job {job_id}"
