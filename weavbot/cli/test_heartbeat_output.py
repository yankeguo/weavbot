import pytest

from weavbot.cli.commands import (
    _assemble_heartbeat_response,
    _build_background_notify_contract,
    _build_cron_execute_input,
    _build_heartbeat_execute_input,
    _collect_heartbeat_progress,
    _looks_like_agent_error,
    _parse_heartbeat_target,
    _pick_heartbeat_target_from_sessions,
    _suppress_background_progress,
)


def test_heartbeat_response_without_toolcalls_uses_final_only() -> None:
    assembled = _assemble_heartbeat_response([], "同步完成")
    assert assembled == "同步完成"


def test_heartbeat_response_with_progress_and_final() -> None:
    progress = ["步骤 1: 扫描邮箱", "步骤 2: 邮件汇总报告"]
    assembled = _assemble_heartbeat_response(progress, "本次同步未发现新邮件。")
    assert assembled == "步骤 1: 扫描邮箱\n\n步骤 2: 邮件汇总报告\n\n本次同步未发现新邮件。"


def test_heartbeat_response_with_progress_only_fallback() -> None:
    assembled = _assemble_heartbeat_response(["步骤 1: 扫描邮箱"], "")
    assert assembled == "步骤 1: 扫描邮箱"


def test_heartbeat_progress_ignores_tool_hints() -> None:
    progress: list[str] = []
    _collect_heartbeat_progress(progress, 'read_file(path="HEARTBEAT.md")', tool_hint=True)
    _collect_heartbeat_progress(progress, "步骤 1: 扫描邮箱", tool_hint=False)
    assert progress == ["步骤 1: 扫描邮箱"]


def test_heartbeat_progress_deduplicates_adjacent_text() -> None:
    progress: list[str] = []
    _collect_heartbeat_progress(progress, "步骤 1: 扫描邮箱")
    _collect_heartbeat_progress(progress, "步骤 1: 扫描邮箱")
    assembled = _assemble_heartbeat_response(progress, "步骤 2: 汇总完成")
    assert assembled == "步骤 1: 扫描邮箱\n\n步骤 2: 汇总完成"


def test_heartbeat_response_empty_when_progress_and_final_are_empty() -> None:
    assembled = _assemble_heartbeat_response([], "")
    assert assembled == ""


def test_parse_heartbeat_target_wechat_scoped_key() -> None:
    parsed = _parse_heartbeat_target("wechat:bot-main:u_123")
    assert parsed == (
        "wechat",
        "u_123",
        "wechat:bot-main:u_123",
        {"wechat": {"account_key": "bot-main"}},
    )


def test_pick_heartbeat_target_prefers_enabled_wechat_and_exposes_metadata() -> None:
    sessions = [
        {"key": "feishu:oc_legacy"},
        {"key": "wechat:acc-a:u_new"},
    ]
    channel, chat_id, session_key, metadata = _pick_heartbeat_target_from_sessions(
        sessions, {"wechat"}
    )
    assert channel == "wechat"
    assert chat_id == "u_new"
    assert session_key == "wechat:acc-a:u_new"
    assert metadata == {"wechat": {"account_key": "acc-a"}}


def test_pick_heartbeat_target_fallbacks_to_cli_when_no_routable_session() -> None:
    sessions = [
        {"key": "feishu:oc_legacy"},
        {"key": "cli:direct"},
    ]
    channel, chat_id, session_key, metadata = _pick_heartbeat_target_from_sessions(
        sessions, {"wechat"}
    )
    assert channel == "cli"
    assert chat_id == "direct"
    assert session_key == "cli:direct"
    assert metadata == {}


def test_pick_heartbeat_target_ignores_background_sessions() -> None:
    sessions = [
        {"key": "heartbeat:telegram:1001:2026-03-26"},
        {"key": "cron:job-1"},
        {"key": "telegram:2002"},
    ]
    channel, chat_id, session_key, metadata = _pick_heartbeat_target_from_sessions(
        sessions, {"telegram"}
    )
    assert channel == "telegram"
    assert chat_id == "2002"
    assert session_key == "telegram:2002"
    assert metadata == {}


def test_pick_heartbeat_target_prefers_session_interactive_snapshot() -> None:
    sessions = [
        {
            "key": "telegram:1001",
            "metadata": {
                "interactive_target": {
                    "channel": "slack",
                    "chat_id": "C111",
                    "session_key": "slack:C111:T222",
                    "metadata": {"slack": {"thread_ts": "T222", "channel_type": "channel"}},
                }
            },
        }
    ]
    channel, chat_id, session_key, metadata = _pick_heartbeat_target_from_sessions(
        sessions, {"slack", "telegram"}
    )
    assert channel == "slack"
    assert chat_id == "C111"
    assert session_key == "slack:C111:T222"
    assert metadata == {"slack": {"thread_ts": "T222", "channel_type": "channel"}}


def test_background_notify_contract_mentions_message_and_target_context() -> None:
    contract = _build_background_notify_contract(
        source="Heartbeat",
        channel="wechat",
        chat_id="u_123",
        target_metadata={"wechat": {"account_key": "acc-a"}},
    )
    assert "Only notify when necessary by calling the `message` tool." in contract
    assert "channel: wechat" in contract
    assert "chat_id: u_123" in contract
    assert '"account_key": "acc-a"' in contract


def test_build_heartbeat_execute_input_includes_contract_and_tasks() -> None:
    text = _build_heartbeat_execute_input(
        "check pending reviews",
        channel="telegram",
        chat_id="1001",
        target_metadata={"foo": "bar"},
    )
    assert "[Heartbeat Task]" in text
    assert "check pending reviews" in text
    assert "[Heartbeat Notification Contract]" in text
    assert "channel: telegram" in text
    assert "chat_id: 1001" in text
    assert '"foo": "bar"' in text


def test_build_cron_execute_input_includes_contract_and_instruction() -> None:
    text = _build_cron_execute_input(
        job_name="daily-check",
        instruction="collect report and notify if needed",
        channel="slack",
        chat_id="C123",
    )
    assert "Task 'daily-check' has been triggered." in text
    assert "Scheduled instruction: collect report and notify if needed" in text
    assert "[Cron Notification Contract]" in text
    assert "channel: slack" in text
    assert "chat_id: C123" in text


def test_looks_like_agent_error_detects_known_failure_texts() -> None:
    assert _looks_like_agent_error("Sorry, I encountered an error calling the AI model.")
    assert _looks_like_agent_error("I reached the maximum number of tool call iterations (40).")
    assert not _looks_like_agent_error("All checks are done. No user notification is required.")


@pytest.mark.asyncio
async def test_suppress_background_progress_is_noop() -> None:
    assert await _suppress_background_progress("running tool call...", tool_hint=True) is None
    assert await _suppress_background_progress("step 1", tool_hint=False) is None
