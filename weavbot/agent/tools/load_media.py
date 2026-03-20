"""Tool to load local media files into chat context."""

import mimetypes
from pathlib import Path
from typing import Any

from weavbot.agent.tools.base import Tool, ToolResult
from weavbot.utils import resolve_path

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

_SUPPORTED_PREFIXES = ("image/", "audio/", "video/")
_SUPPORTED_EXACT = ("application/pdf",)

_DESCRIPTION = """Load a local media file into chat context.

Usage:
- The path can be relative to workspace or absolute.
- Supported: images (jpeg, png, gif, webp, ...), audio (wav, mp3, ogg, ...), video (mp4, webm, mov, ...), and PDF.
- Maximum file size: 20 MB.
- Only image/* is attached as multimodal input.
- Non-image files are kept as file paths in text context."""


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
            supported = (
                any(mime.startswith(p) for p in _SUPPORTED_PREFIXES) or mime in _SUPPORTED_EXACT
            )
            if not mime or not supported:
                return f"Error: Unsupported media type ({mime or 'unknown'}). Expected image/*, audio/*, video/*, or application/pdf."

            size = file_path.stat().st_size
            if size > MAX_FILE_SIZE:
                return f"Error: File too large ({_human_size(size)}). Maximum is {_human_size(MAX_FILE_SIZE)}."
            if size == 0:
                return f"Error: File is empty: {path}"

            path_text = str(file_path)
            if mime.startswith("image/"):
                return ToolResult(
                    content=f"Media loaded: {path_text} ({mime}, {_human_size(size)})",
                    media=[path_text],
                )
            return ToolResult(
                content=(
                    f"File loaded: {path_text} ({mime}, {_human_size(size)}). "
                    "Non-image files are passed as file-path context only."
                ),
                media=[],
            )
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error loading media: {e}"
