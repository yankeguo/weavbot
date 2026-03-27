from weavbot.channels.store import ChannelTarget
from weavbot.cli.commands import _resolve_cron_interactive_target


def test_resolve_cron_interactive_target_prefers_interactive_key() -> None:
    target = _resolve_cron_interactive_target(
        job_id="job-1",
        interactive_session_key="slack_C111_T333",
        interactive_resolved=ChannelTarget(
            channel="slack",
            chat_id="C111",
            metadata={"slack": {"thread_ts": "T333"}},
        ),
        original_session_key="slack_C222_T444",
        primary=ChannelTarget(channel="slack", chat_id="C222", metadata={}),
    )

    assert target is not None
    assert target.session_key == "slack_C111_T333"
    assert target.chat_id == "C111"


def test_resolve_cron_interactive_target_falls_back_to_original_route_only() -> None:
    target = _resolve_cron_interactive_target(
        job_id="job-1",
        interactive_session_key="slack_missing",
        interactive_resolved=None,
        original_session_key="slack_C222_T444",
        primary=ChannelTarget(channel="slack", chat_id="C222", metadata={}),
    )

    assert target is not None
    assert target.session_key == "slack_C222_T444"
    assert target.channel == "slack"
    assert target.chat_id == "C222"


def test_resolve_cron_interactive_target_returns_none_when_unroutable() -> None:
    target = _resolve_cron_interactive_target(
        job_id="job-1",
        interactive_session_key="slack_missing",
        interactive_resolved=None,
        original_session_key="slack_C222_T444",
        primary=None,
    )

    assert target is None
