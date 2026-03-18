from weavbot.cli.commands import _assemble_heartbeat_response, _collect_heartbeat_progress


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
