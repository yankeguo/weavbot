"""Skills loader for agent capabilities."""

import json
import os
import shutil
from pathlib import Path

import frontmatter

BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"


class SkillsLoader:
    """
    Loader for agent skills.

    Skills are markdown files (SKILL.md) that teach the agent how to use
    specific tools or perform certain tasks.
    """

    def __init__(self, workspace: Path, builtin_skills_dir: Path | None = None):
        self.workspace = workspace
        self.workspace_skills = workspace / "skills"
        self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR

    def _load_skill_post(self, name: str):
        """Load and parse a skill file. Returns frontmatter.Post or None."""
        raw = self._read_skill_file(name)
        if raw is None:
            return None
        try:
            return frontmatter.loads(raw)
        except Exception:
            return None

    def _read_skill_file(self, name: str) -> str | None:
        """Read raw skill file content from workspace (priority) then builtin."""
        for base in (self.workspace_skills, self.builtin_skills):
            if base:
                path = base / name / "SKILL.md"
                if path.exists():
                    return path.read_text(encoding="utf-8")
        return None

    def load_skill(self, name: str) -> str | None:
        return self._read_skill_file(name)

    def get_skill_metadata(self, name: str) -> dict | None:
        post = self._load_skill_post(name)
        if post and isinstance(post.metadata, dict) and post.metadata:
            return post.metadata
        return None

    def load_skills_for_context(self, skill_names: list[str]) -> str:
        parts = []
        for name in skill_names:
            post = self._load_skill_post(name)
            if post:
                body = post.content.strip() if post.content else ""
                parts.append(f'<skill name="{name}">\n{body}\n</skill>')
        return "\n\n---\n\n".join(parts) if parts else ""

    def get_always_skills(self) -> list[str]:
        result = []
        for s in self.list_skills(filter_unavailable=True):
            meta = self.get_skill_metadata(s["name"]) or {}
            weavbot_meta = _parse_weavbot_metadata(meta.get("metadata", ""))
            if weavbot_meta.get("always") or meta.get("always"):
                result.append(s["name"])
        return result

    def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, str]]:
        skills: list[dict[str, str]] = []

        if self.workspace_skills.exists():
            for skill_dir in sorted(self.workspace_skills.iterdir()):
                if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                    skills.append(
                        {
                            "name": skill_dir.name,
                            "path": str(skill_dir / "SKILL.md"),
                            "source": "workspace",
                        }
                    )

        if self.builtin_skills and self.builtin_skills.exists():
            for skill_dir in sorted(self.builtin_skills.iterdir()):
                if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                    if not any(s["name"] == skill_dir.name for s in skills):
                        skills.append(
                            {
                                "name": skill_dir.name,
                                "path": str(skill_dir / "SKILL.md"),
                                "source": "builtin",
                            }
                        )

        if filter_unavailable:
            return [
                s for s in skills if self._check_requirements(self._get_weavbot_meta(s["name"]))
            ]
        return skills

    def build_skills_summary(self) -> str:
        all_skills = self.list_skills(filter_unavailable=False)
        if not all_skills:
            return ""

        lines = ["<skills>"]
        for s in all_skills:
            meta = self.get_skill_metadata(s["name"]) or {}
            weavbot_meta = _parse_weavbot_metadata(meta.get("metadata", ""))
            available = self._check_requirements(weavbot_meta)
            raw_desc = meta.get("description")
            desc = str(raw_desc or s["name"])

            lines.append(f'  <skill available="{str(available).lower()}">')
            lines.append(f"    <name>{_esc(s['name'])}</name>")
            lines.append(f"    <description>{_esc(desc)}</description>")
            lines.append(f"    <location>{_esc(s['path'])}</location>")

            if not available:
                missing = self._get_missing_requirements(weavbot_meta)
                if missing:
                    lines.append(f"    <requires>{_esc(missing)}</requires>")

            lines.append("  </skill>")
        lines.append("</skills>")

        return "\n".join(lines)

    def _get_missing_requirements(self, skill_meta: dict) -> str:
        missing = []
        requires = skill_meta.get("requires", {})
        for b in requires.get("bins", []):
            if not shutil.which(b):
                missing.append(f"CLI: {b}")
        for env in requires.get("env", []):
            if not os.environ.get(env):
                missing.append(f"ENV: {env}")
        return ", ".join(missing)

    def _check_requirements(self, skill_meta: dict) -> bool:
        requires = skill_meta.get("requires", {})
        for b in requires.get("bins", []):
            if not shutil.which(b):
                return False
        for env in requires.get("env", []):
            if not os.environ.get(env):
                return False
        return True

    def _get_weavbot_meta(self, name: str) -> dict:
        meta = self.get_skill_metadata(name) or {}
        return _parse_weavbot_metadata(meta.get("metadata", ""))


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _parse_weavbot_metadata(raw: str) -> dict:
    """Parse skill metadata JSON (supports weavbot and openclaw keys)."""
    try:
        data = json.loads(raw)
        return data.get("weavbot", data.get("openclaw", {})) if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}
