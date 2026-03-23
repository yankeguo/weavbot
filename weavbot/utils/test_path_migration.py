import json
from pathlib import Path

from weavbot.utils.path_migration import PathMigration, prepare_runtime_paths


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


def test_run_startup_migrations_merges_cron_and_sessions(monkeypatch, tmp_path: Path):
    wb_home = tmp_path / "wb-home"
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("WB_HOME", str(wb_home))

    _write_cron(workspace / "cron" / "jobs.json", [{"id": "job-1", "name": "legacy"}])
    _write_session(workspace / "sessions" / "cli_direct.jsonl", "2026-01-02T00:00:00", "legacy")

    PathMigration.run_startup_migrations(workspace)

    cron_data = json.loads((wb_home / "cron.json").read_text(encoding="utf-8"))
    assert [j["id"] for j in cron_data["jobs"]] == ["job-1"]
    assert "legacy" in (wb_home / "sessions" / "cli_direct.jsonl").read_text(encoding="utf-8")
    assert not (workspace / "cron").exists()
    assert not (workspace / "sessions").exists()


def test_prepare_runtime_paths_returns_cron_location_and_runs_migrations(
    monkeypatch, tmp_path: Path
):
    wb_home = tmp_path / "wb-home"
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("WB_HOME", str(wb_home))

    _write_cron(workspace / "cron" / "jobs.json", [{"id": "job-2", "name": "legacy-2"}])

    runtime_paths = prepare_runtime_paths(workspace, sync_templates=False)

    assert runtime_paths.workspace == workspace
    assert runtime_paths.cron_store_path == wb_home / "cron.json"
    cron_data = json.loads(runtime_paths.cron_store_path.read_text(encoding="utf-8"))
    assert [j["id"] for j in cron_data["jobs"]] == ["job-2"]
