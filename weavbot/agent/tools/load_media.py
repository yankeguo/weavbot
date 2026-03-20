"""Tool to load local media files into chat context."""

import mimetypes
from pathlib import Path
from typing import Any

from weavbot.agent.tools.base import Tool, ToolResult
from weavbot.utils import resolve_path

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

_SUPPORTED_PREFIX = "image/"

_DESCRIPTION = """Load a local media file into chat context.

Usage:
- The path can be relative to workspace or absolute.
- Supported: images only (jpeg, png, gif, webp, ...).
- Maximum file size: 20 MB.
- The file is attached as multimodal image input."""


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


class LoadMediaTool(Tool):
    """Tool to load local media files into chat context."""

    def __init__(self, workspace: Path, restrict_to_workspace: bool = False):
        self._workspace = workspace
        self._restrict_to_workspace = restrict_to_workspace

    @property
    def name(self) -> str:
        return "load_media"

    @property
    def description(self) -> str:
        return _DESCRIPTION

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to the media file (relative to workspace or absolute)",
                },
            },
            "required": ["path"],
        }

    async def execute(self, path: str, **kwargs: Any) -> str | ToolResult:
        try:
            file_path = resolve_path(path, self._workspace, self._restrict_to_workspace)
            if not file_path.exists():
                return f"Error: File not found: {path}"
            if not file_path.is_file():
                return f"Error: Not a file: {path}"

            mime, _ = mimetypes.guess_type(str(file_path))
            if not mime or not mime.startswith(_SUPPORTED_PREFIX):
                return f"Error: Unsupported media type ({mime or 'unknown'}). Expected image/*."

            size = file_path.stat().st_size
            if size > MAX_FILE_SIZE:
                return f"Error: File too large ({_human_size(size)}). Maximum is {_human_size(MAX_FILE_SIZE)}."
            if size == 0:
                return f"Error: File is empty: {path}"

            path_text = str(file_path)
            return ToolResult(
                content=f"Media loaded: {path_text} ({mime}, {_human_size(size)})",
                media=[path_text],
            )
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error loading media: {e}"
