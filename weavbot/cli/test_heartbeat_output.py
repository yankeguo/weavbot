import pytest

from weavbot.channels.store import ChannelStore, ChannelEndpoint
from weavbot.cli.commands import (
    _assemble_heartbeat_response,
    _build_background_notify_contract,
    _build_cron_execute_input,
    _build_heartbeat_execute_input,
    _collect_heartbeat_progress,
    _looks_like_agent_error,
    _pick_heartbeat_target_from_sessions,
    _should_print_cli_progress,
    _suppress_background_progress,
)


def test_should_print_cli_progress_matches_channel_manager_gating() -> None:
    class Ch:
        send_tool_hints = False
        send_progress = True

    assert not _should_print_cli_progress(Ch(), is_tool_hint=True)
    assert _should_print_cli_progress(Ch(), is_tool_hint=False)

    class Ch2:
        send_tool_hints = True
        send_progress = False

    assert _should_print_cli_progress(Ch2(), is_tool_hint=True)
    assert not _should_print_cli_progress(Ch2(), is_tool_hint=False)

    assert _should_print_cli_progress(None, is_tool_hint=True)


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


@pytest.mark.asyncio
async def test_pick_heartbeat_target_prefers_enabled_wechat_and_exposes_metadata(tmp_path) -> None:
    store = ChannelStore(tmp_path / "channels")
    await store.upsert(
        "wechat_acc-a_u_new",
        ChannelEndpoint(
            channel="wechat",
            chat_id="u_new",
            metadata={"wechat": {"account_key": "acc-a"}},
        ),
    )
    sessions = [
        {"key": "feishu:oc_legacy"},
        {
            "key": "wechat_acc-a_u_new",
            "metadata": {
                "interactive_target": {
                    "session_key": "wechat_acc-a_u_new",
                    "metadata": {"wechat": {"account_key": "acc-a"}},
                }
            },
        },
    ]
    target = await _pick_heartbeat_target_from_sessions(sessions, {"wechat"}, store)
    assert target.channel == "wechat"
    assert target.chat_id == "u_new"
    assert target.session_key == "wechat_acc-a_u_new"
    assert target.metadata == {"wechat": {"account_key": "acc-a"}}


@pytest.mark.asyncio
async def test_pick_heartbeat_target_fallbacks_to_cli_when_no_routable_session(tmp_path) -> None:
    store = ChannelStore(tmp_path / "channels")
    sessions = [
        {"key": "feishu:oc_legacy"},
        {"key": "cli:direct"},
    ]
    target = await _pick_heartbeat_target_from_sessions(sessions, {"wechat"}, store)
    assert target.channel == "cli"
    assert target.chat_id == "direct"
    assert target.session_key == "cli_direct"
    assert target.metadata == {}


@pytest.mark.asyncio
async def test_pick_heartbeat_target_ignores_background_sessions(tmp_path) -> None:
    store = ChannelStore(tmp_path / "channels")
    await store.upsert(
        "telegram_2002",
        ChannelEndpoint(channel="telegram", chat_id="2002", metadata={}),
    )
    sessions = [
        {"key": "heartbeat:telegram:1001:2026-03-26"},
        {"key": "cron:job-1"},
        {
            "key": "telegram_2002",
            "metadata": {
                "interactive_target": {
                    "session_key": "telegram_2002",
                    "metadata": {},
                }
            },
        },
    ]
    target = await _pick_heartbeat_target_from_sessions(sessions, {"telegram"}, store)
    assert target.channel == "telegram"
    assert target.chat_id == "2002"
    assert target.session_key == "telegram_2002"
    assert target.metadata == {}


@pytest.mark.asyncio
async def test_pick_heartbeat_target_prefers_session_interactive_snapshot(tmp_path) -> None:
    store = ChannelStore(tmp_path / "channels")
    await store.upsert(
        "slack_C111_T222",
        ChannelEndpoint(
            channel="slack",
            chat_id="C111",
            metadata={"slack": {"thread_ts": "T222", "channel_type": "channel"}},
        ),
    )
    sessions = [
        {
            "key": "telegram:1001",
            "metadata": {
                "interactive_target": {
                    "session_key": "slack_C111_T222",
                    "metadata": {"slack": {"thread_ts": "T222", "channel_type": "channel"}},
                }
            },
        }
    ]
    target = await _pick_heartbeat_target_from_sessions(sessions, {"slack", "telegram"}, store)
    assert target.channel == "slack"
    assert target.chat_id == "C111"
    assert target.session_key == "slack_C111_T222"
    assert target.metadata == {"slack": {"thread_ts": "T222", "channel_type": "channel"}}


def test_background_notify_contract_mentions_message_and_target_context() -> None:
    contract = _build_background_notify_contract(
        source="Heartbeat",
        target_session_key="wechat_acc-a_u_123",
        target_metadata={"wechat": {"account_key": "acc-a"}},
    )
    assert "Only notify when necessary by calling the `message` tool." in contract
    assert "session_key: wechat_acc-a_u_123" in contract
    assert '"account_key": "acc-a"' in contract


def test_build_heartbeat_execute_input_includes_contract_and_tasks() -> None:
    text = _build_heartbeat_execute_input(
        "check pending reviews",
        target_session_key="telegram_1001",
        target_metadata={"foo": "bar"},
    )
    assert "[Heartbeat Task]" in text
    assert "check pending reviews" in text
    assert "[Heartbeat Notification Contract]" in text
    assert "session_key: telegram_1001" in text
    assert '"foo": "bar"' in text


def test_build_cron_execute_input_includes_contract_and_instruction() -> None:
    text = _build_cron_execute_input(
        job_name="daily-check",
        instruction="collect report and notify if needed",
        target_session_key="slack_C123_T456",
    )
    assert "Task 'daily-check' has been triggered." in text
    assert "Scheduled instruction: collect report and notify if needed" in text
    assert "[Cron Notification Contract]" in text
    assert "session_key: slack_C123_T456" in text


def test_looks_like_agent_error_detects_known_failure_texts() -> None:
    assert _looks_like_agent_error("Sorry, I encountered an error calling the AI model.")
    assert _looks_like_agent_error("I reached the maximum number of tool call iterations (40).")
    assert not _looks_like_agent_error("All checks are done. No user notification is required.")


@pytest.mark.asyncio
async def test_suppress_background_progress_is_noop() -> None:
    assert await _suppress_background_progress("running tool call...", tool_hint=True) is None
    assert await _suppress_background_progress("step 1", tool_hint=False) is None
