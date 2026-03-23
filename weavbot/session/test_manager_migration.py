import json
from pathlib import Path

from weavbot.utils.path_migration import PathMigration


def _write_session(path: Path, updated_at: str, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "_type": "metadata",
        "key": "cli:direct",
        "created_at": updated_at,
        "updated_at": updated_at,
        "metadata": {},
        "memory_consolidated_cursor": 0,
        "context_compacted_cursor": 0,
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(metadata) + "\n")
        f.write(json.dumps({"role": "assistant", "content": marker}) + "\n")


def test_workspace_sessions_merge_prefers_newer_metadata_and_removes_old_dir(
    monkeypatch, tmp_path: Path
):
    wb_home = tmp_path / "wb-home"
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("WB_HOME", str(wb_home))

    src_file = workspace / "sessions" / "cli_direct.jsonl"
    dst_file = wb_home / "sessions" / "cli_direct.jsonl"
    _write_session(dst_file, "2026-01-01T00:00:00", "target-old")
    _write_session(src_file, "2026-01-02T00:00:00", "legacy-new")

    PathMigration.merge_sessions_dir(wb_home / "sessions", workspace / "sessions")

    text = dst_file.read_text(encoding="utf-8")
    assert "legacy-new" in text
    assert not (workspace / "sessions").exists()


def test_workspace_sessions_merge_keeps_target_when_target_newer(monkeypatch, tmp_path: Path):
    wb_home = tmp_path / "wb-home"
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("WB_HOME", str(wb_home))

    src_file = workspace / "sessions" / "cli_direct.jsonl"
    dst_file = wb_home / "sessions" / "cli_direct.jsonl"
    _write_session(dst_file, "2026-01-03T00:00:00", "target-new")
    _write_session(src_file, "2026-01-02T00:00:00", "legacy-old")

    PathMigration.merge_sessions_dir(wb_home / "sessions", workspace / "sessions")

    text = dst_file.read_text(encoding="utf-8")
    assert "target-new" in text
    assert not (workspace / "sessions").exists()
