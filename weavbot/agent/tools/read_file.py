"""Tool to read file contents."""

from pathlib import Path
from typing import Any

from weavbot.agent.tools.base import Tool
from weavbot.agent.tools.filesystem import _resolve_path

# Constants (from read.ts)
DEFAULT_READ_LIMIT = 2000
MAX_LINE_LENGTH = 2000
MAX_LINE_SUFFIX = f"... (line truncated to {MAX_LINE_LENGTH} chars)"
MAX_BYTES = 50 * 1024  # 50 KB
MAX_BYTES_LABEL = "50 KB"

# Binary extensions blacklist (from read.ts isBinaryFile)
_BINARY_EXTENSIONS = frozenset({
    ".zip", ".tar", ".gz", ".exe", ".dll", ".so", ".class", ".jar", ".war",
    ".7z", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp", ".bin", ".dat", ".obj", ".o", ".a", ".lib",
    ".wasm", ".pyc", ".pyo",
})


def _is_binary_extension(path: Path) -> bool:
    """Return True if extension is in binary blacklist."""
    return path.suffix.lower() in _BINARY_EXTENSIONS


def _is_binary_by_content(data: bytes) -> bool:
    """Return True if content appears binary (null byte or >30% non-printable)."""
    if not data:
        return False
    sample = data[:4096]
    non_printable = 0
    for b in sample:
        if b == 0:
            return True
        if b < 9 or (b > 13 and b < 32):
            non_printable += 1
    return non_printable / len(sample) > 0.3


_DESCRIPTION = """Read a file from the local filesystem. If the path does not exist, an error is returned.

Usage:
- The path can be relative to workspace or absolute.
- By default, returns up to 2000 lines from the start of the file.
- The offset parameter is the line number to start from (1-indexed).
- To read later sections, call again with a larger offset.
- Use the grep_file tool to find specific content in large files or files with long lines.
- If unsure of the file path, use the glob_file or list_dir tool to look up filenames.
- Contents are returned with each line prefixed as `<line>: <content>`, e.g. "1: foo".
- Any line longer than 2000 characters is truncated.
- Call this tool in parallel when reading multiple files.
- Avoid tiny repeated slices (e.g. 30 lines); read a larger window when you need more context."""


class ReadFileTool(Tool):
    """Tool to read file contents."""

    def __init__(self, workspace: Path | None = None, allowed_dir: Path | None = None):
        self._workspace = workspace
        self._allowed_dir = allowed_dir

    @property
    def name(self) -> str:
        return "read_file"

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
                    "description": "File path (relative to workspace or absolute)",
                },
                "offset": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Starting line (1-based). Default 1.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Max lines to read. Default 2000.",
                },
            },
            "required": ["path"],
        }

    async def execute(
        self,
        path: str,
        offset: int | None = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            file_path = _resolve_path(path, self._workspace, self._allowed_dir)
            if not file_path.exists():
                return f"Error: File not found: {path}"
            if not file_path.is_file():
                return f"Error: Not a file: {path}"

            offset = offset if offset is not None else 1
            limit = limit if limit is not None else DEFAULT_READ_LIMIT
            if offset < 1:
                return f"Error: offset must be >= 1, got {offset}"

            # Binary detection
            if _is_binary_extension(file_path):
                return f"Error: Cannot read binary file: {path}"
            file_size = file_path.stat().st_size
            if file_size > 0:
                head = file_path.read_bytes()[:4096]
                if _is_binary_by_content(head):
                    return f"Error: Cannot read binary file: {path}"

            # Stream read with offset, limit, line truncation, byte cap
            start = offset - 1
            raw: list[str] = []
            total_lines = 0
            bytes_used = 0
            truncated_by_bytes = False
            has_more_lines = False

            with file_path.open(encoding="utf-8", errors="replace") as f:
                for line_num, line_text in enumerate(f, start=1):
                    total_lines = line_num
                    if line_num <= start:
                        continue
                    if len(raw) >= limit:
                        has_more_lines = True
                        break

                    # Truncate long lines
                    if len(line_text) > MAX_LINE_LENGTH:
                        line_text = line_text[:MAX_LINE_LENGTH] + MAX_LINE_SUFFIX
                    # Strip trailing newline for join; we add it back in output
                    if line_text.endswith("\n"):
                        line_text = line_text[:-1]

                    output_line = f"{line_num}: {line_text}\n"
                    line_bytes = len(output_line.encode("utf-8"))
                    if bytes_used + line_bytes > MAX_BYTES:
                        truncated_by_bytes = True
                        has_more_lines = True
                        break

                    raw.append(line_text)
                    bytes_used += line_bytes

            # Offset out of range
            if total_lines < offset and not (total_lines == 0 and offset == 1):
                return f"Error: Offset {offset} is out of range (file has {total_lines} lines)"

            # Build output
            lines = [f"{start + i + 1}: {raw[i]}" for i in range(len(raw))]
            output = "\n".join(lines)

            last_read_line = offset + len(raw) - 1
            next_offset = last_read_line + 1

            if truncated_by_bytes:
                output += f"\n\n(Output capped at {MAX_BYTES_LABEL}. Showing lines {offset}-{last_read_line}. Use offset={next_offset} to continue.)"
            elif has_more_lines:
                output += f"\n\n(Showing lines {offset}-{last_read_line} of {total_lines}. Use offset={next_offset} to continue.)"
            else:
                output += f"\n\n(End of file - total {total_lines} lines)"

            return output

        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error reading file: {str(e)}"
