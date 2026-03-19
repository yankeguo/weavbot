"""Tool to load local image/video files into the chat context."""

import mimetypes
from pathlib import Path
from typing import Any

from weavbot.agent.tools.base import Tool, ToolResult
from weavbot.utils import resolve_path

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

_IMAGE_PREFIXES = ("image/",)
_VIDEO_PREFIXES = ("video/",)
_SUPPORTED_PREFIXES = _IMAGE_PREFIXES + _VIDEO_PREFIXES

_DESCRIPTION = """Load a local image or video file into the chat context so you can see and analyze its contents.

Usage:
- The path can be relative to workspace or absolute.
- Supported media: common image formats (jpeg, png, gif, webp, ...) and video formats (mp4, webm, mov, ...).
- Maximum file size: 20 MB.
- Video support depends on the underlying model — not all models can process video.
- Use this tool when you need to visually inspect an image or video file."""


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


class LoadMediaTool(Tool):
    """Tool to load local media files into the chat context as multimodal content."""

    def __init__(self, workspace: Path, allowed_dir: Path | None = None):
        self._workspace = workspace
        self._allowed_dir = allowed_dir

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
                    "description": "File path to the image or video (relative to workspace or absolute)",
                },
            },
            "required": ["path"],
        }

    async def execute(self, path: str, **kwargs: Any) -> str | ToolResult:
        try:
            file_path = resolve_path(path, self._workspace, self._allowed_dir)
            if not file_path.exists():
                return f"Error: File not found: {path}"
            if not file_path.is_file():
                return f"Error: Not a file: {path}"

            mime, _ = mimetypes.guess_type(str(file_path))
            if not mime or not any(mime.startswith(p) for p in _SUPPORTED_PREFIXES):
                return f"Error: Unsupported media type ({mime or 'unknown'}). Expected image/* or video/*."

            size = file_path.stat().st_size
            if size > MAX_FILE_SIZE:
                return f"Error: File too large ({_human_size(size)}). Maximum is {_human_size(MAX_FILE_SIZE)}."
            if size == 0:
                return f"Error: File is empty: {path}"

            return ToolResult(
                content=f"Media loaded: {file_path.name} ({mime}, {_human_size(size)})",
                media=[str(file_path)],
            )
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error loading media: {e}"
