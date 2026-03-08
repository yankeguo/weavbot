"""Tool to find files by glob pattern."""

from pathlib import Path
from typing import Any

from weavbot.agent.tools.base import Tool
from weavbot.utils import resolve_path

_LIMIT = 100

_DESCRIPTION = """Fast file pattern matching tool that works with any codebase size.
Supports glob patterns like "**/*.js" or "src/**/*.ts".
Returns matching file paths sorted by modification time (newest first).
Use this tool when you need to find files by name patterns.
Call multiple globs in a batch when useful."""


class GlobFileTool(Tool):
    """Tool to find files by glob pattern."""

    def __init__(self, workspace: Path | None = None, allowed_dir: Path | None = None):
        self._workspace = workspace
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "glob_file"

    @property
    def description(self) -> str:
        return _DESCRIPTION

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. **/*.py, src/**/*.ts)",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in (default: workspace)",
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self,
        pattern: str,
        path: str | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            search_path_str = path if path is not None else "."
            base = resolve_path(search_path_str, self._workspace, self._allowed_dir)

            if not base.exists():
                return f"Error: Directory not found: {search_path_str}"
            if not base.is_dir():
                return f"Error: Not a directory: {search_path_str}"

            files: list[tuple[Path, float]] = []
            truncated = False
            for p in base.glob(pattern):
                if not p.is_file():
                    continue
                if len(files) >= _LIMIT:
                    truncated = True
                    break
                mtime = p.stat().st_mtime
                files.append((p, mtime))

            files.sort(key=lambda x: x[1], reverse=True)
            paths = [str(p) for p, _ in files]

            if not paths:
                return "No files found"

            output = "\n".join(paths)
            if truncated:
                output += f"\n\n(Results truncated: showing first {_LIMIT}. Consider a more specific pattern.)"
            return output

        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error: {str(e)}"
