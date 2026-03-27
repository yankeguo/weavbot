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
    channel: str | None = None  # e.g. "telegram"
    to: str | None = None  # e.g. phone number
    interactive_channel: str | None = None
    interactive_chat_id: str | None = None
    interactive_session_key: str | None = None
    interactive_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_store_dict(cls, raw: dict[str, Any]) -> "CronPayload":
        """Create payload from jobs.json payload block."""
        payload = raw if isinstance(raw, dict) else {}
        return cls(
            kind=payload.get("kind", "agent_turn"),
            message=payload.get("message", ""),
            deliver=payload.get("deliver", False),
            channel=payload.get("channel"),
            to=payload.get("to"),
            interactive_channel=payload.get("interactiveChannel"),
            interactive_chat_id=payload.get("interactiveChatId"),
            interactive_session_key=payload.get("interactiveSessionKey"),
            interactive_metadata=dict(payload.get("interactiveMetadata") or {}),
        )

    def to_store_dict(self) -> dict[str, Any]:
        """Convert payload to jobs.json payload block."""
        return {
            "kind": self.kind,
            "message": self.message,
            "deliver": self.deliver,
            "channel": self.channel,
            "to": self.to,
            "interactiveChannel": self.interactive_channel,
            "interactiveChatId": self.interactive_chat_id,
            "interactiveSessionKey": self.interactive_session_key,
            "interactiveMetadata": dict(self.interactive_metadata or {}),
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
