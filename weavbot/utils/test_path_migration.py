import json
from pathlib import Path

from weavbot.utils.path_migration import PathMigration, prepare_runtime_paths

LEGACY_WORKSPACE_DIRNAME = "workspace"
LEGACY_CRON_REL_PATH = Path("cron") / "jobs.json"
LEGACY_SESSIONS_REL_PATH = Path("sessions")


def _write_cron(path: Path, jobs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "jobs": jobs}), encoding="utf-8")


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


def test_merge_cron_store_merges_by_job_id_and_deletes_legacy_dir(tmp_path: Path):
    target = tmp_path / "wbhome" / "cron.json"
    legacy = tmp_path / LEGACY_WORKSPACE_DIRNAME / LEGACY_CRON_REL_PATH

    _write_cron(target, [{"id": "a", "name": "target-a"}])
    _write_cron(legacy, [{"id": "a", "name": "legacy-a"}, {"id": "b", "name": "legacy-b"}])

    PathMigration.merge_cron_store(target, legacy, legacy.parent)

    data = json.loads(target.read_text(encoding="utf-8"))
    assert [j["id"] for j in data["jobs"]] == ["a", "b"]
    assert data["jobs"][0]["name"] == "target-a"
    assert not legacy.parent.exists()


def test_merge_cron_store_creates_target_when_missing(tmp_path: Path):
    target = tmp_path / "wbhome" / "cron.json"
    legacy = tmp_path / LEGACY_WORKSPACE_DIRNAME / LEGACY_CRON_REL_PATH
    _write_cron(legacy, [{"id": "job-1", "name": "legacy"}])

    PathMigration.merge_cron_store(target, legacy, legacy.parent)

    data = json.loads(target.read_text(encoding="utf-8"))
    assert [j["id"] for j in data["jobs"]] == ["job-1"]


def test_merge_sessions_prefers_newer_metadata_and_removes_old_dir(monkeypatch, tmp_path: Path):
    wb_home = tmp_path / "wb-home"
    # Keep "workspace" as legacy fixture input intentionally; migration behavior depends on it.
    workspace = tmp_path / LEGACY_WORKSPACE_DIRNAME
    monkeypatch.setenv("WB_HOME", str(wb_home))

    src_file = workspace / LEGACY_SESSIONS_REL_PATH / "cli_direct.jsonl"
    dst_file = wb_home / "sessions" / "cli_direct.jsonl"
    _write_session(dst_file, "2026-01-01T00:00:00", "target-old")
    _write_session(src_file, "2026-01-02T00:00:00", "legacy-new")

    PathMigration.merge_sessions_dir(wb_home / "sessions", workspace / LEGACY_SESSIONS_REL_PATH)

    text = dst_file.read_text(encoding="utf-8")
    assert "legacy-new" in text
    assert not (workspace / LEGACY_SESSIONS_REL_PATH).exists()


def test_merge_sessions_keeps_target_when_target_newer(monkeypatch, tmp_path: Path):
    wb_home = tmp_path / "wb-home"
    workspace = tmp_path / LEGACY_WORKSPACE_DIRNAME
    monkeypatch.setenv("WB_HOME", str(wb_home))

    src_file = workspace / LEGACY_SESSIONS_REL_PATH / "cli_direct.jsonl"
    dst_file = wb_home / "sessions" / "cli_direct.jsonl"
    _write_session(dst_file, "2026-01-03T00:00:00", "target-new")
    _write_session(src_file, "2026-01-02T00:00:00", "legacy-old")

    PathMigration.merge_sessions_dir(wb_home / "sessions", workspace / LEGACY_SESSIONS_REL_PATH)

    text = dst_file.read_text(encoding="utf-8")
    assert "target-new" in text
    assert not (workspace / LEGACY_SESSIONS_REL_PATH).exists()


def test_run_startup_migrations_merges_cron_and_sessions(monkeypatch, tmp_path: Path):
    wb_home = tmp_path / "wb-home"
    workspace = tmp_path / LEGACY_WORKSPACE_DIRNAME
    monkeypatch.setenv("WB_HOME", str(wb_home))

    _write_cron(workspace / LEGACY_CRON_REL_PATH, [{"id": "job-1", "name": "legacy"}])
    _write_session(
        workspace / LEGACY_SESSIONS_REL_PATH / "cli_direct.jsonl",
        "2026-01-02T00:00:00",
        "legacy",
    )

    PathMigration.run_startup_migrations(workspace)

    cron_data = json.loads((wb_home / "cron.json").read_text(encoding="utf-8"))
    assert [j["id"] for j in cron_data["jobs"]] == ["job-1"]
    assert "legacy" in (wb_home / "sessions" / "cli_direct.jsonl").read_text(encoding="utf-8")
    assert not (workspace / "cron").exists()
    assert not (workspace / LEGACY_SESSIONS_REL_PATH).exists()


def test_prepare_runtime_paths_returns_cron_location_and_runs_migrations(
    monkeypatch, tmp_path: Path
):
    wb_home = tmp_path / "wb-home"
    workspace = tmp_path / LEGACY_WORKSPACE_DIRNAME
    monkeypatch.setenv("WB_HOME", str(wb_home))

    _write_cron(workspace / LEGACY_CRON_REL_PATH, [{"id": "job-2", "name": "legacy-2"}])

    runtime_paths = prepare_runtime_paths(workspace, sync_templates=False)

    assert runtime_paths.workspace == workspace
    assert runtime_paths.cron_store_path == wb_home / "cron.json"
    cron_data = json.loads(runtime_paths.cron_store_path.read_text(encoding="utf-8"))
    assert [j["id"] for j in cron_data["jobs"]] == ["job-2"]
