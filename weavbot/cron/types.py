"""Cron types."""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class CronSchedule:
    """Schedule definition for a cron job."""

    kind: Literal["at", "every", "cron"]
    # For "at": timestamp in ms
    at_ms: int | None = None
    # For "every": interval in ms
    every_ms: int | None = None
    # For "cron": cron expression (e.g. "0 9 * * *")
    expr: str | None = None
    # Timezone for cron expressions
    tz: str | None = None


@dataclass
class CronPayload:
    """What to do when the job runs."""

    kind: Literal["system_event", "agent_turn"] = "agent_turn"
    message: str = ""
    # Deliver response to channel
    deliver: bool = False
    original_session_key: str | None = None
    interactive_session_key: str | None = None

    @classmethod
    def from_store_dict(cls, raw: dict[str, Any]) -> "CronPayload":
        """Create payload from jobs.json payload block."""
        payload = raw if isinstance(raw, dict) else {}
        return cls(
            kind=payload.get("kind", "agent_turn"),
            message=payload.get("message", ""),
            deliver=payload.get("deliver", False),
            original_session_key=payload.get("originalSessionKey"),
            interactive_session_key=payload.get("interactiveSessionKey"),
        )

    def to_store_dict(self) -> dict[str, Any]:
        """Convert payload to jobs.json payload block."""
        return {
            "kind": self.kind,
            "message": self.message,
            "deliver": self.deliver,
            "originalSessionKey": self.original_session_key,
            "interactiveSessionKey": self.interactive_session_key,
        }


@dataclass
class CronJobState:
    """Runtime state of a job."""

    next_run_at_ms: int | None = None
    last_run_at_ms: int | None = None
    last_status: Literal["ok", "error", "skipped"] | None = None
    last_error: str | None = None


@dataclass
class CronJob:
    """A scheduled job."""

    id: str
    name: str
    enabled: bool = True
    schedule: CronSchedule = field(default_factory=lambda: CronSchedule(kind="every"))
    payload: CronPayload = field(default_factory=CronPayload)
    state: CronJobState = field(default_factory=CronJobState)
    created_at_ms: int = 0
    updated_at_ms: int = 0
    delete_after_run: bool = False


@dataclass
class CronStore:
    """Persistent store for cron jobs."""

    version: int = 1
    jobs: list[CronJob] = field(default_factory=list)
