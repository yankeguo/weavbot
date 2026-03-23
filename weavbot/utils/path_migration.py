"""Path/data migration utilities for startup."""

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from weavbot.utils.helpers import ensure_data_path, sync_workspace_templates


@dataclass(frozen=True)
class RuntimePaths:
    """Resolved runtime paths after startup preparation."""

    workspace: Path
    data_root: Path
    cron_store_path: Path
    sessions_dir: Path


class PathMigration:
    """Centralized startup migrations for cron and sessions data paths."""

    @staticmethod
    def _read_cron_store_file(path: Path) -> dict[str, Any] | None:
        """Read a cron store json file; return None on decode errors."""
        if not path.exists():
            return {"version": 1, "jobs": []}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Cron migration: failed to parse {}: {}", path, e)
            return None
        if not isinstance(raw, dict):
            logger.warning("Cron migration: invalid root json in {}", path)
            return None
        jobs = raw.get("jobs")
        if jobs is None:
            raw["jobs"] = []
        elif not isinstance(jobs, list):
            logger.warning("Cron migration: invalid jobs array in {}", path)
            return None
        return raw

    @classmethod
    def merge_cron_store(
        cls,
        target_store_path: Path,
        legacy_store_path: Path,
        legacy_dir: Path | None = None,
    ) -> None:
        """
        Merge legacy cron jobs into target store and remove legacy directory afterwards.

        Conflict resolution: keep target job when IDs collide.
        """
        if target_store_path.resolve() == legacy_store_path.resolve():
            return
        if not legacy_store_path.exists():
            return

        target = cls._read_cron_store_file(target_store_path)
        legacy = cls._read_cron_store_file(legacy_store_path)
        if target is None or legacy is None:
            return

        target_jobs = [j for j in target.get("jobs", []) if isinstance(j, dict)]
        legacy_jobs = [j for j in legacy.get("jobs", []) if isinstance(j, dict)]
        target_by_id = {
            str(j.get("id")): j for j in target_jobs if isinstance(j.get("id"), str) and j.get("id")
        }

        merged_jobs = list(target_jobs)
        added = 0
        for job in legacy_jobs:
            job_id = job.get("id")
            if not isinstance(job_id, str) or not job_id:
                continue
            if job_id in target_by_id:
                continue
            merged_jobs.append(job)
            added += 1

        changed = added > 0
        if changed or not target_store_path.exists():
            payload = {"version": target.get("version", 1), "jobs": merged_jobs}
            target_store_path.parent.mkdir(parents=True, exist_ok=True)
            target_store_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info(
                "Cron migration: merged {} jobs from {} into {}",
                added,
                legacy_store_path,
                target_store_path,
            )

        try:
            if legacy_store_path.exists():
                legacy_store_path.unlink()
        except Exception as e:
            logger.warning(
                "Cron migration: failed deleting legacy file {}: {}", legacy_store_path, e
            )

        old_dir = legacy_dir or legacy_store_path.parent
        try:
            if old_dir.exists():
                shutil.rmtree(old_dir)
        except Exception as e:
            logger.warning("Cron migration: failed deleting legacy dir {}: {}", old_dir, e)

    @staticmethod
    def _parse_session_metadata_time(path: Path) -> datetime | None:
        """Parse metadata time from the first line of a session file."""
        try:
            with open(path, encoding="utf-8") as f:
                first_line = f.readline().strip()
            if not first_line:
                return None
            data = json.loads(first_line)
            if not isinstance(data, dict) or data.get("_type") != "metadata":
                return None
            for field_name in ("updated_at", "created_at"):
                value = data.get(field_name)
                if isinstance(value, str) and value:
                    try:
                        return datetime.fromisoformat(value)
                    except ValueError:
                        continue
        except Exception:
            return None
        return None

    @classmethod
    def _session_source_is_newer(cls, source: Path, target: Path) -> bool:
        """
        Return True if source session should replace target session.

        Rule: newer metadata time wins; fallback to mtime.
        """
        source_time = cls._parse_session_metadata_time(source)
        target_time = cls._parse_session_metadata_time(target)
        if source_time and target_time:
            return source_time > target_time
        if source_time and not target_time:
            return True
        if target_time and not source_time:
            return False
        return source.stat().st_mtime > target.stat().st_mtime

    @classmethod
    def merge_sessions_dir(cls, target_root: Path, legacy_root: Path) -> None:
        """Merge legacy workspace sessions into WB_DATA_PATH sessions and clean old dir."""
        if not legacy_root.exists() or not legacy_root.is_dir():
            return
        if legacy_root.resolve() == target_root.resolve():
            return

        migrated = 0
        failed = 0
        for source in legacy_root.rglob("*"):
            if not source.is_file():
                continue
            rel = source.relative_to(legacy_root)
            target = target_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                if not target.exists():
                    shutil.move(str(source), str(target))
                    migrated += 1
                    continue
                if source.suffix == ".jsonl":
                    if cls._session_source_is_newer(source, target):
                        shutil.move(str(source), str(target))
                        migrated += 1
                    else:
                        source.unlink(missing_ok=True)
                    continue
                # Non-session files: keep target-first by default.
                source.unlink(missing_ok=True)
            except Exception as e:
                failed += 1
                logger.warning(
                    "Failed merging legacy session file {} -> {}: {}",
                    source,
                    target,
                    e,
                )

        try:
            shutil.rmtree(legacy_root)
        except Exception as e:
            logger.warning("Failed deleting legacy sessions dir {}: {}", legacy_root, e)

        if migrated or failed:
            logger.info(
                "Session migration from workspace completed: migrated={}, failed={}, source={}",
                migrated,
                failed,
                legacy_root,
            )

    @classmethod
    def run_startup_migrations(cls, workspace: Path, data_root: Path | None = None) -> None:
        """Run all startup path migrations for cron and sessions."""
        root = data_root or ensure_data_path()

        cron_target = root / "cron.json"
        cron_legacy = workspace / "cron" / "jobs.json"
        cls.merge_cron_store(cron_target, cron_legacy, cron_legacy.parent)

        sessions_target = root / "sessions"
        sessions_target.mkdir(parents=True, exist_ok=True)
        sessions_legacy = workspace / "sessions"
        cls.merge_sessions_dir(sessions_target, sessions_legacy)


def prepare_runtime_paths(workspace: Path, *, sync_templates: bool = True) -> RuntimePaths:
    """Prepare workspace/data paths for runtime startup and return resolved locations."""
    if sync_templates:
        sync_workspace_templates(workspace)
    data_root = ensure_data_path()
    PathMigration.run_startup_migrations(workspace, data_root=data_root)
    return RuntimePaths(
        workspace=workspace,
        data_root=data_root,
        cron_store_path=data_root / "cron.json",
        sessions_dir=data_root / "sessions",
    )
