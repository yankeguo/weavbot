import json
from pathlib import Path

from weavbot.utils.path_migration import PathMigration


def _write_store(path: Path, jobs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "jobs": jobs}), encoding="utf-8")


def test_merge_legacy_store_merges_by_job_id_and_deletes_legacy_dir(tmp_path: Path):
    target = tmp_path / "wbhome" / "cron.json"
    legacy = tmp_path / "workspace" / "cron" / "jobs.json"

    _write_store(target, [{"id": "a", "name": "target-a"}])
    _write_store(legacy, [{"id": "a", "name": "legacy-a"}, {"id": "b", "name": "legacy-b"}])

    PathMigration.merge_cron_store(target, legacy, legacy.parent)

    data = json.loads(target.read_text(encoding="utf-8"))
    assert [j["id"] for j in data["jobs"]] == ["a", "b"]
    assert data["jobs"][0]["name"] == "target-a"
    assert not legacy.parent.exists()


def test_merge_legacy_store_creates_target_when_missing(tmp_path: Path):
    target = tmp_path / "wbhome" / "cron.json"
    legacy = tmp_path / "workspace" / "cron" / "jobs.json"
    _write_store(legacy, [{"id": "job-1", "name": "legacy"}])

    PathMigration.merge_cron_store(target, legacy, legacy.parent)

    data = json.loads(target.read_text(encoding="utf-8"))
    assert [j["id"] for j in data["jobs"]] == ["job-1"]
